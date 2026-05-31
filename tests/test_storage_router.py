from src import storage_router
from src import storage


def test_storage_router_defaults_to_sqlite(monkeypatch):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)

    assert storage_router._backend() is storage


def test_storage_router_selects_sqlite_for_unknown_missing_env(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "sqlite")

    assert storage_router._backend() is storage
