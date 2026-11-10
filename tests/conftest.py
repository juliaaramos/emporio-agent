import pytest

from emporio.ingest import ensure_built
from emporio.session import SessionState, Store


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    """Todos os testes rodam em 25/03/2026 10:30 (quarta-feira), salvo override."""
    monkeypatch.setenv("REFERENCE_DATE", "2026-03-25")
    monkeypatch.setenv("REFERENCE_TIME", "10:30")
    ensure_built()


@pytest.fixture
def state():
    return SessionState("test")


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "sessions.db")
