"""Grava as chaves de API no .env sem exibi-las.

    python scripts/configurar_chaves.py          # janela com campos mascarados (Ctrl+V funciona)
    python scripts/configurar_chaves.py --texto  # versão de terminal

Campo em branco mantém o valor atual. O .env está no .gitignore.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
KEYS = ["GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"]


def save(values: dict[str, str]) -> list[str]:
    if not ENV.exists():
        shutil.copy(ROOT / ".env.example", ENV)
    text = ENV.read_text(encoding="utf-8")
    saved = []
    for name, value in values.items():
        value = value.strip()
        if not value:
            continue
        if re.search(rf"^{name}=.*$", text, flags=re.M):
            text = re.sub(rf"^{name}=.*$", lambda _: f"{name}={value}", text, flags=re.M)
        else:
            text += f"\n{name}={value}\n"
        saved.append(name)
    ENV.write_text(text, encoding="utf-8")
    return saved


def gui() -> None:
    import tkinter as tk

    root = tk.Tk()
    root.title("Empório — chaves de API")
    root.configure(padx=20, pady=16)
    entries = {}
    for i, name in enumerate(KEYS):
        tk.Label(root, text=name, anchor="w").grid(row=i * 2, column=0, sticky="w", pady=(8, 0))
        e = tk.Entry(root, show="*", width=60)
        e.grid(row=i * 2 + 1, column=0, sticky="we")
        entries[name] = e
    entries[KEYS[0]].focus_set()
    status = tk.Label(root, text="Cole com Ctrl+V. Campo vazio mantém o valor atual.", fg="#645FAA")
    status.grid(row=10, column=0, sticky="w", pady=(12, 0))

    def on_save() -> None:
        saved = save({k: e.get() for k, e in entries.items()})
        status.config(text=f"Gravado: {', '.join(saved) or 'nada'}. Pode fechar.", fg="#1a7f37")
        for e in entries.values():
            e.delete(0, tk.END)

    tk.Button(root, text="Salvar no .env", command=on_save, bg="#645FAA", fg="white", padx=16).grid(
        row=11, column=0, sticky="e", pady=(12, 0)
    )
    root.mainloop()


def text_mode() -> None:
    from getpass import getpass

    print("Cole a chave e aperte Enter (nada aparece na tela; é normal).")
    saved = save({k: getpass(f"{k} (Enter para manter): ") for k in KEYS})
    print(f"Gravado: {', '.join(saved) or 'nada'}.")


if __name__ == "__main__":
    text_mode() if "--texto" in sys.argv else gui()
