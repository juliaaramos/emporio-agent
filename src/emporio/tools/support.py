"""Encaminhamento para atendimento humano (§7.3, §10)."""
from __future__ import annotations

from ..session import SessionState, Store
from .customers import consultar_pedido

CATEGORIAS = ["reclamacao", "defeito", "atraso", "devolucao", "duvida_politica", "cotacao_frete", "outro"]


def _order_facts(state: SessionState, order_id: int) -> str | None:
    """Fatos do pedido montados pelo código, para o resumo do chamado não depender do modelo."""
    o = consultar_pedido(state, order_id)
    if "erro" in o:  # sem verificação ou pedido de outro cliente: não anexa nada
        return None
    facts = [f"Pedido {o['order_id']}", f"compra em {o['data_da_compra']}", f"status {o['status']}"]
    if "previsao_entrega" in o:
        facts.append(f"previsão de entrega {o['previsao_entrega']}")
    if o.get("atrasado"):
        facts.append(f"{o['dias_de_atraso']} dias de atraso")
    if "codigo_rastreio" in o:
        facts.append(f"rastreio {o['codigo_rastreio']}")
    return ", ".join(facts) + "."


def encaminhar_humano(
    state: SessionState, store: Store, categoria: str, resumo: str, order_id: int | None = None
) -> dict:
    if categoria not in CATEGORIAS:
        categoria = "outro"
    facts = _order_facts(state, order_id) if order_id else None
    if order_id and not facts:
        order_id = None
    if order_id and (existente := store.open_ticket_for(state.session_id, order_id)):
        return {
            "protocolo": existente,
            "chamado_ja_existente": True,
            "mensagem_para_cliente": f"Já existe um chamado aberto para esse pedido, com o protocolo {existente}. "
            "A equipe retorna em até 24 horas úteis.",
            "instrucao": "Não abra outro chamado. Use a mensagem_para_cliente como está.",
        }
    texto = f"Dados do sistema: {facts} Relato do cliente: {resumo}" if facts else f"Relato do cliente: {resumo}"
    protocolo = store.open_ticket(state.session_id, state.verified_customer_id, order_id, categoria, texto[:800])
    return {
        "protocolo": protocolo,
        "prazo_retorno": "até 24 horas úteis (§7.3)",
        "mensagem_para_cliente": f"Chamado aberto com o protocolo {protocolo}. A equipe retorna em até 24 horas úteis.",
        "instrucao": "Use a mensagem_para_cliente como está. Não prometa solução específica em nome da equipe.",
    }
