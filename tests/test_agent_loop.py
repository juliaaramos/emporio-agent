"""Testa o loop do agente com um cliente LLM falso: sem rede e sem custo."""
import json
from types import SimpleNamespace as NS

from emporio.agent import Agent, build_system_prompt
from emporio.config import LLMConfig

CFG = LLMConfig(api_key="x", base_url="http://fake", model="fake", temperature=0)


def _call(i, name, args):
    return NS(id=f"call_{i}", function=NS(name=name, arguments=json.dumps(args)))


class FakeClient:
    """Devolve respostas roteirizadas e guarda as mensagens recebidas."""

    def __init__(self, script):
        self.script, self.seen = list(script), []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.seen.append(kw["messages"])
        msg = self.script.pop(0)
        return NS(choices=[NS(message=msg)], usage=NS(prompt_tokens=10, completion_tokens=5))


def test_tool_round_trip(store):
    client = FakeClient([
        NS(content=None, tool_calls=[_call(1, "buscar_produtos", {"texto": "Takamine GD20"})]),
        NS(content="O Takamine GD20 custa R$ 2.199,00.", tool_calls=None),
    ])
    agent = Agent(client, CFG, store, store.new_session("fake"))
    r = agent.turn("Quanto custa o Takamine GD20?")
    assert r.reply == "O Takamine GD20 custa R$ 2.199,00."
    assert [c.name for c in r.tool_calls] == ["buscar_produtos"]
    tool_msg = client.seen[1][-1]
    assert tool_msg["role"] == "tool" and "R$ 2.199,00" in tool_msg["content"]
    assert r.usage["prompt_tokens"] == 20


def test_verification_lives_in_session_state_not_in_model_args(store):
    client = FakeClient([
        NS(content=None, tool_calls=[_call(1, "verificar_cliente", {"email": "pedro.oliveira@jmail.com", "order_id": 1})]),
        NS(content=None, tool_calls=[_call(2, "consultar_pedido", {"order_id": 8, "customer_id": 2})]),
        NS(content="ok", tool_calls=None),
    ])
    agent = Agent(client, CFG, store, store.new_session("fake"))
    r = agent.turn("oi")
    assert agent.state.verified_customer_id == 3
    # argumento extra (customer_id) é rejeitado; o modelo não consegue escolher o cliente
    assert "erro" in r.tool_calls[1].result


def test_history_persists_but_verification_does_not(store):
    sid = store.new_session("fake")
    a1 = Agent(FakeClient([
        NS(content=None, tool_calls=[_call(1, "verificar_cliente", {"email": "pedro.oliveira@jmail.com", "order_id": 1})]),
        NS(content="verificado", tool_calls=None),
    ]), CFG, store, sid)
    a1.turn("sou o Pedro")
    a2 = Agent(FakeClient([NS(content="oi de novo", tool_calls=None)]), CFG, store, sid)
    assert len(a2.history) == 4  # user, assistant(tool_calls), tool, assistant
    assert a2.state.verified_customer_id is None


def test_provider_error_returns_safe_message(store):
    class Broken:
        chat = NS(completions=NS(create=lambda **kw: (_ for _ in ()).throw(TimeoutError("boom"))))

    r = Agent(Broken(), CFG, store, store.new_session("fake")).turn("oi")
    assert "WhatsApp" in r.reply and "erro" in r.usage


def test_system_prompt_has_clock():
    p = build_system_prompt()
    assert "25/03/2026 10:30" in p and "Loja aberta agora: sim" in p
