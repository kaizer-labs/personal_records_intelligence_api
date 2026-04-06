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
        self._chat_num_ctx = settings.ollama_chat_num_ctx

    @property
    def chat_model(self) -> str:
        return self._chat_model

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
