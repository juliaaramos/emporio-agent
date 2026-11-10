"""Gera as conversas de exemplo em examples/*.md rodando o agente de verdade, com o
rastro das chamadas de ferramenta. Nada é editado à mão depois.

    python scripts/gerar_exemplos.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from emporio.agent import Agent, make_client
from emporio.config import ROOT, llm_config, reference_now
from emporio.ingest import ensure_built
from emporio.session import Store

CONVERSAS = {
    "01_catalogo_violoes": (
        "Catálogo: violões até R$ 1.000",
        ["Oi! Quais opções de violões disponíveis custando até R$1000?",
         "Gostei do Giannini GF-3D Sunburst, tem ele?"],
    ),
    "02_precos_e_promocoes": (
        "Preços e promoções: promoção encerrada, promoção ativa e PIX",
        ["Quanto custa o Takamine GD20? A Oferta Especial de 12% ainda vale?",
         "E o Taylor 110e, está em promoção? No PIX tenho mais 5%?",
         "E em 12x no cartão?"],
    ),
    "03_devolucao_fora_do_prazo": (
        "Devolução (caso não trivial): verificação, prazos e garantia",
        ["Me arrependi da minha compra, posso devolver meu pedido?",
         "Meu e-mail é pedro.oliveira@jmail.com e o pedido é o 1",
         "Poxa... e se ele estiver com defeito?"],
    ),
    "04_pedido_atrasado": (
        "Pedido atrasado: consulta em tempo real e chamado para a equipe",
        ["Oi, meu pedido ainda não chegou. Meu e-mail é anacarol.ferreira@coldmail.com, pedido 8",
         "Pode abrir uma reclamação, por favor?"],
    ),
    "05_fora_de_escopo_e_loja": (
        "Fora de escopo, acessórios e informações da loja",
        ["Vocês vendem cordas e amplificador?",
         "Me ajuda com meu imposto de renda?",
         "Tá bom! Qual o endereço da loja e vocês estão abertos agora?"],
    ),
}


def render(title: str, model: str, turns: list[tuple[str, object]]) -> str:
    out = [f"# {title}", "",
           f"> Gerado por `scripts/gerar_exemplos.py` · modelo `{model}` · "
           f"data de referência {reference_now():%d/%m/%Y %H:%M}", ""]
    for user, res in turns:
        out += [f"**Cliente:** {user}", ""]
        if res.tool_calls:
            out.append("<details><summary>Rastro das ferramentas</summary>\n\n```text")
            for c in res.tool_calls:
                result = json.dumps(c.result, ensure_ascii=False)
                out.append(f"→ {c.name}({json.dumps(c.arguments, ensure_ascii=False)})")
                out.append(f"← {result[:600]}{'…' if len(result) > 600 else ''}")
            out.append("```\n</details>\n")
        out += [f"**Empório:** {res.reply}", "", "---", ""]
    return "\n".join(out)


def main() -> None:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    ensure_built()
    cfg = llm_config(sys.argv[1] if len(sys.argv) > 1 else None)  # ex.: python scripts/gerar_exemplos.py groq
    client = make_client(cfg)
    dest = ROOT / "examples"
    dest.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "s.db")
        only = sys.argv[2:]  # ex.: python scripts/gerar_exemplos.py groq 02_precos_e_promocoes
        for slug, (title, msgs) in CONVERSAS.items():
            if only and slug not in only:
                continue
            agent = Agent(client, cfg, store, store.new_session(cfg.model))
            turns = [(m, agent.turn(m)) for m in msgs]
            falhas = [r.usage["erro"] for _, r in turns if r.usage.get("erro")]
            if falhas:  # nunca salva uma conversa com a mensagem de erro do provedor
                print(f"FALHOU {slug}: {falhas[0][:200]}")
                continue
            (dest / f"{slug}.md").write_text(render(title, cfg.model, turns), encoding="utf-8")
            print(f"ok {slug}")
        store.con.close()


if __name__ == "__main__":
    main()
