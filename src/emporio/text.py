"""Utilidades de texto: normalização sem acentos e formatação de moeda."""
from __future__ import annotations

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal


def normalize(text: str | None) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    no_accents = re.sub(r"[‐-―−]", "-", no_accents)  # hífens Unicode ("e‑mail")
    return re.sub(r"\s+", " ", no_accents.lower()).strip()


def tokens(text: str | None) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", normalize(text)) if t]


def money(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def brl(value: Decimal | float | int) -> str:
    """Formata em reais no padrão brasileiro: R$ 1.234,56."""
    v = money(value)
    inteiro, centavos = f"{v:.2f}".split(".")
    sign = "-" if inteiro.startswith("-") else ""
    inteiro = inteiro.lstrip("-")
    grupos = []
    while inteiro:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    return f"{sign}R$ {'.'.join(grupos)},{centavos}"


def digits(text: str | None) -> str:
    return re.sub(r"\D", "", text or "")
