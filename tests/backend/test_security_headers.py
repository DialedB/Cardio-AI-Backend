import pytest 
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.config import Settings

def test_security_headers_in_test_environment():
    settings = Settings(app_env="test")
    app = create_app(settings)
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Strict-Transport-Security" in response.headers

def test_security_headers_in_local_environment():
    settings = Settings(app_env="local")
    app = create_app(settings)
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Strict-Transport-Security" not in response.headers