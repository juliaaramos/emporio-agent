"""Sessão: histórico persistido em SQLite, estado volátil (cliente verificado) e chamados.

O estado de verificação NÃO é persistido: ao retomar uma sessão, o cliente precisa
se identificar de novo. O histórico contém dados pessoais (LGPD): em produção,
reter por prazo definido e anonimizar depois (ver README).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import SESSIONS_DB, reference_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, created_at TEXT, model TEXT);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, created_at TEXT, message TEXT
);
CREATE TABLE IF NOT EXISTS tickets (
    protocolo TEXT PRIMARY KEY, session_id TEXT, customer_id INTEGER, order_id INTEGER,
    categoria TEXT, resumo TEXT, created_at TEXT, status TEXT
);
"""
MAX_VERIFY_ATTEMPTS = 3


@dataclass
class SessionState:
    session_id: str
    verified_customer_id: int | None = None
    failed_verifications: int = 0
    tool_log: list[dict] = field(default_factory=list)


class Store:
    def __init__(self, path: Path = SESSIONS_DB):
        self.path = path
        self.con = sqlite3.connect(path)
        self.con.executescript(SCHEMA)

    # --- sessões e mensagens ---
    def new_session(self, model: str) -> str:
        sid = uuid.uuid4().hex[:8]
        self.con.execute("INSERT INTO sessions VALUES (?,?,?)", (sid, datetime.now().isoformat(), model))
        self.con.commit()
        return sid

    def session_exists(self, sid: str) -> bool:
        return self.con.execute("SELECT 1 FROM sessions WHERE session_id=?", (sid,)).fetchone() is not None

    def last_session(self) -> str | None:
        row = self.con.execute("SELECT session_id FROM sessions ORDER BY created_at DESC LIMIT 1").fetchone()
        return row[0] if row else None

    def append(self, sid: str, message: dict) -> None:
        self.con.execute(
            "INSERT INTO messages (session_id, created_at, message) VALUES (?,?,?)",
            (sid, datetime.now().isoformat(), json.dumps(message, ensure_ascii=False)),
        )
        self.con.commit()

    def history(self, sid: str) -> list[dict]:
        rows = self.con.execute("SELECT message FROM messages WHERE session_id=? ORDER BY id", (sid,))
        return [json.loads(r[0]) for r in rows]

    # --- chamados ---
    def open_ticket_for(self, sid: str, order_id: int) -> str | None:
        row = self.con.execute(
            "SELECT protocolo FROM tickets WHERE session_id=? AND order_id=? AND status='aberto'", (sid, order_id)
        ).fetchone()
        return row[0] if row else None

    def open_ticket(self, sid: str, customer_id: int | None, order_id: int | None, categoria: str, resumo: str) -> str:
        n = self.con.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] + 1
        protocolo = f"EMP-{reference_now():%Y%m%d}-{n:04d}"
        self.con.execute(
            "INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?)",
            (protocolo, sid, customer_id, order_id, categoria, resumo, reference_now().isoformat(), "aberto"),
        )
        self.con.commit()
        return protocolo
