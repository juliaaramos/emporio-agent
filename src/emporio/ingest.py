"""Ingestão: CSVs brutos (data/raw, nunca alterados) -> cópia tratada em SQLite.

Uso: python -m emporio.ingest
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from .config import CATALOG_DB, RAW_DIR
from .data_quality import FLAG_REVIEW, check_products

TABLES = ["categories", "customers", "orders", "order_items", "products", "promotions"]

SCHEMA = """
CREATE TABLE categories (category_id INTEGER PRIMARY KEY, name TEXT, description TEXT);
CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT, phone TEXT, email TEXT, city TEXT);
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY, price_brl REAL NOT NULL, name TEXT NOT NULL,
    category_id INTEGER REFERENCES categories, description TEXT, stock_quantity INTEGER,
    status TEXT, specs TEXT, created_at TEXT,
    data_quality_flag TEXT, data_quality_reasons TEXT
);
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers, order_date TEXT,
    status TEXT, total_brl REAL, payment_method TEXT, tracking_code TEXT,
    estimated_delivery TEXT, notes TEXT
);
CREATE TABLE order_items (order_id INTEGER REFERENCES orders, quantity INTEGER, product_id INTEGER REFERENCES products);
CREATE TABLE promotions (
    promotion_id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products,
    discount_percent REAL, description TEXT, is_active INTEGER
);
"""


def read_raw(raw_dir: Path = RAW_DIR) -> dict[str, list[dict]]:
    out = {}
    for t in TABLES:
        with open(raw_dir / f"{t}.csv", encoding="utf-8", newline="") as f:
            out[t] = list(csv.DictReader(f))
    return out


def _none_if_empty(v):
    return None if v is None or str(v).strip() == "" else v


def build(db_path: Path = CATALOG_DB, raw_dir: Path = RAW_DIR) -> Path:
    raw = read_raw(raw_dir)
    checks = check_products(raw["products"])
    tmp = db_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    for t in TABLES:
        rows = raw[t]
        if t == "products":
            for r in rows:
                chk = checks[int(r["product_id"])]
                r["data_quality_flag"] = FLAG_REVIEW if chk.flagged else None
                r["data_quality_reasons"] = "; ".join(chk.reasons) or None
        cols = list(rows[0].keys())
        con.executemany(
            f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [[_none_if_empty(r[c]) for c in cols] for r in rows],
        )
    con.commit()
    con.close()
    tmp.replace(db_path)
    return db_path


def ensure_built(db_path: Path = CATALOG_DB) -> Path:
    """Reconstrói o banco se ele não existir ou se algum CSV for mais novo."""
    if db_path.exists():
        newest = max((RAW_DIR / f"{t}.csv").stat().st_mtime for t in TABLES)
        if db_path.stat().st_mtime >= newest:
            return db_path
    return build(db_path)


if __name__ == "__main__":
    path = build()
    print(f"Banco tratado gerado em {path}")
