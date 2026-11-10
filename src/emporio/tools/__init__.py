"""Registro das ferramentas: schemas (formato OpenAI) e despacho.

O estado da sessão (cliente verificado) é injetado aqui, fora do alcance do modelo:
o modelo não consegue passar um customer_id para ver dados de outra pessoa.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from ..session import SessionState, Store
from . import catalog, customers, policies, pricing, store as store_tools, support


@dataclass
class ToolContext:
    state: SessionState
    store: Store


ITENS_SCHEMA = {
    "type": "array",
    "description": "Produtos pelo código (product_id) e quantidade. Nunca informe preços.",
    "items": {
        "type": "object",
        "properties": {
            "product_id": {"type": "integer"},
            "quantidade": {"type": "integer", "minimum": 1, "default": 1},
        },
        "required": ["product_id"],
    },
}


def _fn(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required or []},
        },
    }


def tool_schemas() -> list[dict]:
    secoes = list(policies.load_sections())
    return [
        _fn(
            "buscar_produtos",
            "Busca instrumentos no catálogo por nome, marca, modelo ou tipo (sem considerar acentos). "
            "Retorna preço original, preço atual, promoção ativa, disponibilidade e alertas de cadastro. "
            "Use para qualquer pergunta sobre preço, estoque ou opções de produto.",
            {
                "texto": {"type": "string", "description": "Ex.: 'Takamine GD20', 'Yamaha', '7 cordas'"},
                "categoria": {
                    "type": "string",
                    "description": "guitarra, baixo, bateria, teclado, violão, ukulele, sopro, cordas orquestrais",
                },
                "preco_max": {"type": "number", "description": "Filtro de preço máximo em R$ (preço atual)"},
                "preco_min": {"type": "number"},
                "so_disponiveis": {"type": "boolean", "default": False},
            },
        ),
        _fn(
            "detalhar_produto",
            "Descrição, especificações e promoções encerradas de um produto. Use quando o cliente "
            "pedir detalhes ou perguntar se uma promoção específica ainda vale. Se o cliente "
            "disser quantas unidades quer, passe 'quantidade' para saber se o estoque atende.",
            {"product_id": {"type": "integer"},
             "quantidade": {"type": "integer", "minimum": 1}},
            ["product_id"],
        ),
        _fn(
            "listar_promocoes_ativas",
            "Lista as promoções vigentes no sistema. Para sugerir promoções parecidas com o produto "
            "da conversa, passe a categoria dele.",
            {"categoria": {"type": "string", "description": "Opcional. Ex.: violão, guitarra, ukulele"}},
        ),
        _fn(
            "calcular_pagamento",
            "Calcula valores de pagamento a partir dos códigos dos produtos: PIX (5% só sem promoção), "
            "débito, boleto e crédito em até 12x com as parcelas mínimas do §3.1. Sem 'forma', "
            "devolve todas as opções. Nunca calcule valores por conta própria.",
            {
                "itens": ITENS_SCHEMA,
                "forma": {"type": "string", "enum": list(pricing.FORMAS)},
                "parcelas": {"type": "integer", "minimum": 1, "maximum": 12},
            },
            ["itens"],
        ),
        _fn(
            "calcular_frete",
            "Frete e prazo de entrega para uma cidade, a partir dos códigos dos produtos.",
            {"itens": ITENS_SCHEMA, "cidade": {"type": "string"}},
            ["itens", "cidade"],
        ),
        _fn(
            "verificar_cliente",
            "Confirma a identidade do cliente antes de qualquer consulta de pedido. Exige o e-mail "
            "do cadastro e mais um dado: o número de um pedido OU os 4 últimos dígitos do telefone.",
            {
                "email": {"type": "string"},
                "order_id": {"type": "integer"},
                "final_telefone": {"type": "string", "description": "4 últimos dígitos"},
            },
            ["email"],
        ),
        _fn("listar_pedidos_do_cliente", "Lista os pedidos do cliente já verificado.", {}),
        _fn(
            "consultar_pedido",
            "Status, itens, total, rastreio e previsão de entrega de um pedido do cliente verificado.",
            {"order_id": {"type": "integer"}},
            ["order_id"],
        ),
        _fn(
            "avaliar_devolucao",
            "Calcula, para um pedido do cliente verificado, os prazos de arrependimento (§4.1), troca "
            "por preferência (§4.3), troca por defeito (§4.2) e garantia legal (§8.1). Use sempre "
            "que o cliente falar em devolver, trocar, arrependimento ou defeito.",
            {"order_id": {"type": "integer"}},
            ["order_id"],
        ),
        _fn(
            "consultar_politica",
            "Devolve o texto exato de uma seção do manual de políticas da loja, para citar. Use "
            f"antes de responder qualquer dúvida de política. Seções: {policies.section_catalog()}.",
            {"secao": {"type": "string", "enum": secoes}},
            ["secao"],
        ),
        _fn(
            "info_loja",
            "Endereço, telefone, WhatsApp, e-mail, horários e se a loja está aberta agora.",
            {},
        ),
        _fn(
            "encaminhar_humano",
            "Abre chamado para a equipe humana: reclamações, defeitos, atrasos, devoluções a "
            "processar, cotação de frete por CEP ou dúvidas que o manual manda levar à gerência.",
            {
                "categoria": {"type": "string", "enum": support.CATEGORIAS},
                "resumo": {"type": "string", "description": (
                    "Só o que o cliente relatou ou pediu, em uma frase. Sem nome, e-mail, telefone ou "
                    "datas: os dados do pedido são anexados pelo sistema a partir do order_id.")},
                "order_id": {"type": "integer"},
            },
            ["categoria", "resumo"],
        ),
    ]


def _handlers(ctx: ToolContext) -> dict[str, Callable[..., Any]]:
    s = ctx.state
    return {
        "buscar_produtos": catalog.buscar_produtos,
        "detalhar_produto": catalog.detalhar_produto,
        "listar_promocoes_ativas": catalog.listar_promocoes_ativas,
        "calcular_pagamento": pricing.calcular_pagamento,
        "calcular_frete": pricing.calcular_frete,
        "verificar_cliente": lambda **kw: customers.verificar_cliente(s, **kw),
        "listar_pedidos_do_cliente": lambda **kw: customers.listar_pedidos_do_cliente(s),
        "consultar_pedido": lambda **kw: customers.consultar_pedido(s, **kw),
        "avaliar_devolucao": lambda **kw: customers.avaliar_devolucao(s, **kw),
        "consultar_politica": policies.consultar_politica,
        "info_loja": lambda **kw: store_tools.info_loja(),
        "encaminhar_humano": lambda **kw: support.encaminhar_humano(s, ctx.store, **kw),
    }


def dispatch(ctx: ToolContext, name: str, raw_args: str | dict | None) -> dict:
    """Executa a ferramenta e sempre devolve um dict; erros viram mensagens para o modelo."""
    handler = _handlers(ctx).get(name)
    if handler is None:
        return {"erro": f"Ferramenta '{name}' não existe."}
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) and raw_args.strip() else (raw_args or {})
        if not isinstance(args, dict):
            raise ValueError("argumentos devem ser um objeto JSON")
        args = {k: v for k, v in args.items() if v is not None}
        return handler(**args)
    except TypeError as e:
        return {"erro": f"Argumentos inválidos para {name}: {e}"}
    except (ValueError, json.JSONDecodeError) as e:
        return {"erro": f"Não consegui ler os argumentos: {e}"}
