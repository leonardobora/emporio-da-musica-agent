"""Command line interface: chat, run-scenario, run-all, history, rebuild."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import database, runner
from .agent import Agent
from .config import Config, REPO_ROOT
from .llm import DeepSeekClient, LLMError

BANNER = """\
Empório da Música — assistente virtual (protótipo)
modelo: {model} · sessão: {session}
Digite sua mensagem. 'sair' encerra, 'historico' mostra a sessão.
"""


def _prepare(cfg: Config):
    conn = database.connect(cfg.db_path)
    database.load_store(conn, cfg.data_dir)
    client = DeepSeekClient(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        model=cfg.model,
        temperature=cfg.temperature,
    )
    return conn, client


def cmd_chat(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    if args.model:
        cfg = cfg.__class__(**{**cfg.__dict__, "model": args.model})
    conn, client = _prepare(cfg)
    session_id = database.start_session(conn, client.model)
    if args.order:
        from . import datasource

        info = datasource.get_order(conn, args.order, args.phone or "")
        if info.get("found"):
            database.bind_customer(conn, session_id, _customer_of(conn, int(args.order)), int(args.order))
            print(f"[pedido #{args.order} verificado na sessão]")
        else:
            print(f"[aviso] pedido #{args.order} não pôde ser verificado; o agente vai pedir os dados")
    agent = Agent(client, conn, session_id)
    print(BANNER.format(model=client.model, session=session_id))
    while True:
        try:
            user_text = input("você › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_text:
            continue
        if user_text.lower() in {"sair", "exit", "quit"}:
            break
        if user_text.lower() in {"historico", "history"}:
            for row in database.history(conn, session_id):
                print(f"  [{row['role']}] {(row['content'] or '')[:160]}")
            continue
        try:
            reply = agent.reply(user_text)
        except LLMError as exc:
            print(f"[erro do provedor] {exc}")
            continue
        for step in reply.steps:
            print(f"  ⚙ {step.tool}({step.arguments})")
        print(f"\nempório › {reply.text}\n")
    print(f"sessão {session_id} encerrada.")
    return 0


def _customer_of(conn, order_id: int) -> int:
    row = conn.execute(
        "SELECT customer_id FROM store_orders WHERE order_id = ?", (order_id,)
    ).fetchone()
    return int(row["customer_id"]) if row else 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    if args.model:
        cfg = cfg.__class__(**{**cfg.__dict__, "model": args.model})
    conn, client = _prepare(cfg)
    scenarios = _scenario_paths(args.paths)
    if not scenarios:
        print("nenhum cenário encontrado")
        return 1
    failed = 0
    for path in scenarios:
        result = runner.run_scenario(path, client, conn, REPO_ROOT / "examples", write_transcript=True)
        status = "PASSOU" if result.passed else "FALHOU"
        print(f"{status} {result.scenario_id} — {result.title}")
        for check in result.checks:
            if not check.passed:
                print(f"    ✗ {check.name} {check.detail}")
                failed += 1
        if result.transcript_path:
            print(f"    → {result.transcript_path.relative_to(REPO_ROOT)}")
    return 1 if failed else 0


def _scenario_paths(paths: list[str]) -> list[Path]:
    directory = REPO_ROOT / "examples" / "scenarios"
    if not paths:
        return sorted(directory.glob("*.json"))
    result: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            result.extend(sorted(path.glob("*.json")))
        elif path.exists():
            result.append(path)
        else:
            for candidate in (directory / raw, directory / f"{raw}.json"):
                if candidate.exists():
                    result.append(candidate)
                    break
    return result


def cmd_history(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    conn = database.connect(cfg.db_path)
    rows = database.history(conn, args.session)
    if not rows:
        print("sessão vazia ou inexistente")
        return 1
    for row in rows:
        content = (row["content"] or "").replace("\n", " ")
        print(f"{row['id']:>3} {row['role']:<9} {content[:200]}")
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    conn = database.connect(cfg.db_path)
    database.load_store(conn, cfg.data_dir)
    counts = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in database.STORE_TABLES
    }
    print("dados recarregados:", counts)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="emporio", description="Assistente virtual da Empório da Música")
    parser.add_argument("--model", help="sobrescreve MODEL do .env")
    sub = parser.add_subparsers(dest="command", required=True)

    chat = sub.add_parser("chat", help="conversa interativa no terminal")
    chat.add_argument("--order", type=int, help="número do pedido para verificar no início da sessão")
    chat.add_argument("--phone", help="4 últimos dígitos do telefone (com --order)")
    chat.set_defaults(func=cmd_chat)

    run = sub.add_parser("run-scenario", help="executa cenários e grava transcrições em examples/")
    run.add_argument("paths", nargs="*", help="arquivos .json, diretório, ou nome do cenário")
    run.set_defaults(func=cmd_run)

    hist = sub.add_parser("history", help="mostra as mensagens de uma sessão")
    hist.add_argument("session")
    hist.set_defaults(func=cmd_history)

    rebuild = sub.add_parser("rebuild", help="recarrega os CSVs no SQLite e mostra as contagens")
    rebuild.set_defaults(func=cmd_rebuild)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
