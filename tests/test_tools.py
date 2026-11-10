from datetime import datetime
from decimal import Decimal

import pytest

from emporio.config import TZ
from emporio.tools import ToolContext, dispatch
from emporio.tools.catalog import buscar_produtos, detalhar_produto, listar_promocoes_ativas
from emporio.tools.customers import avaliar_devolucao, consultar_pedido, listar_pedidos_do_cliente, verificar_cliente
from emporio.tools.pricing import calcular_frete, calcular_pagamento, max_installments, split_installments
from emporio.tools.store import info_loja, status_at


# ---------- catálogo ----------
def test_violoes_ate_1000():
    r = buscar_produtos(categoria="violão", preco_max=1000)
    assert r["total_encontrado"] == 14
    disp = {p["product_id"]: p["disponibilidade"] for p in r["produtos"]}
    assert sum(v == "disponível" for v in disp.values()) == 12
    assert disp[96].startswith("temporariamente sem estoque")
    assert disp[113].startswith("descontinuado")


def test_accent_and_typo_insensitive_search():
    assert buscar_produtos(texto="violao")["total_encontrado"] == 35
    r = buscar_produtos(texto="takamini gd20")
    assert [p["product_id"] for p in r["produtos"]] == [95]
    assert "observacao_busca" in r


def test_wrong_category_falls_back_to_text_search():
    r = buscar_produtos(texto="Takamine GD20", categoria="guitarra")
    assert [p["product_id"] for p in r["produtos"]] == [95]
    assert "observacao_categoria" in r
    # sem texto, categoria vazia continua vazia (sopro)
    assert buscar_produtos(categoria="sopro")["total_encontrado"] == 0


def test_exact_stock_is_not_exposed():
    r = buscar_produtos(categoria="violão", preco_max=1000)
    assert all("estoque" not in p for p in r["produtos"])
    assert detalhar_produto(93).get("ultimas_unidades") is True  # Martin D-28: 2 unidades
    assert "ultimas_unidades" not in detalhar_produto(81)  # Yamaha C40: 12 unidades


def test_discontinued_with_stock_is_not_available():
    p = detalhar_produto(136)
    assert p["disponibilidade"].startswith("descontinuado")
    assert "estoque" not in p


def test_coming_soon():
    assert detalhar_produto(130)["disponibilidade"].startswith("em breve")


def test_flagged_product_hides_specs():
    p = detalhar_produto(137)
    assert p["descricao"] is None and p["especificacoes"] is None
    assert "alerta_cadastro" in p
    assert p["preco_atual"] == "R$ 11.445,00"


def test_inactive_promotion_is_exposed_but_not_applied():
    p = detalhar_produto(95)
    assert p["promocao"] is None
    assert p["preco_atual"] == "R$ 2.199,00"
    assert "Oferta Especial (12%)" in p["promocoes_encerradas"]


def test_active_promotions():
    ids = {p["product_id"] for p in listar_promocoes_ativas()["promocoes_ativas"]}
    assert ids == {90, 94, 121, 127}


def test_empty_category_wording():
    r = buscar_produtos(categoria="sopro")
    assert r["total_encontrado"] == 0
    assert "não temos esse tipo" in r["observacao_catalogo"]


# ---------- pagamento ----------
def test_takamine_options():
    r = calcular_pagamento([{"product_id": 95}])
    assert r["opcoes"]["pix"] == "R$ 2.089,05"
    assert r["opcoes"]["credito_max_parcelas"] == "12x de R$ 183,25 sem juros"


def test_taylor_promo_no_pix_stacking_and_rounding():
    pix = calcular_pagamento([{"product_id": 94}], "pix")
    assert pix["total"] == "R$ 5.519,08"
    card = calcular_pagamento([{"product_id": 94}], "credito", 12)
    assert card["parcelas"] == "11x de R$ 459,92 + 1x de R$ 459,96 sem juros"


@pytest.mark.parametrize(
    "total,expected_max",
    [(Decimal("159.90"), 3), (Decimal("149.99"), 2), (Decimal("479"), 5), (Decimal("1199"), 11), (Decimal("1200"), 12)],
)
def test_installment_bands(total, expected_max):
    assert max_installments(total) == expected_max


def test_installments_sum_to_total():
    for total in [Decimal("5519.08"), Decimal("100.01"), Decimal("7499")]:
        for n in range(1, 13):
            assert sum(split_installments(total, n)) == total


def test_below_minimum_installment_is_refused():
    r = calcular_pagamento([{"product_id": 119}], "credito", 4)
    assert "erro" in r and r["maximo_parcelas_permitido"] == 3


def test_cannot_quote_unavailable_products():
    for pid in (96, 113, 130, 136):
        assert "erro" in calcular_pagamento([{"product_id": pid}])


def test_multiple_items_and_combined_payment():
    r = calcular_pagamento([{"product_id": 83, "quantidade": 2}, {"product_id": 94}], "pix")
    # 2 x 429,90 com 5% (408,41 cada) + Taylor em promoção sem PIX
    assert r["total"] == "R$ 6.335,90"
    assert r["pagamento_combinado_permitido"] is True


# ---------- frete ----------
def test_freight_metro():
    assert calcular_frete([{"product_id": 83}], "Campo Grande")["frete"] == "R$ 35,00"
    assert calcular_frete([{"product_id": 81}], "campo grande")["frete"] == "grátis"


def test_freight_other_city_and_big_items():
    r = calcular_frete([{"product_id": 141}], "Dourados")
    assert len(r["modalidades"]) == 3 and "frete_especial" in r


# ---------- clientes e pedidos ----------
def test_order_requires_verification(state):
    assert consultar_pedido(state, 1)["erro"] == "cliente_nao_verificado"
    assert avaliar_devolucao(state, 1)["erro"] == "cliente_nao_verificado"


def test_verify_by_order_and_block_others_orders(state):
    assert verificar_cliente(state, "Pedro.Oliveira@jmail.com ", order_id=1)["verificado"]
    assert state.verified_customer_id == 3
    assert "erro" in consultar_pedido(state, 8)  # pedido da cliente 2
    assert {p["order_id"] for p in listar_pedidos_do_cliente(state)["pedidos"]} == {1, 19}


def test_duplicate_email_resolved_by_phone(state):
    assert verificar_cliente(state, "bruno.martins@jmail.com", final_telefone="2109")["verificado"]
    assert state.verified_customer_id == 11


def test_duplicate_email_resolved_by_order(state):
    assert verificar_cliente(state, "bruno.martins@jmail.com", order_id=10)["verificado"]
    assert state.verified_customer_id == 11


def test_verification_needs_second_factor_and_locks(state):
    assert not verificar_cliente(state, "pedro.oliveira@jmail.com")["verificado"]
    for _ in range(3):
        r = verificar_cliente(state, "pedro.oliveira@jmail.com", order_id=8)
        assert not r["verificado"]
    r = verificar_cliente(state, "pedro.oliveira@jmail.com", order_id=1)
    assert not r["verificado"] and "Limite" in r["erro"]


def test_response_has_no_pii(state):
    r = verificar_cliente(state, "pedro.oliveira@jmail.com", order_id=1)
    assert set(r) == {"verificado", "primeiro_nome"}


def test_recorded_total_is_kept(state):
    verificar_cliente(state, "isabela.moreira@jmail.com", order_id=3)
    assert consultar_pedido(state, 3)["total"] == "R$ 3.450,00"


def test_late_order(state):
    verificar_cliente(state, "anacarol.ferreira@coldmail.com", final_telefone="7821")
    r = consultar_pedido(state, 8)
    assert r["atrasado"] and r["dias_de_atraso"] == 25
    d = avaliar_devolucao(state, 8)
    assert "ainda nem começou" in d["conclusao"]


def test_return_refused_after_deadlines(state):
    verificar_cliente(state, "pedro.oliveira@jmail.com", order_id=1)
    r = avaliar_devolucao(state, 1)
    assert r["arrependimento_7_dias_secao_4_1"] == {
        "elegivel": False, "prazo_ate": "01/11/2025", "situacao": "terminou em 01/11/2025"}
    assert r["defeito_atendido_pela_loja"]["garantia_legal_situacao"] == "terminou em 23/01/2026"
    assert r["defeito_atendido_pela_loja"]["garantia_legal_ate"] == "23/01/2026"
    assert r["defeito_atendido_pela_loja"]["elegivel"] is False


def test_return_accepted_with_other_reference_date(state, monkeypatch):
    monkeypatch.setenv("REFERENCE_DATE", "2025-10-29")
    verificar_cliente(state, "pedro.oliveira@jmail.com", order_id=1)
    r = avaliar_devolucao(state, 1)
    assert r["arrependimento_7_dias_secao_4_1"]["elegivel"] is True
    assert r["defeito_atendido_pela_loja"]["elegivel"] is True


def test_defect_window_uses_the_most_protective_rule(state, monkeypatch):
    # Pedido 5: compra 05/01/2026, recebimento 18/01/2026. 30 dias da compra = 04/02;
    # 90 dias do recebimento = 18/04. Em 25/03 a loja ainda atende o defeito.
    verificar_cliente(state, "rafael.pereira@jmail.com", order_id=5)
    r = avaliar_devolucao(state, 5)
    assert r["defeito_atendido_pela_loja"]["elegivel"] is True
    assert r["defeito_atendido_pela_loja"]["prazo_ate"] == "18/04/2026"


# ---------- loja ----------
def test_store_open_now():
    info = info_loja()
    assert info["aberta_agora"] is True and info["whatsapp"] == "(67) 3321-4500"


@pytest.mark.parametrize(
    "when,aberta,reabre",
    [
        (datetime(2026, 3, 28, 14, 0, tzinfo=TZ), False, "segunda-feira, 30/03, às 09:00"),  # sábado à tarde
        (datetime(2026, 4, 3, 10, 0, tzinfo=TZ), False, "amanhã, 04/04, às 09:00"),  # Sexta-feira Santa
        (datetime(2026, 3, 25, 7, 0, tzinfo=TZ), False, "hoje, 25/03, às 09:00"),
    ],
)
def test_store_hours_and_holidays(when, aberta, reabre):
    st = status_at(when)
    assert st["aberta_agora"] is aberta and st["reabre"] == reabre


# ---------- despacho ----------
def test_dispatch_handles_bad_input(state, store):
    ctx = ToolContext(state, store)
    assert "erro" in dispatch(ctx, "nao_existe", "{}")
    assert "erro" in dispatch(ctx, "detalhar_produto", "{nao é json")
    assert "erro" in dispatch(ctx, "detalhar_produto", '{"x": 1}')


def test_ticket(state, store):
    r = dispatch(ToolContext(state, store), "encaminhar_humano", {"categoria": "atraso", "resumo": "Pedido 8 atrasado"})
    assert r["protocolo"].startswith("EMP-20260325-") and "24 horas úteis" in r["prazo_retorno"]


def test_requested_quantity_is_checked_without_revealing_stock():
    # Martin D-28 tem 2 unidades
    assert detalhar_produto(93, quantidade=2)["quantidade_solicitada"]["atende"] is True
    assert detalhar_produto(93, quantidade=3)["quantidade_solicitada"]["atende"] is False
    assert detalhar_produto(96, quantidade=1)["quantidade_solicitada"]["atende"] is False  # sem estoque
    err = calcular_pagamento([{"product_id": 93, "quantidade": 3}])["erro"]
    assert "3 unidades" in err and " 2 " not in err


def test_active_promotions_by_category():
    ids = {p["product_id"] for p in listar_promocoes_ativas("violão")["promocoes_ativas"]}
    assert ids and all(detalhar_produto(i)["categoria"] == detalhar_produto(94)["categoria"] for i in ids)
    assert "erro" in listar_promocoes_ativas("helicóptero")


def test_ticket_summary_is_built_from_the_order(state, store):
    verificar_cliente(state, "anacarol.ferreira@coldmail.com", final_telefone="7821")
    ctx = ToolContext(state, store)
    r = dispatch(ctx, "encaminhar_humano", {"categoria": "atraso", "resumo": "Pedido não chegou", "order_id": 8})
    row = store.con.execute("SELECT * FROM tickets WHERE protocolo=?", (r["protocolo"],)).fetchone()
    text = " ".join(str(v) for v in row)
    assert "Pedido 8" in text and "25 dias de atraso" in text and "Relato do cliente: Pedido não chegou" in text
    # pedido de outro cliente não é anexado
    r2 = dispatch(ctx, "encaminhar_humano", {"categoria": "outro", "resumo": "x", "order_id": 1})
    row2 = store.con.execute("SELECT * FROM tickets WHERE protocolo=?", (r2["protocolo"],)).fetchone()
    assert "Pedido 1" not in " ".join(str(v) for v in row2)


def test_no_duplicate_ticket_for_same_order(state, store):
    verificar_cliente(state, "anacarol.ferreira@coldmail.com", final_telefone="7821")
    ctx = ToolContext(state, store)
    a = dispatch(ctx, "encaminhar_humano", {"categoria": "atraso", "resumo": "não chegou", "order_id": 8})
    b = dispatch(ctx, "encaminhar_humano", {"categoria": "reclamacao", "resumo": "reclama", "order_id": 8})
    assert b["protocolo"] == a["protocolo"] and b["chamado_ja_existente"] is True
