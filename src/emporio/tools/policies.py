"""Consulta de políticas por seção (lista fechada), devolvendo o texto exato do manual."""
from __future__ import annotations

import re
from functools import lru_cache

from ..config import POLICIES_MD

# Notas de interpretação para conflitos internos do manual. São separadas do texto
# original para que o agente cite o manual fielmente e explique a regra aplicada.
NOTES = {
    "1": "A base atual não tem instrumentos de sopro nem cordas orquestrais. Diga 'no momento não "
    "temos esse tipo de instrumento disponível', nunca 'não vendemos'.",
    "1.2": "Contatos válidos: telefone (67) 3341-4444, WhatsApp (67) 3321-4500 (§7) e e-mail "
    "contato@emporiodamusica.com.br (sem acento).",
    "3": "As faixas do §3.1 prevalecem sobre a 'parcela mínima de R$ 100,00' da tabela. Valores sempre "
    "via calcular_pagamento.",
    "3.1": "Interpretação: até 3x, parcela mínima de R$ 50,00. Valores sempre via calcular_pagamento.",
    "4.2": "Conflito com §8.1: a garantia legal é de 90 dias a partir do recebimento. A loja atende "
    "defeito pelo maior dos dois prazos; prazos de um pedido específico via avaliar_devolucao.",
    "4.3": "Interpretação: os 7 dias contam a partir do recebimento.",
    "6.1": "Campanhas do calendário só valem se estiverem ativas no sistema (listar_promocoes_ativas).",
    "8.1": "Prazos de um pedido específico via avaliar_devolucao.",
}


@lru_cache(maxsize=1)
def load_sections() -> dict[str, dict]:
    text = POLICIES_MD.read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    sections = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        header, _, body = block.partition("\n")
        num, _, title = header.strip().partition(" ")
        sections[num] = {"titulo": title.strip(), "texto": body.strip()}
    return sections


def section_catalog() -> str:
    return "; ".join(f"{k} = {v['titulo']}" for k, v in load_sections().items())


def consultar_politica(secao: str) -> dict:
    secao = str(secao).strip().lstrip("§")
    sections = load_sections()
    if secao not in sections:
        return {"erro": f"Seção '{secao}' não existe.", "secoes_validas": list(sections)}
    s = sections[secao]
    out = {"secao": f"§{secao} {s['titulo']}", "texto": s["texto"]}
    if secao in NOTES:
        out["nota_de_interpretacao"] = NOTES[secao]
    return out
