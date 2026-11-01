"""CLI plumbing and the LLM transport, without touching the network."""

from __future__ import annotations

import json
import pathlib

import httpx
import pytest

from emporio import cli, database
from emporio.llm import DeepSeekClient, LLMError

ROOT = pathlib.Path(__file__).parents[1]


def test_scenario_paths_resolves_names_directories_and_empty(tmp_path):
    all_scenarios = cli._scenario_paths([])
    assert len(all_scenarios) == 5, "examples/ holds the 3-5 delivered conversations"
    assert all(p.suffix == ".json" for p in all_scenarios)

    by_name = cli._scenario_paths(["02_pedido"])
    assert by_name[0].name == "02_pedido.json"

    by_dir = cli._scenario_paths([str(ROOT / "examples" / "scenarios")])
    assert len(by_dir) == len(all_scenarios)

    extra = cli._scenario_paths([str(ROOT / "tests" / "scenarios" / "06_frete_por_cep.json")])
    assert extra[0].name == "06_frete_por_cep.json"

    missing = cli._scenario_paths(["nao_existe"])
    assert missing == []


def test_rebuild_command_works_without_an_api_key(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "cli.sqlite"
    monkeypatch.setenv("EMPORIO_DB", str(db_path))
    monkeypatch.setenv("EMPORIO_DATA", str(ROOT / "data"))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr("emporio.config.load_dotenv", lambda path=None: None)

    assert cli.main(["rebuild"]) == 0
    out = capsys.readouterr().out
    assert "store_products': 65" in out or "'store_products': 65" in out

    conn = database.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM store_orders").fetchone()[0] == 20


def test_history_command_reports_unknown_session(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EMPORIO_DB", str(tmp_path / "h.sqlite"))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr("emporio.config.load_dotenv", lambda path=None: None)
    assert cli.main(["history", "deadbeef"]) == 1
    assert "inexistente" in capsys.readouterr().out


# --- LLM transport ------------------------------------------------------------------


def _client_with(handler, monkeypatch, **kwargs) -> DeepSeekClient:
    """Build a client whose HTTP transport is a MockTransport (monkeypatch restores it)."""
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: real_client(transport=transport))
    return DeepSeekClient(api_key="test-key", **kwargs)


@pytest.fixture(autouse=True)
def _restore_httpx(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _s: None)
    yield


def test_client_parses_content_and_tool_calls(monkeypatch):
    payload = {
        "model": "deepseek-chat",
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "get_order", "arguments": '{"order_id": 2}'},
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3},
    }
    client = _client_with(lambda request: httpx.Response(200, json=payload), monkeypatch)

    response = client.complete([{"role": "user", "content": "oi"}], tools=[])

    assert response.tool_calls[0]["function"]["name"] == "get_order"
    assert response.usage["prompt_tokens"] == 12


def test_client_retries_server_errors_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": "ok"}}], "usage": {}})

    client = _client_with(handler, monkeypatch, max_retries=2)
    response = client.complete([{"role": "user", "content": "oi"}])
    assert response.content == "ok"
    assert calls["n"] == 2


def test_client_raises_on_client_error_without_retrying(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, text="bad request")

    client = _client_with(handler, monkeypatch, max_retries=3)
    with pytest.raises(LLMError):
        client.complete([{"role": "user", "content": "oi"}])
    assert calls["n"] == 1


def test_client_gives_up_after_max_retries(monkeypatch):
    def handler(request):
        return httpx.Response(500, text="boom")

    client = _client_with(handler, monkeypatch, max_retries=2)
    with pytest.raises(LLMError):
        client.complete([{"role": "user", "content": "oi"}])
