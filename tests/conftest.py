import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Каждый тест работает со своей чистой базой
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_company(client):
    counter = {"n": 0}

    def make():
        counter["n"] += 1
        bin_ = f"{counter['n']:012d}"
        r = client.post("/companies", json={"name": f"ТОО Тест {counter['n']}", "bin": bin_, "phone": "+77011234567"})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    return make
