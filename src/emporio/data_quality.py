"""Regras de qualidade de dados.

Nada aqui altera os CSVs originais: as regras produzem flags que a ingestão grava
na cópia tratada (SQLite) e um relatório para a equipe de catálogo.

Uso: python -m emporio.data_quality   (imprime o relatório)
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median

from .text import normalize

FLAG_REVIEW = "cadastro_em_revisao"

BRANDS = [
    "music man", "yamaha", "tagima", "giannini", "rozini", "shelby", "crafter", "martin",
    "taylor", "takamine", "kala", "ohana", "kalani", "fender", "gibson", "ibanez", "prs",
    "pearl", "tama", "korg", "nord", "roland",
]
# Modelos que identificam a marca mesmo sem o nome dela no texto.
MODEL_TO_BRAND = {
    "precision": "fender", "jazz bass": "fender", "stratocaster": "fender",
    "telecaster": "fender", "les paul": "gibson", "stingray": "music man",
    "stage custom": "yamaha", "export": "pearl", "star-mount": "tama",
    "nord stage": "nord", "supernatural": "roland",
}
GENERIC_NAME = re.compile(r"\b(bass|kit|synth)\s+\d+x?\b", re.IGNORECASE)
WOODS = ["maple", "birch", "poplar", "mogno", "mahogany", "alder", "ash", "basswood"]
ATYPICAL_PRICE_RATIO = 0.25  # preço < 25% da mediana da categoria


@dataclass
class ProductCheck:
    product_id: int
    reasons: list[str] = field(default_factory=list)

    @property
    def flagged(self) -> bool:
        return bool(self.reasons)


def _brands_in(text: str) -> set[str]:
    t = normalize(text)
    found = {b for b in BRANDS if re.search(rf"\b{re.escape(b)}\b", t)}
    found |= {brand for model, brand in MODEL_TO_BRAND.items() if model in t}
    # "music man" contém "man"; nenhuma outra marca é prefixo, então basta isso.
    return found


def _name_brand(name: str) -> str | None:
    t = normalize(name)
    hits = [(t.find(b), b) for b in BRANDS if re.search(rf"\b{re.escape(b)}\b", t)]
    return min(hits)[1] if hits else None


def _spec_contradictions(description: str, specs: dict) -> list[str]:
    desc = normalize(description)
    out = []
    m = re.search(r"(\d+)\s+cordas", desc)
    if m and "strings" in specs and str(specs["strings"]).isdigit() and m.group(1) != str(specs["strings"]):
        out.append(f"descrição diz {m.group(1)} cordas, specs dizem {specs['strings']}")
    m = re.search(r"(\d+)\s+teclas", desc)
    if m and "keys" in specs and m.group(1) != str(specs["keys"]):
        out.append(f"descrição diz {m.group(1)} teclas, specs dizem {specs['keys']}")
    for key in ("shells", "body"):
        spec_wood = normalize(str(specs.get(key, "")))
        desc_woods = {w for w in WOODS if re.search(rf"\b{w}\b", desc)}
        if spec_wood and desc_woods and not any(w in spec_wood for w in desc_woods):
            out.append(f"descrição cita {', '.join(sorted(desc_woods))}, specs dizem {specs[key]}")
    return out


def check_products(products: list[dict]) -> dict[int, ProductCheck]:
    by_cat: dict[int, list[float]] = defaultdict(list)
    for p in products:
        by_cat[int(p["category_id"])].append(float(p["price_brl"]))
    medians = {c: median(v) for c, v in by_cat.items()}

    results = {}
    for p in products:
        pid = int(p["product_id"])
        chk = ProductCheck(pid)
        specs = json.loads(p["specs"]) if p.get("specs") else {}
        name_brand = _name_brand(p["name"])
        desc_brands = _brands_in(p["description"])
        if desc_brands and name_brand and name_brand not in desc_brands:
            chk.reasons.append(
                f"marca do nome ({name_brand}) difere da descrição ({', '.join(sorted(desc_brands))})"
            )
        if GENERIC_NAME.search(p["name"]):
            chk.reasons.append("nome no padrão genérico de cadastro automático")
        chk.reasons.extend(_spec_contradictions(p["description"], specs))
        # Preço atípico só reforça um cadastro já suspeito: sozinho, pode ser
        # apenas um produto de entrada legítimo.
        if chk.reasons and float(p["price_brl"]) < ATYPICAL_PRICE_RATIO * medians[int(p["category_id"])]:
            chk.reasons.append("preço atípico para a categoria")
        results[pid] = chk
    return results


def full_report(tables: dict[str, list[dict]]) -> list[str]:
    """Relatório legível de todos os problemas encontrados nos dados brutos."""
    products, orders = tables["products"], tables["orders"]
    items, promos, customers = tables["order_items"], tables["promotions"], tables["customers"]
    prod_by_id = {int(p["product_id"]): p for p in products}
    lines = []

    for pid, chk in sorted(check_products(products).items()):
        if chk.flagged:
            lines.append(f"[produto {pid}] {FLAG_REVIEW}: " + "; ".join(chk.reasons))

    for p in products:
        if p["status"] == "discontinued" and int(p["stock_quantity"]) > 0:
            lines.append(f"[produto {p['product_id']}] descontinuado com {p['stock_quantity']} unidades em estoque")
        if p["status"] == "active" and int(p["stock_quantity"]) == 0:
            lines.append(f"[produto {p['product_id']}] ativo com estoque zero")

    status_by_order = {int(o["order_id"]): o["status"] for o in orders}
    for it in items:
        p = prod_by_id[int(it["product_id"])]
        if p["status"] == "coming_soon" and status_by_order[int(it["order_id"])] == "delivered":
            lines.append(f"[pedido {it['order_id']}] entregue com produto {p['product_id']} marcado como coming_soon")

    sums: dict[int, float] = defaultdict(float)
    for it in items:
        sums[int(it["order_id"])] += int(it["quantity"]) * float(prod_by_id[int(it["product_id"])]["price_brl"])
    for o in orders:
        oid = int(o["order_id"])
        if abs(sums[oid] - float(o["total_brl"])) > 0.005:
            lines.append(f"[pedido {oid}] total gravado {o['total_brl']} difere da soma dos itens {sums[oid]:.2f}")

    for pid, n in Counter(int(p["product_id"]) for p in promos).items():
        if n > 1:
            lines.append(f"[promoções] produto {pid} tem {n} promoções cadastradas")

    for email, n in Counter(normalize(c["email"]) for c in customers).items():
        if n > 1:
            ids = [c["customer_id"] for c in customers if normalize(c["email"]) == email]
            lines.append(f"[clientes] e-mail {email} compartilhado pelos clientes {', '.join(ids)}")
    return lines


if __name__ == "__main__":
    from .ingest import read_raw

    for line in full_report(read_raw()):
        print(line)
