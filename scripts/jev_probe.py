#!/usr/bin/env python3
"""Probe: could a local System-1 typed decider replace or pre-route the LLM in this agent?

It reads the customer turns this agent has actually logged (emporio.sqlite), builds ground truth from
the tool calls the agent made for each turn, then asks a local decision model — Decision-Jef-0.1,
served at http://127.0.0.1:8088/v1/systemone — the two questions a router would need:

  1. does this message need live store data?
  2. should this message go to a human?

Results are compared against the majority-class baseline, because "62% accuracy" means nothing without it.

Usage:
    python scripts/jev_probe.py                       # uses ./emporio.sqlite
    python scripts/jev_probe.py --db path.sqlite --url http://127.0.0.1:8088/v1/systemone
    python scripts/jev_probe.py --variant literal     # stricter criteria (variant B of the write-up)

Requires the decision model to be running locally; see docs/notes/05-jev-router-experiment.md.
Exit code 0 = probe ran; it does not fail on bad accuracy (bad accuracy is the finding).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Tools that mean "the answer needed the store's live data".
DATA_TOOLS = {
    "search_products",
    "get_product",
    "check_availability",
    "list_active_promotions",
    "payment_options",
    "get_order",
}

QUESTIONS = {
    "generic": {
        "needs_store_data": {
            "type": "noul",
            "instructions": "Does a correct answer to this message require live data from the store database?",
            "criteria": {
                "false": "answerable from static knowledge: opening hours, address, policy text, small talk",
                "true": "requires current price, stock, promotion state, or the customer's own order record",
            },
        },
        "should_escalate": {
            "type": "noul",
            "instructions": "Should this message be handed to a human attendant instead of answered by the bot?",
            "criteria": {
                "false": "a normal question the bot can answer",
                "true": "complaint, exception to policy, price negotiation, legal threat, or explicit request for a human",
            },
        },
    },
    "literal": {
        "needs_store_data": {
            "type": "noul",
            "instructions": (
                "Decide if this customer message needs a database lookup before it can be answered. "
                "Look for literal signals in the message."
            ),
            "criteria": {
                "false": (
                    "the message contains no product name, no product id, no order number, no price, no stock "
                    "question and no promotion question. Greetings, thanks, opening hours, address, general "
                    "policy questions and complaints fit here."
                ),
                "true": (
                    "the message names a product or model, gives an order number, asks a specific price, asks "
                    "whether something is in stock, or asks about a specific promotion"
                ),
            },
        }
    },
}


def load_turns(db_path: Path, channel: str = "scenario") -> tuple[dict[str, set[str]], int]:
    """Map each distinct customer message to the tools the agent called while answering it."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = list(
        conn.execute(
            """SELECT session_id, id, role, content, tool_calls FROM messages
               WHERE session_id IN (SELECT session_id FROM sessions WHERE channel = ?)
               ORDER BY session_id, id""",
            (channel,),
        )
    )
    turns: dict[str, set[str]] = {}
    total = 0
    index = 0
    while index < len(rows):
        row = rows[index]
        if row["role"] != "user":
            index += 1
            continue
        total += 1
        tools: set[str] = set()
        cursor = index + 1
        while (
            cursor < len(rows)
            and rows[cursor]["session_id"] == row["session_id"]
            and rows[cursor]["role"] != "user"
        ):
            if rows[cursor]["tool_calls"]:
                tools.update(t["function"]["name"] for t in json.loads(rows[cursor]["tool_calls"]))
            cursor += 1
        turns.setdefault(row["content"], set()).update(tools)
        index = cursor
    return turns, total


def ask(url: str, state: str, questions: dict) -> tuple[dict, float]:
    body = json.dumps({"state": state, "questions": questions}).encode()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return payload["answers"], (time.perf_counter() - started) * 1000


def confusion(pairs: list[tuple[bool, bool]]) -> dict:
    tp = sum(1 for predicted, truth in pairs if predicted and truth)
    fp = sum(1 for predicted, truth in pairs if predicted and not truth)
    tn = sum(1 for predicted, truth in pairs if not predicted and not truth)
    fn = sum(1 for predicted, truth in pairs if not predicted and truth)
    n = len(pairs) or 1
    return {
        "accuracy": (tp + tn) / n,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


LITERAL_PATTERNS = {
    "order_id": r"\bpedido\s*#?\s*\d+|#\s*\d+",
    "phone4": r"\b\d{4}\b",
    "hours": r"\b(hor[áa]rio|horas|abre|abrem|fecha|fecham|funciona)",
    "address": r"\b(endere[çc]o|onde fica|onde voc|localiza)",
    "price": r"\br\$\s*\d|\bat[ée] r\$|at[ée]\s*\d{3,}",
    "promotion": r"\b(promo[çc][ãa]o|desconto|oferta|liquida)",
    "accessory": r"\b(acess[óo]rio|corda|palheta|cabo|case|pedal|amplificador)",
    "human": r"\b(humano|atendente|gerente|reclama|procon|advogado)",
}


def literal_signals(message: str) -> list[str]:
    lowered = message.lower()
    return [name for name, pattern in LITERAL_PATTERNS.items() if re.search(pattern, lowered)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "emporio.sqlite")
    parser.add_argument("--url", default="http://127.0.0.1:8088/v1/systemone")
    parser.add_argument("--variant", choices=sorted(QUESTIONS), default="generic")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--channel", default="scenario")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"banco não encontrado: {args.db}\nrode antes: python -m emporio run-scenario", file=sys.stderr)
        return 2

    turns, total_turns = load_turns(args.db, args.channel)
    distinct = len(turns)
    if not distinct:
        print("nenhum turno de cliente no banco", file=sys.stderr)
        return 2
    print(f"turnos logados: {total_turns} · mensagens distintas: {distinct} · variante: {args.variant}\n")

    questions = QUESTIONS[args.variant]
    data_pairs, esc_pairs, latencies = [], [], []
    errors = []
    for message, tools in turns.items():
        try:
            answers, latency = ask(args.url, message, questions)
        except (urllib.error.URLError, ConnectionError) as exc:
            print(
                f"decisor não respondeu em {args.url}: {exc}\n"
                "suba o serviço (systemctl --user start decision-jef.service) ou aponte --url",
                file=sys.stderr,
            )
            return 2
        latencies.append(latency)

        predicted_data = answers["needs_store_data"]["noul"] >= args.threshold
        truth_data = bool(tools & DATA_TOOLS)
        data_pairs.append((predicted_data, truth_data))
        if predicted_data != truth_data:
            errors.append(
                (message[:58], round(answers["needs_store_data"]["noul"], 2), truth_data)
            )

        if "should_escalate" in answers:
            predicted_esc = answers["should_escalate"]["noul"] >= args.threshold
            truth_esc = "escalate_to_human" in tools
            esc_pairs.append((predicted_esc, truth_esc))

    data = confusion(data_pairs)
    truth_rate = sum(1 for _, truth in data_pairs if truth) / distinct
    print("needs_store_data")
    print(
        f"  acurácia {data['accuracy']:.0%} · precisão {data['precision']:.0%} · recall {data['recall']:.0%}"
        f" · tp={data['tp']} fp={data['fp']} tn={data['tn']} fn={data['fn']}"
    )
    print(f"  baseline 'sempre true': {truth_rate:.0%}")

    if esc_pairs:
        esc = confusion(esc_pairs)
        esc_rate = sum(1 for _, truth in esc_pairs if truth) / len(esc_pairs)
        print("should_escalate")
        print(
            f"  acurácia {esc['accuracy']:.0%} · precisão {esc['precision']:.0%} · recall {esc['recall']:.0%}"
            f" · tp={esc['tp']} fp={esc['fp']} tn={esc['tn']} fn={esc['fn']}"
        )
        print(f"  baseline 'sempre false': {1 - esc_rate:.0%}")

    latencies.sort()
    print(
        f"\nlatência do decisor: p50 {latencies[len(latencies) // 2]:.0f} ms · max {latencies[-1]:.0f} ms"
    )

    if errors:
        print("\nerros do decisor (mensagem, probabilidade, verdade):")
        for message, probability, truth in errors:
            print(f"  {message!r} → {probability} (verdade: {'dados' if truth else 'sem dados'})")

    covered = sum(1 for message in turns if literal_signals(message))
    print(
        f"\nsinal literal (regex) presente em {covered}/{distinct} mensagens distintas "
        f"({covered / distinct:.0%}) — esses turnos um roteador determinístico resolve sem modelo"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
