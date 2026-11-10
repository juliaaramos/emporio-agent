"""Loop de function calling sobre qualquer API compatível com a da OpenAI. Sem frameworks:
o loop é curto e explícito, o que facilita depurar, medir e trocar de provedor."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .config import PROMPTS_DIR, LLMConfig, reference_now
from .session import SessionState, Store
from .tools import ToolContext, dispatch, tool_schemas
from .tools.store import status_at

MAX_TOOL_ROUNDS = 8
HISTORY_MESSAGES = 40  # janela de contexto; o histórico completo fica no SQLite
FALLBACK = (
    "Desculpe, tive um problema técnico agora. Você pode tentar de novo ou falar com a equipe "
    "pelo WhatsApp (67) 3321-4500."
)


class ChatClient(Protocol):
    """Interface mínima usada do SDK openai (facilita testar com um cliente falso)."""

    chat: object


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict
    result: dict
    ms: int


@dataclass
class TurnResult:
    reply: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0})


def build_system_prompt() -> str:
    st = status_at(reference_now())
    extra = st.get("reabre", "") and f"O atendimento humano volta {st['reabre']}."
    if st["aberta_agora"]:
        extra = f"Fecha hoje às {st['fecha_hoje_as']}."
    template = (PROMPTS_DIR / "system.md").read_text(encoding="utf-8")
    return template.format(agora=st["agora"], aberta="sim" if st["aberta_agora"] else "não", status_extra=extra)


def _trim(history: list[dict], n: int = HISTORY_MESSAGES) -> list[dict]:
    """Mantém as últimas n mensagens começando numa mensagem de usuário, para não
    separar uma chamada de ferramenta do seu resultado."""
    if len(history) <= n:
        return history
    tail = history[-n:]
    for i, m in enumerate(tail):
        if m.get("role") == "user":
            return tail[i:]
    return tail


class Agent:
    def __init__(
        self,
        client: ChatClient,
        cfg: LLMConfig,
        store: Store,
        session_id: str,
        on_tool: Callable[[ToolCallRecord], None] | None = None,
    ):
        self.client, self.cfg, self.store = client, cfg, store
        self.state = SessionState(session_id)  # verificação não sobrevive ao fim da sessão
        self.ctx = ToolContext(self.state, store)
        self.history = store.history(session_id)
        self.on_tool = on_tool
        self.tools = tool_schemas()

    def _remember(self, message: dict) -> None:
        self.history.append(message)
        self.store.append(self.state.session_id, message)

    def _complete(self, system: dict):
        kwargs = dict(
            model=self.cfg.model,
            temperature=self.cfg.temperature,
            messages=[system, *_trim(self.history)],
            tools=self.tools,
            tool_choice="auto",
        )
        if self.cfg.max_tokens:
            kwargs["max_tokens"] = self.cfg.max_tokens
        try:
            return self.client.chat.completions.create(**kwargs)
        except Exception as e:
            # Alguns provedores (ex.: Groq) validam a chamada de ferramenta gerada e devolvem
            # 400 quando o modelo produz argumentos malformados. Uma nova amostragem costuma resolver.
            if "tool call validation" in str(e).lower() or "failed to call a function" in str(e).lower():
                return self.client.chat.completions.create(**kwargs)
            raise

    def turn(self, user_text: str) -> TurnResult:
        self._remember({"role": "user", "content": user_text})
        result = TurnResult(reply="")
        system = {"role": "system", "content": build_system_prompt()}

        for _ in range(MAX_TOOL_ROUNDS):
            try:
                resp = self._complete(system)
            except Exception as e:  # erro de rede/provedor: resposta segura, sem travar a conversa
                result.reply = FALLBACK
                result.usage["erro"] = f"{type(e).__name__}: {e}"
                self._remember({"role": "assistant", "content": FALLBACK})
                return result

            if getattr(resp, "usage", None):
                result.usage["prompt_tokens"] += resp.usage.prompt_tokens or 0
                result.usage["completion_tokens"] += resp.usage.completion_tokens or 0
            msg = resp.choices[0].message
            calls = msg.tool_calls or []
            if not calls:
                result.reply = (msg.content or "").strip() or FALLBACK
                self._remember({"role": "assistant", "content": result.reply})
                return result

            self._remember(
                {
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": [
                        {"id": c.id, "type": "function",
                         "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}}
                        for c in calls
                    ],
                }
            )
            for c in calls:
                t0 = time.perf_counter()
                out = dispatch(self.ctx, c.function.name, c.function.arguments)
                try:
                    args = json.loads(c.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {"_raw": c.function.arguments}
                rec = ToolCallRecord(c.function.name, args, out, int((time.perf_counter() - t0) * 1000))
                result.tool_calls.append(rec)
                if self.on_tool:
                    self.on_tool(rec)
                self._remember(
                    {"role": "tool", "tool_call_id": c.id, "content": json.dumps(out, ensure_ascii=False)}
                )

        result.reply = (
            "Hmm, essa ficou mais complexa do que consigo resolver por aqui. Vou deixar registrado "
            "para a equipe: fale com a gente pelo WhatsApp (67) 3321-4500."
        )
        self._remember({"role": "assistant", "content": result.reply})
        return result


def make_client(cfg: LLMConfig):
    from openai import OpenAI

    from .config import PROVIDERS

    if not cfg.api_key:
        var = (PROVIDERS.get(cfg.provider) or {}).get("key_env") or "LLM_API_KEY"
        raise SystemExit(f"Defina {var} no arquivo .env (veja .env.example).")
    local = cfg.provider == "ollama"
    # Modelo local em CPU é lento; provedores gratuitos devolvem 429: o SDK faz backoff
    # exponencial respeitando o Retry-After.
    return OpenAI(api_key=cfg.api_key, base_url=cfg.base_url, timeout=900 if local else 90, max_retries=6)
