"""Pagamento e frete. Recebe só códigos e quantidades: preços vêm do sistema, nunca do modelo."""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from ..config import METRO_CITIES
from ..text import brl, money, normalize
from .catalog import AVAILABILITY_LABEL, availability, get_product, price_info

PIX_DISCOUNT = Decimal("0.05")
COMBINED_MIN = Decimal("2000")
FREE_SHIPPING_FROM = Decimal("500")
METRO_FEE = Decimal("35")
FORMAS = ("pix", "debito", "credito", "boleto")


def min_installment(n: int) -> Decimal:
    """§3.1. Leitura de 'sem valor mínimo (exceto abaixo de R$ 50,00)': parcela >= R$ 50 até 3x."""
    if n <= 3:
        return Decimal("50")
    if n <= 6:
        return Decimal("80")
    return Decimal("100")


def split_installments(total: Decimal, n: int) -> list[Decimal]:
    """Parcelas com centavos truncados; a última absorve a diferença."""
    base = (total / n).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    return [base] * (n - 1) + [money(total - base * (n - 1))]


def max_installments(total: Decimal) -> int:
    best = 1
    for n in range(2, 13):
        if split_installments(total, n)[0] >= min_installment(n):
            best = n
    return best


def _describe(parts: list[Decimal]) -> str:
    n = len(parts)
    if n == 1:
        return f"1x de {brl(parts[0])}"
    if parts[-1] == parts[0]:
        return f"{n}x de {brl(parts[0])}"
    return f"{n - 1}x de {brl(parts[0])} + 1x de {brl(parts[-1])}"


def _resolve_items(itens: list[dict]) -> tuple[list[dict], list[str]]:
    lines, errors = [], []
    for it in itens or []:
        pid, qty = it.get("product_id"), int(it.get("quantidade", 1) or 1)
        p = get_product(pid) if pid is not None else None
        if not p:
            errors.append(f"Produto {pid} não encontrado.")
            continue
        avail = availability(p["status"], p["stock_quantity"])
        if avail != "disponivel":
            errors.append(f"{p['name']} está {AVAILABILITY_LABEL[avail]} e não pode ser orçado.")
            continue
        if qty > p["stock_quantity"]:
            errors.append(f"{p['name']}: não há {qty} unidades disponíveis (a quantidade exata em estoque não é divulgada).")
            continue
        info = price_info(p)
        lines.append({"p": p, "qty": qty, "info": info, "unit": info["_preco_atual"]})
    return lines, errors


def calcular_pagamento(itens: list[dict], forma: str | None = None, parcelas: int | None = None) -> dict:
    lines, errors = _resolve_items(itens)
    if errors:
        return {"erro": " ".join(errors)}
    if not lines:
        return {"erro": "Informe ao menos um product_id."}

    subtotal = sum((l["unit"] * l["qty"] for l in lines), Decimal(0))
    # PIX: 5% sobre o preço de tabela, só em itens SEM promoção (§6.2: não cumulativo).
    pix_total = sum(
        (money(l["unit"] * (1 - PIX_DISCOUNT)) * l["qty"] if not l["info"]["promocao"] else l["unit"] * l["qty"]
         for l in lines),
        Decimal(0),
    )
    itens_out = [
        {
            "product_id": l["p"]["product_id"],
            "nome": l["p"]["name"],
            "quantidade": l["qty"],
            "preco_original": l["info"]["preco_original"],
            "promocao": l["info"]["promocao"],
            "preco_unitario": brl(l["unit"]),
        }
        for l in lines
    ]
    any_promo = any(l["info"]["promocao"] for l in lines)
    max_n = max_installments(subtotal)
    out: dict = {
        "itens": itens_out,
        "total_a_vista": brl(subtotal),
        "pagamento_combinado_permitido": subtotal > COMBINED_MIN,
    }
    regra_pix = (
        "Desconto PIX não se aplica a itens em promoção (§6.2)." if any_promo else "PIX tem 5% de desconto (§3)."
    )

    if forma is None:
        out["opcoes"] = {
            "pix": brl(pix_total),
            "debito": brl(subtotal),
            "boleto": brl(subtotal),
            "credito_max_parcelas": _describe(split_installments(subtotal, max_n)) + " sem juros",
        }
        out["regras"] = regra_pix
        return out

    forma = normalize(forma)
    if forma not in FORMAS:
        return {"erro": f"Forma de pagamento inválida. Use uma de: {', '.join(FORMAS)}."}
    if forma == "pix":
        out.update(forma="pix", total=brl(pix_total), regras=regra_pix)
    elif forma in ("debito", "boleto"):
        out.update(forma=forma, total=brl(subtotal))
        if forma == "boleto":
            out["regras"] = "Compensação em até 3 dias úteis (§3)."
    else:
        n = int(parcelas or 1)
        if not 1 <= n <= 12:
            return {"erro": "Parcelamento de 1x a 12x."}
        parts = split_installments(subtotal, n)
        if n > 1 and parts[0] < min_installment(n):
            return {
                "erro": f"Em {n}x a parcela ficaria abaixo do mínimo de {brl(min_installment(n))} (§3.1).",
                "maximo_parcelas_permitido": max_n,
                "opcao_maxima": _describe(split_installments(subtotal, max_n)) + " sem juros",
            }
        out.update(
            forma="credito",
            total=brl(subtotal),
            parcelas=_describe(parts) + " sem juros",
            regras="Até 3x: parcela mínima R$ 50; 4x a 6x: R$ 80; 7x a 12x: R$ 100 (§3.1).",
        )
    return out


def calcular_frete(itens: list[dict], cidade: str) -> dict:
    lines, errors = _resolve_items(itens)
    if errors:
        return {"erro": " ".join(errors)}
    if not lines:
        return {"erro": "Informe ao menos um product_id."}
    subtotal = sum((l["unit"] * l["qty"] for l in lines), Decimal(0))
    if normalize(cidade) in METRO_CITIES:
        # "acima de 500" grátis / "abaixo de 500" R$ 35: exatamente R$ 500 fica grátis (a favor do cliente).
        fee = Decimal(0) if subtotal >= FREE_SHIPPING_FROM else METRO_FEE
        return {
            "cidade": cidade,
            "regiao": "Região metropolitana de Campo Grande (§5.1)",
            "valor_pedido": brl(subtotal),
            "frete": "grátis" if fee == 0 else brl(fee),
            "prazo": "1 a 3 dias úteis, por motoboy próprio (a loja liga antes da entrega)",
        }
    big = [l["p"]["name"] for l in lines if l["p"]["category_id"] in (2, 3, 4)]
    out = {
        "cidade": cidade,
        "regiao": "Outras cidades (§5.2)",
        "valor_frete": "Depende de cotação pelo CEP de destino, peso e dimensões. Peça o CEP e "
        "informe que um atendente envia a cotação.",
        "modalidades": [
            {"nome": "PAC (Correios)", "prazo": "5 a 12 dias úteis"},
            {"nome": "SEDEX (Correios)", "prazo": "2 a 5 dias úteis"},
            {"nome": "Jadlog (.package)", "prazo": "3 a 8 dias úteis"},
        ],
        "observacao": "Todas com rastreamento e seguro incluído.",
    }
    if big:
        out["frete_especial"] = (
            f"Instrumentos de grande porte ({', '.join(big)}) podem exigir frete especial com cotação individual."
        )
    return out
