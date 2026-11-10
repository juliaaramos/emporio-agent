"""Clientes e pedidos. A checagem de identidade e de posse do pedido é feita aqui, no
código, nunca pelo modelo. As respostas expõem o mínimo de dado pessoal (LGPD)."""
from __future__ import annotations

from datetime import date, timedelta

from .. import db
from ..config import today
from ..session import MAX_VERIFY_ATTEMPTS, SessionState
from ..text import brl, digits, normalize

STATUS_LABEL = {
    "pending": "aguardando confirmação de pagamento",
    "confirmed": "pagamento confirmado, em preparação para envio",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}
PAYMENT_LABEL = {"pix": "PIX", "debit": "cartão de débito", "boleto": "boleto"}
NOT_VERIFIED = {
    "erro": "cliente_nao_verificado",
    "instrucao": "Peça o e-mail do cadastro e o número de um pedido OU os 4 últimos dígitos do "
    "telefone, e chame verificar_cliente.",
}
NOT_FOUND = {"erro": "Não encontrei esse pedido no seu cadastro. Confira o número, por favor."}


def _payment_label(code: str) -> str:
    if code and code.startswith("credit_"):
        return f"cartão de crédito em {code.split('_')[1]}"
    return PAYMENT_LABEL.get(code, code)


def _br_date(iso: str | None) -> str | None:
    return date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else None


def verificar_cliente(
    state: SessionState, email: str, order_id: int | None = None, final_telefone: str | None = None
) -> dict:
    if state.failed_verifications >= MAX_VERIFY_ATTEMPTS:
        return {
            "verificado": False,
            "erro": "Limite de tentativas atingido nesta conversa. Ofereça encaminhar a um atendente.",
        }
    if not order_id and not final_telefone:
        return {"verificado": False, "erro": "Além do e-mail, peça o número de um pedido ou os 4 últimos dígitos do telefone."}

    candidates = db.query("SELECT * FROM customers WHERE lower(email)=?", (normalize(email),))
    matches = []
    for c in candidates:
        ok = True
        if order_id:
            ok &= db.query_one(
                "SELECT 1 FROM orders WHERE order_id=? AND customer_id=?", (int(order_id), c["customer_id"])
            ) is not None
        if final_telefone:
            tail = digits(final_telefone)
            ok &= len(tail) >= 4 and digits(c["phone"]).endswith(tail[-4:])
        if ok:
            matches.append(c)

    if len(matches) != 1:
        state.failed_verifications += 1
        # Mensagem genérica: não revela se o e-mail existe (evita enumeração).
        return {
            "verificado": False,
            "erro": "Não consegui confirmar os dados. Peça para o cliente conferir.",
            "tentativas_restantes": MAX_VERIFY_ATTEMPTS - state.failed_verifications,
        }
    state.verified_customer_id = matches[0]["customer_id"]
    state.failed_verifications = 0
    return {"verificado": True, "primeiro_nome": matches[0]["name"].split()[0]}


def _own_order(state: SessionState, order_id: int) -> dict | None:
    return db.query_one(
        "SELECT * FROM orders WHERE order_id=? AND customer_id=?", (int(order_id), state.verified_customer_id)
    )


def _items(order_id: int) -> list[dict]:
    return [
        {"product_id": r["product_id"], "nome": r["name"], "quantidade": r["quantity"]}
        for r in db.query(
            "SELECT oi.product_id, oi.quantity, p.name FROM order_items oi JOIN products p USING (product_id) "
            "WHERE order_id=?",
            (order_id,),
        )
    ]


def listar_pedidos_do_cliente(state: SessionState) -> dict:
    if not state.verified_customer_id:
        return NOT_VERIFIED
    rows = db.query(
        "SELECT order_id, order_date, status FROM orders WHERE customer_id=? ORDER BY order_date DESC",
        (state.verified_customer_id,),
    )
    return {
        "pedidos": [
            {"order_id": r["order_id"], "data": _br_date(r["order_date"]), "status": STATUS_LABEL[r["status"]],
             "itens": [i["nome"] for i in _items(r["order_id"])]}
            for r in rows
        ]
    }


def consultar_pedido(state: SessionState, order_id: int) -> dict:
    if not state.verified_customer_id:
        return NOT_VERIFIED
    o = _own_order(state, order_id)
    if not o:
        return NOT_FOUND
    hoje = today()
    out = {
        "order_id": o["order_id"],
        # Só existe a data da compra; a data de despacho não é registrada no sistema.
        "data_da_compra": _br_date(o["order_date"]),
        "data_de_envio": "não registrada no sistema (não informe)",
        "status": STATUS_LABEL[o["status"]],
        "itens": _items(o["order_id"]),
        # Total gravado no pedido, sem recalcular (pedidos 3 e 20 divergem da soma dos itens).
        "total": brl(o["total_brl"]),
        "pagamento": _payment_label(o["payment_method"]),
    }
    if o["tracking_code"]:
        out["codigo_rastreio"] = o["tracking_code"]
        out["rastreio"] = "Consultar no site dos Correios ou da Jadlog (§5.3)."
    if o["estimated_delivery"]:
        out["previsao_entrega"] = _br_date(o["estimated_delivery"])
        if o["status"] == "shipped" and date.fromisoformat(o["estimated_delivery"]) < hoje:
            dias = (hoje - date.fromisoformat(o["estimated_delivery"])).days
            out["atrasado"] = True
            out["dias_de_atraso"] = dias
            out["instrucao"] = (
                "Peça desculpas e PERGUNTE se a pessoa quer que você abra um chamado (categoria "
                "'atraso'). Só chame encaminhar_humano depois do sim. O retorno é em até 24 horas úteis (§7.3)."
            )
    if o["notes"]:
        out["observacao"] = o["notes"]
    if o["status"] in ("pending", "confirmed"):
        out["observacao_envio"] = "O código de rastreio é enviado por e-mail e WhatsApp assim que o pedido é despachado (§5.3)."
    return out


def avaliar_devolucao(state: SessionState, order_id: int) -> dict:
    """Calcula em código todos os prazos de arrependimento, troca e garantia de um pedido."""
    if not state.verified_customer_id:
        return NOT_VERIFIED
    o = _own_order(state, order_id)
    if not o:
        return NOT_FOUND
    hoje = today()
    base = {"order_id": o["order_id"], "hoje": hoje.strftime("%d/%m/%Y"), "status": STATUS_LABEL[o["status"]]}

    if o["status"] == "cancelled":
        return {**base, "conclusao": "Pedido cancelado; não há devolução a fazer.", "observacao": o["notes"]}
    if o["status"] == "shipped":
        return {
            **base,
            "conclusao": "O produto ainda não foi recebido, então o prazo de 7 dias de arrependimento (§4.1) "
            "ainda nem começou: ele conta a partir do recebimento.",
            "atrasado": bool(o["estimated_delivery"] and date.fromisoformat(o["estimated_delivery"]) < hoje),
        }
    if o["status"] in ("pending", "confirmed"):
        return {
            **base,
            "conclusao": "Pedido ainda não enviado. O manual não trata de cancelamento antes do envio: "
            "encaminhe a um atendente (encaminhar_humano, categoria 'devolucao').",
        }

    # Entregue. Sem data real de recebimento, usamos a previsão de entrega como aproximação.
    recebimento = date.fromisoformat(o["estimated_delivery"] or o["order_date"])
    compra = date.fromisoformat(o["order_date"])
    online = bool(o["tracking_code"])
    arrependimento_ate = recebimento + timedelta(days=7)
    preferencia_ate = recebimento + timedelta(days=7)
    defeito_30d_ate = compra + timedelta(days=30)
    garantia_legal_ate = recebimento + timedelta(days=90)
    # Regra mais protetiva: a loja atende defeito enquanto valer qualquer um dos dois prazos.
    defeito_loja_ate = max(defeito_30d_ate, garantia_legal_ate)

    def janela(ate: date, aplica: bool = True) -> dict:
        if not aplica:
            return {"elegivel": False, "motivo": "Só vale para compras online."}
        ok, d = hoje <= ate, ate.strftime("%d/%m/%Y")
        # Frase pronta, no tempo verbal certo, para o modelo não reescrever o prazo.
        return {"elegivel": ok, "prazo_ate": d, "situacao": f"vale até {d}" if ok else f"terminou em {d}"}

    arrep, pref, defeito = janela(arrependimento_ate, online), janela(preferencia_ate), janela(defeito_loja_ate)
    # Próximo passo decidido no código, para o modelo não misturar caminhos encerrados e abertos.
    if arrep["elegivel"] or pref["elegivel"]:
        proximo = "A devolução/troca ainda está no prazo: explique as condições e ofereça encaminhar (categoria 'devolucao')."
    elif defeito["elegivel"]:
        proximo = ("Arrependimento e troca encerrados. Diga isso e pergunte se há defeito; se houver, "
                   "a loja ainda atende (abra chamado categoria 'defeito' após o sim).")
    else:
        proximo = ("Arrependimento, troca e garantia legal encerrados. Agora: diga que o arrependimento terminou e "
                   "pergunte se há defeito, sem falar ainda de garantia legal. Se houver defeito: diga que a garantia "
                   "legal terminou, que vale a do fabricante (§8.2) e que a loja pode intermediar (§4.2).")
    return {
        **base,
        "proximo_passo": proximo,
        "data_recebimento_considerada": recebimento.strftime("%d/%m/%Y"),
        "data_recebimento_e_estimativa": True,
        "compra_online": online,
        "arrependimento_7_dias_secao_4_1": arrep,
        "troca_por_preferencia_7_dias_secao_4_3": pref,
        "defeito_atendido_pela_loja": {
            **defeito,
            "regra": "Maior prazo entre 30 dias da compra (§4.2) e 90 dias de garantia legal desde o "
            "recebimento (§8.1). Depois disso vale a garantia do fabricante (§8.2), com intermediação "
            "da loja se o cliente pedir (§4.2).",
            "garantia_legal_ate": garantia_legal_ate.strftime("%d/%m/%Y"),
            "garantia_legal_situacao": (
                f"{'vale até' if hoje <= garantia_legal_ate else 'terminou em'} "
                f"{garantia_legal_ate.strftime('%d/%m/%Y')}"
            ),
        },
        "condicoes": "Arrependimento/preferência: embalagem original, sem uso, com acessórios e manuais. "
        "Mau uso, quedas, umidade e modificações não são cobertos (§4.2, §8.3).",
        "secoes_para_citar": ["4.1", "4.2", "4.3", "8.1", "8.2"],
    }
