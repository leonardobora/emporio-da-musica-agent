"""The agent loop: one customer turn in, tool calls in between, one answer out."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from . import database, prompts, tools
from .llm import DeepSeekClient


@dataclass
class ToolStep:
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass
class AgentReply:
    text: str
    steps: list[ToolStep] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    rounds: int = 0


class Agent:
    def __init__(
        self,
        client: DeepSeekClient,
        conn: sqlite3.Connection,
        session_id: str,
        system_prompt: str | None = None,
        max_tool_rounds: int = 6,
    ):
        self.client = client
        self.conn = conn
        self.session_id = session_id
        self.system_prompt = system_prompt or prompts.build_system_prompt()
        self.max_tool_rounds = max_tool_rounds
        self.toolbox = tools.ToolBox(conn, session_id)

    # -- message plumbing ---------------------------------------------------------
    def _replay(self) -> list[dict[str, Any]]:
        """Rebuild the provider-agnostic message list from the persisted history.

        The policy manual lives in the system prompt (ADR 0001); the session's verified order
        is re-stated so the model does not ask for the phone again on every turn (ADR 0004).
        """
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        bound_order = database.get_bound_order(self.conn, self.session_id)
        if bound_order is not None:
            messages.append(
                {
                    "role": "system",
                    "content": prompts.SESSION_CONTEXT_TEMPLATE.format(order_id=bound_order),
                }
            )
        for row in database.history(self.conn, self.session_id):
            if row["role"] == "assistant" and row["tool_calls"]:
                messages.append(
                    {
                        "role": "assistant",
                        "content": row["content"] or "",
                        "tool_calls": json.loads(row["tool_calls"]),
                    }
                )
            elif row["role"] == "tool":
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": row["tool_call_id"],
                        "content": row["content"] or "{}",
                    }
                )
            else:
                messages.append({"role": row["role"], "content": row["content"] or ""})
        return messages

    # -- main loop ----------------------------------------------------------------
    def reply(self, user_text: str) -> AgentReply:
        database.append_message(self.conn, self.session_id, "user", user_text)
        messages = self._replay()
        steps: list[ToolStep] = []
        usage_total: dict[str, Any] = {}

        for round_index in range(1, self.max_tool_rounds + 1):
            response = self.client.complete(messages, tools.TOOLS)
            for key, value in (response.usage or {}).items():
                if isinstance(value, int):
                    usage_total[key] = usage_total.get(key, 0) + value

            if not response.tool_calls:
                text = response.content.strip()
                database.append_message(self.conn, self.session_id, "assistant", text)
                return AgentReply(text=text, steps=steps, usage=usage_total, rounds=round_index)

            messages.append(
                {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": response.tool_calls,
                }
            )
            database.append_message(
                self.conn,
                self.session_id,
                "assistant",
                response.content or "",
                tool_calls=response.tool_calls,
            )

            for call in response.tool_calls:
                name = call["function"]["name"]
                raw_args = call["function"].get("arguments") or "{}"
                try:
                    arguments = json.loads(raw_args)
                except json.JSONDecodeError:
                    arguments = {}
                result = self.toolbox.call(name, arguments)
                steps.append(ToolStep(tool=name, arguments=arguments, result=result))
                serialized = json.dumps(result, ensure_ascii=False, default=str)
                messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": serialized}
                )
                database.append_message(
                    self.conn,
                    self.session_id,
                    "tool",
                    serialized,
                    tool_call_id=call["id"],
                )

        fallback = (
            "Desculpe, tive um problema para concluir sua consulta agora. "
            "Posso te encaminhar para um atendente humano — quer que eu faça isso?"
        )
        database.append_message(self.conn, self.session_id, "assistant", fallback)
        return AgentReply(text=fallback, steps=steps, usage=usage_total, rounds=self.max_tool_rounds)
