from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoints_are_compatible() -> None:
    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/health").json() == {"status": "ok"}
