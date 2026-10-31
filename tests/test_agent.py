"""Agent loop and tool dispatch with the LLM mocked at the transport boundary (ADR 0007)."""

from __future__ import annotations

import json
import pathlib

import pytest

from emporio import database, runner, tools
from emporio.agent import Agent
from emporio.llm import LLMResponse

DATA_DIR = pathlib.Path(__file__).parents[1] / "data"


class FakeClient:
    """Replays a fixed list of LLMResponse objects; records the messages it was given."""

    model = "fake-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    def complete(self, messages, tools=None):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("FakeClient ran out of scripted responses")
        return self.responses.pop(0)


def _tool_call(name: str, arguments: dict, call_id: str = "call_1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


@pytest.fixture()
def conn(tmp_path):
    connection = database.connect(tmp_path / "agent.sqlite")
    database.load_store(connection, DATA_DIR)
    return connection


def _agent(conn, responses, monkeypatch):
    from emporio import agent as agent_module

    monkeypatch.setattr(agent_module.prompts, "build_system_prompt", lambda: "SYSTEM")
    session_id = database.start_session(conn, "fake-model")
    return Agent(FakeClient(responses), conn, session_id, system_prompt="SYSTEM"), session_id


def test_loop_executes_tool_then_answers(conn, monkeypatch):
    responses = [
        LLMResponse(
            content="",
            tool_calls=[_tool_call("get_product", {"product_id_or_name": "Takamine GD20"})],
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            model="fake-model",
        ),
        LLMResponse(
            content="O Takamine GD20 está R$ 2.199,00 e temos 5 em estoque.",
            tool_calls=[],
            usage={"prompt_tokens": 20, "completion_tokens": 15},
            model="fake-model",
        ),
    ]
    agent, session_id = _agent(conn, responses, monkeypatch)
    reply = agent.reply("Quanto custa o Takamine GD20?")

    assert reply.rounds == 2
    assert "R$ 2.199,00" in reply.text
    assert reply.steps[0].tool == "get_product"
    assert reply.steps[0].result["price"]["price_formatted"] == "R$ 2.199,00"
    assert reply.usage["prompt_tokens"] == 30

    roles = [row["role"] for row in database.history(conn, session_id)]
    assert roles == ["user", "assistant", "tool", "assistant"]


def test_replay_keeps_tool_calls_and_results(conn, monkeypatch):
    responses = [
        LLMResponse(content="", tool_calls=[_tool_call("store_info", {})], usage={}, model="fake"),
        LLMResponse(content="Abrimos sábado até 13h.", tool_calls=[], usage={}, model="fake"),
        LLMResponse(content="De nada!", tool_calls=[], usage={}, model="fake"),
    ]
    agent, _ = _agent(conn, responses, monkeypatch)
    agent.reply("Que horas vocês abrem no sábado?")
    agent.reply("Obrigado!")

    second_turn_messages = agent.client.calls[-1]
    assert any(m.get("role") == "tool" for m in second_turn_messages)
    assistant_with_tools = [m for m in second_turn_messages if m.get("tool_calls")]
    assert assistant_with_tools and assistant_with_tools[0]["tool_calls"][0]["id"] == "call_1"


def test_verified_order_is_remembered_for_the_session(conn, monkeypatch):
    responses = [
        LLMResponse(
            content="",
            tool_calls=[_tool_call("get_order", {"order_id": 2, "phone_last4": "6543"})],
            usage={},
            model="fake",
        ),
        LLMResponse(content="Seu pedido foi entregue.", tool_calls=[], usage={}, model="fake"),
        LLMResponse(
            content="",
            tool_calls=[_tool_call("get_order", {"order_id": 2})],
            usage={},
            model="fake",
        ),
        LLMResponse(content="O rastreio é BRCX9876543BR.", tool_calls=[], usage={}, model="fake"),
    ]
    agent, session_id = _agent(conn, responses, monkeypatch)
    agent.reply("Meu pedido 2 chegou? telefone termina 6543")
    reply = agent.reply("E o rastreio?")

    assert database.get_bound_order(conn, session_id) == 2
    assert reply.steps[0].result["tracking_code"] == "BRCX9876543BR"
    assert "Contexto da sessão" in str(agent.client.calls[-1])


def test_wrong_phone_does_not_bind_the_session(conn, monkeypatch):
    responses = [
        LLMResponse(
            content="",
            tool_calls=[_tool_call("get_order", {"order_id": 2, "phone_last4": "0000"})],
            usage={},
            model="fake",
        ),
        LLMResponse(content="Não encontrei esse pedido com esses dados.", tool_calls=[], usage={}, model="fake"),
    ]
    agent, session_id = _agent(conn, responses, monkeypatch)
    reply = agent.reply("Pedido 2, telefone 0000")
    assert reply.steps[0].result["found"] is False
    assert database.get_bound_order(conn, session_id) is None


def test_max_tool_rounds_falls_back_to_human_handoff(conn, monkeypatch):
    looping = [
        LLMResponse(
            content="",
            tool_calls=[_tool_call("store_info", {}, call_id=f"call_{i}")],
            usage={},
            model="fake",
        )
        for i in range(3)
    ]
    from emporio import agent as agent_module

    session_id = database.start_session(conn, "fake-model")
    agent = Agent(FakeClient(looping), conn, session_id, system_prompt="SYSTEM", max_tool_rounds=3)
    reply = agent.reply("???")
    assert "atendente humano" in reply.text
    assert reply.rounds == 3


def test_unknown_tool_returns_error_without_crashing(conn):
    box = tools.ToolBox(conn, database.start_session(conn, "fake"))
    assert "desconhecida" in box.call("drop_database", {})["error"]


def test_escalation_is_persisted(conn):
    session_id = database.start_session(conn, "fake")
    box = tools.ToolBox(conn, session_id)
    result = box.call("escalate_to_human", {"reason": "reclamação", "summary": "produto com defeito"})
    assert result["registered"] is True
    row = conn.execute("SELECT reason FROM handoffs WHERE session_id = ?", (session_id,)).fetchone()
    assert row["reason"].startswith("reclamação")


def test_payment_options_tool_uses_product_price(conn):
    box = tools.ToolBox(conn, database.start_session(conn, "fake"))
    result = box.call("payment_options", {"product_id": 94})
    assert result["price_formatted"] == "R$ 5.519,08"
    assert result["pix"]["discount_percent"] == 0
    assert result["credit"]["max_installments"] == 12


def test_runner_checks_turn_level_expectations():
    scenario = {
        "id": "x",
        "title": "x",
        "turns": ["a"],
        "turn_expect": [{"index": 1, "reply_contains": ["R$"], "reply_not_contains": ["300"]}],
    }
    from emporio.agent import AgentReply

    checks = runner.evaluate(scenario, [AgentReply(text="custa R$ 10,00")])
    assert all(check.passed for check in checks)

    failing = runner.evaluate(scenario, [AgentReply(text="300 instrumentos")])
    assert not all(check.passed for check in failing)
