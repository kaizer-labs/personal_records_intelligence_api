from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/health_check")

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "Personal Records Intelligence API"
    assert payload["version"] == "0.1.0"
    assert payload["environment"] == "development"
    assert payload["database"]["status"] == "ok"
    assert payload["database"]["engine"] == "duckdb"
    assert payload["database"]["path"]
    assert payload["database"]["table_count"] >= 1
