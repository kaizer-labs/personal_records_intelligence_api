from __future__ import annotations

from dataclasses import dataclass
import json
from time import monotonic
from typing import Iterator

import httpx

from app.core.config import Settings


class OllamaServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class OllamaChatResult:
    content: str
    model: str


@dataclass(frozen=True)
class OllamaChatDelta:
    content: str
    model: str
    done: bool = False


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._chat_model = settings.ollama_chat_model
        self._embedding_model = settings.ollama_embedding_model
        self._chat_num_ctx = settings.ollama_chat_num_ctx
        self._chat_num_predict = settings.ollama_chat_num_predict
        self._embedding_model_available_cache: bool | None = None
        self._embedding_model_checked_at = 0.0
        self._embedding_model_cache_ttl_seconds = 30.0

    @property
    def chat_model(self) -> str:
        return self._chat_model

    @property
    def embedding_model(self) -> str:
        return self._embedding_model

    def chat(self, *, system_prompt: str, user_prompt: str) -> OllamaChatResult:
        payload = self._build_chat_payload(system_prompt=system_prompt, user_prompt=user_prompt)

        try:
            with httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                response = client.post(f"{self._base_url}/api/chat", json=payload)
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise OllamaServiceError("Unable to reach Ollama for chat generation.") from error

        data = response.json()
        message = data.get("message", {})
        content = str(message.get("content", "")).strip()

        if not content:
            raise OllamaServiceError("Ollama returned an empty response.")

        return OllamaChatResult(content=content, model=str(data.get("model", self._chat_model)))

    def chat_stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> Iterator[OllamaChatDelta]:
        payload = self._build_chat_payload(system_prompt=system_prompt, user_prompt=user_prompt)
        payload["stream"] = True

        try:
            with httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
                with client.stream("POST", f"{self._base_url}/api/chat", json=payload) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line:
                            continue

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError as error:
                            raise OllamaServiceError(
                                "Ollama returned an unreadable streamed response."
                            ) from error

                        message = data.get("message", {})
                        yield OllamaChatDelta(
                            content=str(message.get("content", "")),
                            model=str(data.get("model", self._chat_model)),
                            done=bool(data.get("done", False)),
                        )
        except httpx.HTTPError as error:
            raise OllamaServiceError("Unable to reach Ollama for chat generation.") from error

    def _build_chat_payload(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, object]:
        payload = {
            "model": self._chat_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "num_ctx": self._chat_num_ctx,
            },
        }
        if self._chat_num_predict is not None:
            payload["options"]["num_predict"] = self._chat_num_predict
        return payload

    def embedding_model_available(self) -> bool:
        if (
            self._embedding_model_available_cache is not None
            and (monotonic() - self._embedding_model_checked_at)
            < self._embedding_model_cache_ttl_seconds
        ):
            return self._embedding_model_available_cache

        try:
            with httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
                response = client.get(f"{self._base_url}/api/tags")
                response.raise_for_status()
        except httpx.HTTPError:
            self._embedding_model_available_cache = False
            self._embedding_model_checked_at = monotonic()
            return False

        data = response.json()
        models = data.get("models", [])
        available = any(
            str(model.get("name", "")) == self._embedding_model for model in models
        )
        self._embedding_model_available_cache = available
        self._embedding_model_checked_at = monotonic()
        return available

    def embed_text(self, text: str) -> list[float]:
        if not self.embedding_model_available():
            raise OllamaServiceError(
                f'Embedding model "{self._embedding_model}" is not available in Ollama.'
            )

        embeddings = self._embed_inputs_without_check(text)
        if not embeddings:
            raise OllamaServiceError("Ollama returned an empty embedding response.")

        return embeddings[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if not self.embedding_model_available():
            raise OllamaServiceError(
                f'Embedding model "{self._embedding_model}" is not available in Ollama.'
            )

        return self._embed_inputs_without_check(texts)

    def _embed_inputs_without_check(self, inputs: str | list[str]) -> list[list[float]]:
        payload = {
            "model": self._embedding_model,
            "input": inputs,
        }

        try:
            with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                response = client.post(f"{self._base_url}/api/embed", json=payload)
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise OllamaServiceError("Unable to reach Ollama for embeddings.") from error

        data = response.json()
        embeddings = data.get("embeddings", [])
        if not embeddings:
            raise OllamaServiceError("Ollama returned an empty embedding response.")

        return [[float(value) for value in embedding] for embedding in embeddings]
