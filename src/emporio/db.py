"""Acesso somente leitura ao catálogo tratado."""
from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

from .config import CATALOG_DB
from .ingest import ensure_built


@lru_cache(maxsize=4)
def _connect(path: str) -> sqlite3.Connection:
    ensure_built(Path(path))
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def query(sql: str, params: tuple = (), db_path: Path = CATALOG_DB) -> list[dict]:
    return [dict(r) for r in _connect(str(db_path)).execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple = (), db_path: Path = CATALOG_DB) -> dict | None:
    rows = query(sql, params, db_path)
    return rows[0] if rows else None
