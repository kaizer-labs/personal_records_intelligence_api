from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import Settings


class OllamaServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class OllamaChatResult:
    content: str
    model: str


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._chat_model = settings.ollama_chat_model
        self._embedding_model = settings.ollama_embedding_model
        self._chat_num_ctx = settings.ollama_chat_num_ctx

    @property
    def chat_model(self) -> str:
        return self._chat_model

    @property
    def embedding_model(self) -> str:
        return self._embedding_model

    def chat(self, *, system_prompt: str, user_prompt: str) -> OllamaChatResult:
        payload = {
            "model": self._chat_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {"num_ctx": self._chat_num_ctx},
        }

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

    def embedding_model_available(self) -> bool:
        try:
            with httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
                response = client.get(f"{self._base_url}/api/tags")
                response.raise_for_status()
        except httpx.HTTPError:
            return False

        data = response.json()
        models = data.get("models", [])
        return any(str(model.get("name", "")) == self._embedding_model for model in models)

    def embed_text(self, text: str) -> list[float]:
        if not self.embedding_model_available():
            raise OllamaServiceError(
                f'Embedding model "{self._embedding_model}" is not available in Ollama.'
            )

        return self._embed_text_without_check(text)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if not self.embedding_model_available():
            raise OllamaServiceError(
                f'Embedding model "{self._embedding_model}" is not available in Ollama.'
            )

        return [self._embed_text_without_check(text) for text in texts]

    def _embed_text_without_check(self, text: str) -> list[float]:
        payload = {
            "model": self._embedding_model,
            "input": text,
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

        first_embedding = embeddings[0]
        return [float(value) for value in first_embedding]
