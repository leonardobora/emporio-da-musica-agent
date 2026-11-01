"""Scenario runner: transcript rendering and end-to-end run with the LLM faked."""

from __future__ import annotations

import json
import pathlib

import pytest

from emporio import database, runner
from emporio.agent import Agent, AgentReply, ToolStep
from emporio.llm import LLMResponse

ROOT = pathlib.Path(__file__).parents[1]
DATA_DIR = ROOT / "data"


class ScriptedClient:
    """Returns one canned answer per turn, with an optional tool call first."""

    model = "scripted"

    def __init__(self, per_turn):
        self.per_turn = list(per_turn)

    def complete(self, messages, tools=None):
        return self.per_turn.pop(0)


def _reply(text, tool=None, result=None):
    steps = []
    if tool:
        steps.append(ToolStep(tool=tool, arguments={"order_id": 2}, result=result or {"found": True}))
    return AgentReply(text=text, steps=steps, usage={"prompt_tokens": 10, "completion_tokens": 5})


def test_render_transcript_contains_dialogue_tools_and_checks():
    scenario = {
        "id": "99_teste",
        "title": "Teste",
        "goal": "provar o renderizador",
        "turns": ["oi"],
    }
    turns = [("oi", _reply("olá", tool="store_info", result={"hours": {"saturday": "09:00–13:00"}}))]
    checks = [runner.ScenarioCheck(name="usou store_info", passed=True)]

    text = runner.render_transcript(scenario, "abc123", "modelo-x", turns, checks)

    assert "# 99_teste — Teste" in text
    assert "**Cliente:** oi" in text
    assert "**Agente:** olá" in text
    assert "`store_info(" in text
    assert "✅ usou store_info" in text
    assert "do not edit" in text


def test_render_truncates_large_tool_results():
    big = {"products": [{"name": f"produto {i}", "description": "x" * 40} for i in range(40)]}
    text = runner.render_transcript(
        {"id": "t", "title": "t", "goal": "", "turns": ["oi"]},
        "s",
        "m",
        [("oi", _reply("ok", tool="search_products", result=big))],
        [],
    )
    assert "truncado" in text
    assert len(text) < 6000


def test_run_scenario_writes_the_transcript_and_scores_the_checks(tmp_path, monkeypatch):
    monkeypatch.setattr("emporio.prompts.build_system_prompt", lambda: "SYSTEM")
    conn = database.connect(tmp_path / "r.sqlite")
    database.load_store(conn, DATA_DIR)

    scenario = {
        "id": "98_run",
        "title": "Runner",
        "goal": "rodar de ponta a ponta",
        "turns": ["meu pedido 2, telefone 6543"],
        "expect": {"tools_required": ["get_order"], "reply_contains": ["entregue"]},
    }
    path = tmp_path / "98_run.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")

    client = ScriptedClient(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "get_order", "arguments": '{"order_id": 2, "phone_last4": "6543"}'},
                    }
                ],
                usage={"prompt_tokens": 5},
                model="scripted",
            ),
            LLMResponse(content="Seu pedido 2 foi entregue.", tool_calls=[], usage={}, model="scripted"),
        ]
    )

    result = runner.run_scenario(path, client, conn, tmp_path / "out", write_transcript=True)  # type: ignore[arg-type]

    assert result.passed is True
    assert result.answers == ["Seu pedido 2 foi entregue."]
    assert result.transcript_path and result.transcript_path.exists()
    assert result.usage["prompt_tokens"] >= 5


def test_run_scenario_reports_failures(tmp_path, monkeypatch):
    monkeypatch.setattr("emporio.prompts.build_system_prompt", lambda: "SYSTEM")
    conn = database.connect(tmp_path / "f.sqlite")
    database.load_store(conn, DATA_DIR)

    scenario = {
        "id": "97_fail",
        "title": "Falha",
        "goal": "",
        "turns": ["oi"],
        "expect": {"tools_required": ["get_order"], "reply_not_contains": ["R$"]},
    }
    path = tmp_path / "97_fail.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")

    client = ScriptedClient(
        [LLMResponse(content="custa R$ 10,00", tool_calls=[], usage={}, model="scripted")]
    )
    result = runner.run_scenario(path, client, conn, tmp_path / "out", write_transcript=False)  # type: ignore[arg-type]

    assert result.passed is False
    failed = [check.name for check in result.checks if not check.passed]
    assert any("get_order" in name for name in failed)


def test_evaluate_flags_missing_turn(tmp_path):
    scenario = {"id": "x", "title": "x", "turns": ["a"], "turn_expect": [{"index": 3, "reply_contains": ["z"]}]}
    checks = runner.evaluate(scenario, [_reply("nada")])
    assert any("turno 3" in check.name and not check.passed for check in checks)
