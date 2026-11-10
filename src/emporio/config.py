"""Configuração central: caminhos, relógio de referência e parâmetros do modelo."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import dotenv_values, load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
POLICIES_MD = DATA_DIR / "policies.md"
CATALOG_DB = DATA_DIR / "emporio.db"
SESSIONS_DB = DATA_DIR / "sessions.db"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

TZ = ZoneInfo("America/Campo_Grande")

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    temperature: float
    provider: str = "custom"
    max_tokens: int | None = None  # teto de resposta; alguns planos gratuitos exigem


# Provedores pré-configurados (todos com API compatível com a da OpenAI).
# A chave de cada um vem de uma variável própria; o modelo pode ser trocado por <NOME>_MODEL.
PROVIDERS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-3.5-flash",
        "key_env": "GEMINI_API_KEY",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-120b",
        "key_env": "GROQ_API_KEY",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5:3b",
        "key_env": None,  # local, sem chave
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "key_env": "OPENAI_API_KEY",
    },
}
DEFAULT_PROVIDER = "groq"


def llm_config(provider: str | None = None) -> LLMConfig:
    """Provedor escolhido por argumento, por LLM_PROVIDER ou o padrão (groq).
    LLM_BASE_URL/LLM_MODEL/LLM_API_KEY, se definidos, sobrescrevem tudo (provedor livre)."""
    name = (provider or os.getenv("LLM_PROVIDER") or DEFAULT_PROVIDER).lower()
    if name not in PROVIDERS:
        raise SystemExit(f"Provedor '{name}' desconhecido. Use um de: {', '.join(PROVIDERS)}.")
    p = PROVIDERS[name]
    custom = provider is None  # overrides genéricos só valem para o provedor do .env
    # Chaves vêm SÓ do .env do projeto, nunca de variáveis do sistema: evita usar sem
    # querer uma chave de outro projeto/empresa que esteja no ambiente da máquina.
    env_file = dotenv_values(ROOT / ".env")
    key = (p["key_env"] and env_file.get(p["key_env"]) or "") or ("ollama" if p["key_env"] is None else "")
    return LLMConfig(
        api_key=(custom and env_file.get("LLM_API_KEY")) or key,
        base_url=(custom and os.getenv("LLM_BASE_URL")) or p["base_url"],
        model=(custom and os.getenv("LLM_MODEL")) or os.getenv(f"{name.upper()}_MODEL") or p["model"],
        temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
        provider=name,
        # Ex.: a Groq gratuita limita alguns modelos a 1.000 tokens de saída por minuto e
        # recusa pedidos sem teto explícito. GROQ_MAX_TOKENS=900 resolve.
        max_tokens=int(v) if (v := os.getenv(f"{name.upper()}_MAX_TOKENS") or os.getenv("LLM_MAX_TOKENS")) else None,
    )


def reference_now() -> datetime:
    """'Agora' da loja. REFERENCE_DATE/REFERENCE_TIME congelam o relógio para
    que o retrato dos dados (março/2026) seja coerente e os testes reprodutíveis."""
    real = datetime.now(TZ)
    d_raw = os.getenv("REFERENCE_DATE", "").strip()
    t_raw = os.getenv("REFERENCE_TIME", "").strip()
    d = date.fromisoformat(d_raw) if d_raw else real.date()
    t = time.fromisoformat(t_raw) if t_raw else real.time().replace(microsecond=0)
    return datetime.combine(d, t, tzinfo=TZ)


def today() -> date:
    return reference_now().date()


# Dados da loja. Conflitos do manual resolvidos e documentados no README:
# - §1.2 lista (67) 3341-4444 como "Telefone / WhatsApp"; §7 dá (67) 3321-4500 como
#   o canal de WhatsApp. Usamos 3341-4444 como telefone e 3321-4500 como WhatsApp.
# - E-mail sem acento (a capa do manual não tem acento; o §1.2 parece erro de digitação).
STORE = {
    "nome": "Empório da Música",
    "slogan": "Sua música começa aqui.",
    "endereco": "Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, CEP 79202-333",
    "telefone": "(67) 3341-4444",
    "whatsapp": "(67) 3321-4500",
    "email": "contato@emporiodamusica.com.br",
}

# Região metropolitana atendida por motoboy (§5.1). O manual não lista os municípios;
# suposição conservadora: apenas Campo Grande. Ampliar aqui quando a loja confirmar.
METRO_CITIES = {"campo grande"}
