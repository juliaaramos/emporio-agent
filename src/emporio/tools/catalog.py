"""Catálogo: busca, detalhe, disponibilidade e promoções."""
from __future__ import annotations

import difflib
import json
from decimal import Decimal

from .. import db
from ..text import brl, money, normalize, tokens

# Sinônimos -> category_id. Permite "violão", "guitarra elétrica", "piano" etc.
CATEGORY_WORDS = {
    "guitarra": 1, "guitarras": 1,
    "baixo": 2, "baixos": 2, "contrabaixo": 2, "contrabaixos": 2,
    "bateria": 3, "baterias": 3, "percussao": 3,
    "teclado": 4, "teclados": 4, "piano": 4, "pianos": 4, "sintetizador": 4, "synth": 4,
    "violao": 5, "violoes": 5,
    "sopro": 6, "flauta": 6, "clarinete": 6, "saxofone": 6, "sax": 6, "oboe": 6,
    "trompete": 7, "trombone": 7, "tuba": 7, "trompa": 7,
    "violino": 8, "viola": 8, "violoncelo": 8, "cello": 8,
    "ukulele": 9, "ukuleles": 9, "uke": 9,
}
LOW_STOCK = 2
STOPWORDS = {"de", "da", "do", "o", "a", "os", "as", "um", "uma", "e", "com", "para", "em", "modelo"}

AVAILABILITY_LABEL = {
    "disponivel": "disponível",
    "sem_estoque": "temporariamente sem estoque",
    "descontinuado": "descontinuado (não faz mais parte do catálogo)",
    "em_breve": "em breve (ainda não disponível para venda)",
}
REVIEW_NOTE = (
    "Cadastro em revisão: informe apenas nome, preço e disponibilidade. Não afirme "
    "especificações, marca de componentes nem descrição; diga que a equipe vai confirmar os detalhes."
)


def availability(status: str, stock: int) -> str:
    """Status e estoque juntos (§7.3): descontinuado nunca é oferecido, mesmo com estoque."""
    if status == "discontinued":
        return "descontinuado"
    if status == "coming_soon":
        return "em_breve"
    return "disponivel" if (stock or 0) > 0 else "sem_estoque"


def active_promotion(product_id: int) -> dict | None:
    """Só vale promoção com is_active=1; se houver mais de uma, a de maior desconto."""
    return db.query_one(
        "SELECT * FROM promotions WHERE product_id=? AND is_active=1 "
        "ORDER BY discount_percent DESC LIMIT 1",
        (product_id,),
    )


def inactive_promotions(product_id: int) -> list[str]:
    rows = db.query(
        "SELECT description, discount_percent FROM promotions WHERE product_id=? AND is_active=0",
        (product_id,),
    )
    seen, out = set(), []
    for r in rows:
        label = f"{r['description']} ({r['discount_percent']:g}%)"
        if label not in seen:
            seen.add(label)
            out.append(label)
    return out


def price_info(product: dict) -> dict:
    original = money(product["price_brl"])
    promo = active_promotion(product["product_id"])
    if promo:
        pct = Decimal(str(promo["discount_percent"]))
        final = money(original * (Decimal(100) - pct) / Decimal(100))
        return {
            "preco_original": brl(original),
            "promocao": {"nome": promo["description"], "desconto_percentual": float(pct)},
            "preco_atual": brl(final),
            "_preco_atual": final,
        }
    return {"preco_original": brl(original), "promocao": None, "preco_atual": brl(original), "_preco_atual": original}


def get_product(product_id: int) -> dict | None:
    return db.query_one(
        "SELECT p.*, c.name AS categoria FROM products p JOIN categories c USING (category_id) "
        "WHERE product_id=?",
        (int(product_id),),
    )


def _summary(p: dict) -> dict:
    info = price_info(p)
    avail = availability(p["status"], p["stock_quantity"])
    out = {
        "product_id": p["product_id"],
        "nome": p["name"],
        "categoria": p["categoria"],
        "preco_original": info["preco_original"],
        "preco_atual": info["preco_atual"],
        "promocao": info["promocao"],
        "disponibilidade": AVAILABILITY_LABEL[avail],
    }
    # A quantidade exata não vai para o modelo (nem para o cliente): basta saber se há
    # e se são as últimas unidades. A checagem de quantidade fica em calcular_pagamento.
    if avail == "disponivel" and p["stock_quantity"] <= LOW_STOCK:
        out["ultimas_unidades"] = True
    encerradas = inactive_promotions(p["product_id"])
    if encerradas:  # permite responder "aquela promoção ainda vale?" com base no sistema
        out["promocoes_encerradas"] = encerradas
    if p["data_quality_flag"]:
        out["alerta_cadastro"] = REVIEW_NOTE
    return out


def _resolve_category(categoria: str | None) -> int | None:
    if not categoria:
        return None
    key = normalize(categoria)
    if key in CATEGORY_WORDS:
        return CATEGORY_WORDS[key]
    for row in db.query("SELECT category_id, name FROM categories"):
        if key in normalize(row["name"]):
            return row["category_id"]
    return None


def buscar_produtos(
    texto: str | None = None,
    categoria: str | None = None,
    preco_max: float | None = None,
    preco_min: float | None = None,
    so_disponiveis: bool = False,
    limite: int = 15,
) -> dict:
    out = _buscar(texto, categoria, preco_max, preco_min, so_disponiveis, limite)
    # O modelo às vezes chuta a categoria errada ("Takamine GD20" como guitarra).
    # Com texto e sem resultado, tenta de novo sem a categoria.
    if texto and categoria and not out.get("erro") and out["total_encontrado"] == 0:
        retry = _buscar(texto, None, preco_max, preco_min, so_disponiveis, limite)
        if retry["total_encontrado"]:
            retry["observacao_categoria"] = (
                f"Nada encontrado na categoria '{categoria}'; estes resultados são de outras categorias."
            )
            return retry
    return out


def _buscar(texto, categoria, preco_max, preco_min, so_disponiveis, limite) -> dict:
    cat_id = _resolve_category(categoria)
    if categoria and cat_id is None:
        cats = [r["name"] for r in db.query("SELECT name FROM categories")]
        return {"erro": f"Categoria '{categoria}' não reconhecida.", "categorias_validas": cats}

    query_tokens = [t for t in tokens(texto) if t not in STOPWORDS]
    # Uma palavra de categoria no texto ("violão Yamaha") vira filtro de categoria.
    if cat_id is None:
        for t in query_tokens:
            if t in CATEGORY_WORDS:
                cat_id = CATEGORY_WORDS[t]
                break
    if cat_id is not None:
        query_tokens = [t for t in query_tokens if CATEGORY_WORDS.get(t) != cat_id]

    sql = "SELECT p.*, c.name AS categoria FROM products p JOIN categories c USING (category_id)"
    params: tuple = ()
    if cat_id is not None:
        sql += " WHERE p.category_id=?"
        params = (cat_id,)
    rows = db.query(sql, params)

    def haystack(p: dict) -> str:
        parts = [p["name"], p["categoria"]]
        # Descrição de cadastro em revisão não é confiável para busca.
        if not p["data_quality_flag"]:
            parts.append(p["description"])
        text = " ".join(normalize(x) for x in parts)
        return text + " " + text.replace("-", "")  # "d28" encontra "D-28"

    matched = [p for p in rows if all(t in haystack(p) for t in query_tokens)]
    fuzzy_used = False
    if query_tokens and not matched:
        names = {normalize(p["name"]): p for p in rows}
        close = difflib.get_close_matches(" ".join(query_tokens), list(names), n=5, cutoff=0.45)
        if not close:  # tenta palavra a palavra (ex.: "takamini")
            for t in query_tokens:
                for n in names:
                    if difflib.get_close_matches(t, n.split(), n=1, cutoff=0.75):
                        close.append(n)
        matched = [names[n] for n in dict.fromkeys(close)]
        fuzzy_used = bool(matched)

    results = []
    for p in matched:
        s = _summary(p)
        price = price_info(p)["_preco_atual"]
        if preco_max is not None and price > Decimal(str(preco_max)):
            continue
        if preco_min is not None and price < Decimal(str(preco_min)):
            continue
        if so_disponiveis and s["disponibilidade"] != AVAILABILITY_LABEL["disponivel"]:
            continue
        results.append((price, s))
    results.sort(key=lambda x: x[0])

    out: dict = {"total_encontrado": len(results), "produtos": [s for _, s in results[:limite]]}
    if len(results) > limite:
        out["observacao"] = f"Mostrando {limite} de {len(results)}. Refine a busca se necessário."
    if fuzzy_used:
        out["observacao_busca"] = "Nenhum nome exato; resultados aproximados. Confirme com o cliente."
    if cat_id in (6, 7, 8) and not results:
        out["observacao_catalogo"] = (
            "No momento não há itens desta categoria no sistema. Diga 'no momento não temos "
            "esse tipo de instrumento disponível' (nunca 'não vendemos')."
        )
    return out


def detalhar_produto(product_id: int, quantidade: int | None = None) -> dict:
    p = get_product(product_id)
    if not p:
        return {"erro": f"Produto {product_id} não encontrado."}
    out = _summary(p)
    if quantidade:
        # Responde "tem 3 unidades?" com sim/não, sem revelar o número em estoque.
        q = int(quantidade)
        ok = availability(p["status"], p["stock_quantity"]) == "disponivel" and q <= p["stock_quantity"]
        out["quantidade_solicitada"] = {"quantidade": q, "atende": ok}
    out.setdefault("promocoes_encerradas", [])
    if p["data_quality_flag"]:
        out["descricao"] = None
        out["especificacoes"] = None
    else:
        out["descricao"] = p["description"]
        out["especificacoes"] = json.loads(p["specs"]) if p["specs"] else {}
    avail = availability(p["status"], p["stock_quantity"])
    if avail != "disponivel":
        out["sugestao"] = (
            "Ofereça alternativas disponíveis da mesma categoria e faixa de preço "
            "(use buscar_produtos com so_disponiveis=true)."
        )
    return out


def listar_promocoes_ativas(categoria: str | None = None) -> dict:
    cat_id = _resolve_category(categoria)
    if categoria and cat_id is None:
        cats = [r["name"] for r in db.query("SELECT name FROM categories")]
        return {"erro": f"Categoria '{categoria}' não reconhecida.", "categorias_validas": cats}
    sql = (
        "SELECT DISTINCT p.product_id FROM promotions pr JOIN products p USING (product_id) "
        "WHERE pr.is_active=1"
    )
    params: tuple = ()
    if cat_id is not None:
        sql += " AND p.category_id=?"
        params = (cat_id,)
    rows = db.query(sql + " ORDER BY p.product_id", params)
    produtos = [_summary(get_product(r["product_id"])) for r in rows]
    return {
        "promocoes_ativas": produtos,
        "observacao": "Somente estas promoções estão vigentes no sistema. Campanhas do calendário "
        "(ex.: Black Friday) só valem se aparecerem aqui.",
    }
