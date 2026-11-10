"""Avaliação do agente contra o golden set.

    python -m emporio.eval                 # 3 repetições por caso, modelo do .env
    python -m emporio.eval --runs 1 --only preco_takamine
    python -m emporio.eval --judge         # + LLM como juiz do tom (opcional)
    python -m emporio.eval --provider gemini groq ollama --pause 5   # compara provedores

Um caso só passa se passar em TODAS as repetições. Casos reservados (holdout)
são reportados separadamente. Resultados em eval_results/<modelo>.json e .md.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import yaml

from .agent import Agent, make_client
from .config import ROOT, llm_config
from .ingest import ensure_built
from .session import Store
from .text import normalize

GOLDEN = ROOT / "tests" / "eval" / "golden.yaml"
OUT_DIR = ROOT / "eval_results"
MONEY_RE = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)")

JUDGE_PROMPT = """Você avalia o TOM de um assistente de loja de instrumentos musicais.
Critério (manual da loja, §7.1): informal mas profissional, acolhedor, "um amigo que entende de música",
nada robótico nem excessivamente formal, objetivo para chat.
Dê uma nota de 1 a 5 e uma justificativa curta. Responda só JSON: {"nota": n, "justificativa": "..."}"""


def money_values(text: str) -> set[Decimal]:
    out = set()
    for m in MONEY_RE.findall(text):
        out.add(Decimal(m.replace(".", "").replace(",", ".")))
    return out


def _to_dec(s: str) -> Decimal:
    return Decimal(s.replace(".", "").replace(",", "."))


@dataclass
class TurnCheck:
    ok: bool
    failures: list[str] = field(default_factory=list)


def check_turn(expect: dict, reply: str, tools: list[str], tools_so_far: list[str]) -> TurnCheck:
    f: list[str] = []
    text = normalize(reply)
    called = set(tools)
    for t in expect.get("tools_all", []):
        if t not in called:
            f.append(f"não chamou {t}")
    if expect.get("tools_any") and not called & set(expect["tools_any"]):
        f.append(f"não chamou nenhuma de {expect['tools_any']}")
    for t in expect.get("tools_none", []):
        if t in called:
            f.append(f"chamou {t} indevidamente")
    if expect.get("policy") and "consultar_politica" not in tools_so_far:
        f.append("respondeu política sem consultar_politica")
    values = money_values(reply)
    for n in expect.get("numbers", []):
        if _to_dec(n) not in values:
            f.append(f"valor R$ {n} ausente")
    for n in expect.get("forbid_numbers", []):
        if _to_dec(n) in values:
            f.append(f"valor proibido R$ {n}")
    if expect.get("contains_any") and not any(normalize(s) in text for s in expect["contains_any"]):
        f.append(f"faltou algum de {expect['contains_any']}")
    for s in expect.get("not_contains", []):
        if normalize(s) in text:
            f.append(f"contém '{s}'")
    return TurnCheck(not f, f)


def run_case(client, cfg, case: dict, store: Store) -> dict:
    agent = Agent(client, cfg, store, store.new_session(cfg.model))
    turns, all_tools, ok = [], [], True
    for t in case["turns"]:
        t0 = time.perf_counter()
        res = agent.turn(t["user"])
        names = [c.name for c in res.tool_calls]
        all_tools += names
        chk = check_turn(t.get("expect", {}), res.reply, names, all_tools)
        ok &= chk.ok
        turns.append({
            "user": t["user"], "reply": res.reply, "tools": names, "ok": chk.ok,
            "failures": chk.failures, "latency_s": round(time.perf_counter() - t0, 2), "usage": res.usage,
        })
    return {"ok": ok, "turns": turns}


def judge_tone(client, cfg, transcript: str) -> dict:
    try:
        r = client.chat.completions.create(
            model=cfg.model, temperature=0,
            messages=[{"role": "system", "content": JUDGE_PROMPT}, {"role": "user", "content": transcript}],
        )
        return json.loads(re.search(r"\{.*\}", r.choices[0].message.content, re.S).group(0))
    except Exception as e:  # o juiz é opcional; falha não derruba a avaliação
        return {"nota": None, "justificativa": f"erro do juiz: {e}"}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--only", nargs="*", help="ids de casos")
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--provider", nargs="*", help="um ou mais: gemini groq ollama openai")
    ap.add_argument("--pause", type=float, default=0, help="segundos entre casos (limites de planos gratuitos)")
    args = ap.parse_args(argv)
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    ensure_built()
    summaries = []
    for provider in args.provider or [None]:
        summaries.append(evaluate(llm_config(provider), args))
    if len(summaries) > 1:
        write_comparison(summaries)


def write_comparison(summaries: list[dict]) -> None:
    cols = ["provedor", "modelo", "casos_dev", "casos_holdout", "acerto_de_ferramenta_por_turno",
            "latencia_mediana_s", "tokens_totais", "erros_de_provedor"]
    lines = ["# Comparação de modelos", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(s.get(c, "")) for c in cols) + " |" for s in summaries]
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "comparacao.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def evaluate(cfg, args) -> dict:
    print(f"\n=== {cfg.provider} / {cfg.model} ===")
    try:
        client = make_client(cfg)
    except SystemExit as e:
        print(f"pulando: {e}")
        return {"provedor": cfg.provider, "modelo": cfg.model, "casos_dev": "sem chave"}
    cases = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))
    if args.only:
        cases = [c for c in cases if c["id"] in args.only]

    results = []
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "eval_sessions.db")
        for i, case in enumerate(cases):
            if i and args.pause:
                time.sleep(args.pause)
            runs = [run_case(client, cfg, case, store) for _ in range(args.runs)]
            passed = all(r["ok"] for r in runs)
            entry = {"id": case["id"], "holdout": bool(case.get("holdout")), "passed": passed, "runs": runs}
            if args.judge:
                transcript = "\n".join(f"Cliente: {t['user']}\nAssistente: {t['reply']}" for t in runs[0]["turns"])
                entry["tom"] = judge_tone(client, cfg, transcript)
            results.append(entry)
            fails = sorted({f for r in runs for t in r["turns"] for f in t["failures"]})
            mark = "PASS" if passed else "FAIL"
            print(f"[{mark}] {case['id']}{' (holdout)' if entry['holdout'] else ''} {'; '.join(fails)}")
        store.con.close()

    def rate(sel):
        return f"{sum(r['passed'] for r in sel)}/{len(sel)}" if sel else "-"

    dev = [r for r in results if not r["holdout"]]
    hold = [r for r in results if r["holdout"]]
    all_turns = [t for r in results for run in r["runs"] for t in run["turns"]]
    tool_ok = sum(not any(f.startswith(("não chamou", "chamou", "respondeu política")) for f in t["failures"]) for t in all_turns)
    lat = sorted(t["latency_s"] for t in all_turns)
    tokens = sum(t["usage"]["prompt_tokens"] + t["usage"]["completion_tokens"] for t in all_turns)
    summary = {
        "provedor": cfg.provider,
        "modelo": cfg.model,
        "erros_de_provedor": sum(1 for t in all_turns if "erro" in t["usage"]),
        "repeticoes": args.runs,
        "casos_dev": rate(dev),
        "casos_holdout": rate(hold),
        "acerto_de_ferramenta_por_turno": f"{tool_ok}/{len(all_turns)}",
        "latencia_mediana_s": lat[len(lat) // 2] if lat else None,
        "tokens_totais": tokens,
    }
    if args.judge:
        notas = [r["tom"]["nota"] for r in results if r.get("tom", {}).get("nota")]
        summary["tom_nota_media"] = round(sum(notas) / len(notas), 2) if notas else None
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    OUT_DIR.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9.-]+", "_", cfg.model)
    (OUT_DIR / f"{slug}.json").write_text(
        json.dumps({"resumo": summary, "casos": results}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [f"# Golden set — {cfg.model}", "", *(f"- **{k}**: {v}" for k, v in summary.items()), "",
             "| caso | holdout | resultado |", "|---|---|---|"]
    lines += [f"| {r['id']} | {'sim' if r['holdout'] else ''} | {'✅' if r['passed'] else '❌'} |" for r in results]
    (OUT_DIR / f"{slug}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    main()
