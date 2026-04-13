from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.services import ollama as ollama_module
from app.services.ollama import OllamaClient, OllamaServiceError


class FakeResponse:
    def __init__(
        self,
        *,
        payload: dict[str, object] | None = None,
        lines: list[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._payload = payload or {}
        self._lines = lines or []
        self._error = error

    def raise_for_status(self) -> None:
        if self._error is not None:
            raise self._error

    def json(self) -> dict[str, object]:
        return self._payload

    def iter_lines(self):
        for line in self._lines:
            yield line

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class FakeClient:
    def __init__(
        self,
        *,
        post_response: FakeResponse | None = None,
        get_response: FakeResponse | None = None,
        stream_response: FakeResponse | None = None,
        record: dict[str, object] | None = None,
    ) -> None:
        self._post_response = post_response or FakeResponse()
        self._get_response = get_response or FakeResponse()
        self._stream_response = stream_response or FakeResponse()
        self._record = record if record is not None else {}

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def post(self, url: str, json: dict[str, object]) -> FakeResponse:
        self._record.setdefault("posts", []).append((url, json))
        return self._post_response

    def get(self, url: str) -> FakeResponse:
        self._record["last_get_url"] = url
        self._record["get_calls"] = int(self._record.get("get_calls", 0)) + 1
        return self._get_response

    def stream(self, method: str, url: str, json: dict[str, object]) -> FakeResponse:
        self._record.setdefault("streams", []).append((method, url, json))
        return self._stream_response


def build_settings(*, num_predict: int | None = 256) -> Settings:
    return Settings(
        app_name="PRI API",
        app_version="0.1.0",
        app_env="test",
        cors_origins=["http://localhost:5173"],
        duckdb_path="/tmp/app.duckdb",
        storage_root="/tmp/storage",
        examples_path="/tmp/examples",
        ollama_base_url="http://ollama.test",
        ollama_chat_model="chat-model",
        ollama_embedding_model="embed-model",
        ollama_chat_num_ctx=4096,
        ollama_chat_num_predict=num_predict,
    )


def test_chat_success_and_payload(monkeypatch) -> None:
    record: dict[str, object] = {}
    monkeypatch.setattr(
        ollama_module.httpx,
        "Client",
        lambda timeout: FakeClient(
            post_response=FakeResponse(
                payload={"message": {"content": "Answer text"}, "model": "chat-model-v2"}
            ),
            record=record,
        ),
    )

    client = OllamaClient(build_settings())
    result = client.chat(system_prompt="System", user_prompt="User")

    assert result.content == "Answer text"
    assert result.model == "chat-model-v2"
    assert record["posts"][0][0] == "http://ollama.test/api/chat"
    payload = record["posts"][0][1]
    assert payload["options"]["num_ctx"] == 4096
    assert payload["options"]["num_predict"] == 256


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (
            FakeResponse(
                error=httpx.ConnectError("boom"),
            ),
            "Unable to reach Ollama for chat generation.",
        ),
        (
            FakeResponse(
                payload={"message": {"content": "   "}},
            ),
            "Ollama returned an empty response.",
        ),
    ],
)
def test_chat_errors(monkeypatch, response: FakeResponse, message: str) -> None:
    monkeypatch.setattr(
        ollama_module.httpx,
        "Client",
        lambda timeout: FakeClient(post_response=response),
    )

    client = OllamaClient(build_settings())
    with pytest.raises(OllamaServiceError, match=message):
        client.chat(system_prompt="System", user_prompt="User")


def test_chat_stream_success_and_invalid_json(monkeypatch) -> None:
    record: dict[str, object] = {}
    monkeypatch.setattr(
        ollama_module.httpx,
        "Client",
        lambda timeout: FakeClient(
            stream_response=FakeResponse(
                lines=[
                    json.dumps(
                        {"message": {"content": "Hello "}, "model": "chat-model", "done": False}
                    ),
                    json.dumps(
                        {"message": {"content": "world"}, "model": "chat-model", "done": True}
                    ),
                ]
            ),
            record=record,
        ),
    )

    client = OllamaClient(build_settings())
    deltas = list(client.chat_stream(system_prompt="System", user_prompt="User"))
    assert [delta.content for delta in deltas] == ["Hello ", "world"]
    assert deltas[-1].done is True
    assert record["streams"][0][0] == "POST"

    monkeypatch.setattr(
        ollama_module.httpx,
        "Client",
        lambda timeout: FakeClient(
            stream_response=FakeResponse(lines=["{not-json"]),
        ),
    )
    with pytest.raises(OllamaServiceError, match="unreadable streamed response"):
        list(client.chat_stream(system_prompt="System", user_prompt="User"))


def test_embedding_model_available_uses_cache_and_handles_failure(monkeypatch) -> None:
    record: dict[str, object] = {}
    time_values = iter([100.0, 100.0, 140.0, 140.0])
    monkeypatch.setattr(ollama_module, "monotonic", lambda: next(time_values))
    monkeypatch.setattr(
        ollama_module.httpx,
        "Client",
        lambda timeout: FakeClient(
            get_response=FakeResponse(
                payload={"models": [{"name": "embed-model"}]},
            ),
            record=record,
        ),
    )

    client = OllamaClient(build_settings())
    assert client.embedding_model_available() is True
    assert client.embedding_model_available() is True
    assert record["get_calls"] == 1

    monkeypatch.setattr(
        ollama_module.httpx,
        "Client",
        lambda timeout: FakeClient(
            get_response=FakeResponse(error=httpx.ConnectError("boom")),
        ),
    )
    assert client.embedding_model_available() is False


def test_embed_text_and_embed_texts(monkeypatch) -> None:
    monkeypatch.setattr(
        OllamaClient,
        "embedding_model_available",
        lambda self: True,
    )
    monkeypatch.setattr(
        ollama_module.httpx,
        "Client",
        lambda timeout: FakeClient(
            post_response=FakeResponse(payload={"embeddings": [[1, 2], [3, 4]]}),
        ),
    )

    client = OllamaClient(build_settings())
    assert client.embed_text("hello") == [1.0, 2.0]
    assert client.embed_texts(["hello", "world"]) == [[1.0, 2.0], [3.0, 4.0]]
    assert client.embed_texts([]) == []


def test_embedding_errors(monkeypatch) -> None:
    unavailable_client = OllamaClient(build_settings())
    monkeypatch.setattr(
        OllamaClient,
        "embedding_model_available",
        lambda self: False,
    )
    with pytest.raises(OllamaServiceError, match='Embedding model "embed-model" is not available'):
        unavailable_client.embed_text("hello")

    monkeypatch.setattr(
        OllamaClient,
        "embedding_model_available",
        lambda self: True,
    )
    client = OllamaClient(build_settings(num_predict=None))
    payload = client._build_chat_payload(system_prompt="System", user_prompt="User")
    assert "num_predict" not in payload["options"]

    monkeypatch.setattr(
        ollama_module.httpx,
        "Client",
        lambda timeout: FakeClient(
            post_response=FakeResponse(error=httpx.ConnectError("boom")),
        ),
    )
    with pytest.raises(OllamaServiceError, match="Unable to reach Ollama for embeddings."):
        client._embed_inputs_without_check("hello")

    monkeypatch.setattr(
        ollama_module.httpx,
        "Client",
        lambda timeout: FakeClient(
            post_response=FakeResponse(payload={"embeddings": []}),
        ),
    )
    with pytest.raises(OllamaServiceError, match="empty embedding response"):
        client._embed_inputs_without_check("hello")
