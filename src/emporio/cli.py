"""Interface de linha de comando.

    python -m emporio.cli              # nova conversa
    python -m emporio.cli --trace      # mostra as chamadas de ferramenta
    python -m emporio.cli --resume     # retoma a última conversa (histórico, sem a verificação)
    python -m emporio.cli --session ID
"""
from __future__ import annotations

import argparse
import json
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.theme import Theme

from .agent import Agent, ToolCallRecord, make_client
from .config import llm_config, reference_now
from .ingest import ensure_built
from .session import Store

THEME = Theme({"agent": "bold #645FAA", "user": "bold #20BEC6", "trace": "#20BEC6", "muted": "grey50"})


def trace_line(rec: ToolCallRecord) -> str:
    args = json.dumps(rec.arguments, ensure_ascii=False)
    res = json.dumps(rec.result, ensure_ascii=False)
    if len(res) > 300:
        res = res[:300] + "…"
    return f"→ {rec.name}({args}) [{rec.ms} ms]\n  ← {res}"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Agente de atendimento da Empório da Música")
    ap.add_argument("--trace", action="store_true", help="mostra as chamadas de ferramenta")
    ap.add_argument("--resume", action="store_true", help="retoma a última sessão")
    ap.add_argument("--session", help="retoma uma sessão específica")
    ap.add_argument("--provider", help="gemini | groq | ollama | openai (padrão: LLM_PROVIDER do .env)")
    args = ap.parse_args(argv)

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    console = Console(theme=THEME)
    ensure_built()
    cfg = llm_config(args.provider)
    store = Store()

    sid = args.session or (store.last_session() if args.resume else None)
    if sid and not store.session_exists(sid):
        console.print(f"[muted]Sessão {sid} não encontrada; iniciando uma nova.[/]")
        sid = None
    sid = sid or store.new_session(cfg.model)

    on_tool = (lambda r: console.print(trace_line(r), style="trace", highlight=False)) if args.trace else None
    agent = Agent(make_client(cfg), cfg, store, sid, on_tool=on_tool)

    console.print(
        Panel.fit(
            f"[agent]Empório da Música[/] — assistente virtual\n"
            f"[muted]sessão {sid} · {cfg.provider}/{cfg.model} ·data de referência {reference_now():%d/%m/%Y %H:%M}\n"
            f"digite /sair para encerrar[/]",
            border_style="#645FAA",
        )
    )
    while True:
        try:
            text = console.input("[user]você ›[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text.lower() in {"/sair", "sair", "/exit", "/quit"}:
            break
        with console.status("[muted]pensando…[/]", spinner="dots"):
            result = agent.turn(text)
        console.print("[agent]empório ›[/]", end=" ")
        console.print(Markdown(result.reply))
        if args.trace:
            u = result.usage
            console.print(f"[muted]tokens: {u['prompt_tokens']} in / {u['completion_tokens']} out[/]")
    console.print(f"[muted]Até mais! Para retomar: python -m emporio.cli --session {sid}[/]")


if __name__ == "__main__":
    main()
