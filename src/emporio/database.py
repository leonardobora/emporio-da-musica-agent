"""SQLite storage: the store's read-only catalogue and the writable session log."""

from __future__ import annotations

import csv
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

STORE_TABLES = (
    "store_categories",
    "store_products",
    "store_customers",
    "store_orders",
    "store_order_items",
    "store_promotions",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS store_categories (
    category_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);
CREATE TABLE IF NOT EXISTS store_products (
    product_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category_id INTEGER NOT NULL,
    category_name TEXT NOT NULL,
    price_brl REAL NOT NULL,
    stock_quantity INTEGER NOT NULL,
    status TEXT NOT NULL,
    description TEXT,
    specs TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS store_customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT,
    city TEXT
);
CREATE TABLE IF NOT EXISTS store_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date TEXT NOT NULL,
    status TEXT NOT NULL,
    total_brl REAL NOT NULL,
    payment_method TEXT,
    tracking_code TEXT,
    estimated_delivery TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS store_order_items (
    order_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    PRIMARY KEY (order_id, product_id)
);
CREATE TABLE IF NOT EXISTS store_promotions (
    promotion_id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL,
    discount_percent REAL NOT NULL,
    description TEXT,
    is_active INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    model TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'cli'
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    role TEXT NOT NULL,
    content TEXT,
    tool_calls TEXT,
    tool_call_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
CREATE TABLE IF NOT EXISTS session_customer (
    session_id TEXT PRIMARY KEY REFERENCES sessions(session_id),
    customer_id INTEGER NOT NULL,
    order_id INTEGER,
    verified_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS handoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_csv(data_dir: Path, name: str) -> list[dict[str, str]]:
    path = data_dir / name
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def connect(db_path: Path | str) -> sqlite3.Connection:
    db_path = Path(db_path)
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def load_store(conn: sqlite3.Connection, data_dir: Path) -> None:
    """(Re)build the read-only store tables from the provided CSVs. Idempotent."""
    data_dir = Path(data_dir)
    categories = {row["category_id"]: row for row in _read_csv(data_dir, "categories.csv")}

    for table in STORE_TABLES:
        conn.execute(f"DELETE FROM {table}")

    conn.executemany(
        "INSERT INTO store_categories (category_id, name, description) VALUES (?, ?, ?)",
        [(int(c["category_id"]), c["name"], c["description"]) for c in categories.values()],
    )

    products = _read_csv(data_dir, "products.csv")
    conn.executemany(
        """INSERT INTO store_products
           (product_id, name, category_id, category_name, price_brl, stock_quantity, status,
            description, specs, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                int(p["product_id"]),
                p["name"],
                int(p["category_id"]),
                categories.get(p["category_id"], {}).get("name", "Sem categoria"),
                float(p["price_brl"]),
                int(p["stock_quantity"]),
                p["status"],
                p["description"],
                p["specs"],
                p["created_at"],
            )
            for p in products
        ],
    )

    customers = _read_csv(data_dir, "customers.csv")
    conn.executemany(
        "INSERT INTO store_customers (customer_id, name, phone, email, city) VALUES (?, ?, ?, ?, ?)",
        [(int(c["customer_id"]), c["name"], c["phone"], c["email"], c["city"]) for c in customers],
    )

    orders = _read_csv(data_dir, "orders.csv")
    conn.executemany(
        """INSERT INTO store_orders
           (order_id, customer_id, order_date, status, total_brl, payment_method, tracking_code,
            estimated_delivery, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                int(o["order_id"]),
                int(o["customer_id"]),
                o["order_date"],
                o["status"],
                float(o["total_brl"]),
                o["payment_method"],
                o["tracking_code"],
                o["estimated_delivery"],
                o["notes"],
            )
            for o in orders
        ],
    )

    items = _read_csv(data_dir, "order_items.csv")
    conn.executemany(
        "INSERT INTO store_order_items (order_id, quantity, product_id) VALUES (?, ?, ?)",
        [(int(i["order_id"]), int(i["quantity"]), int(i["product_id"])) for i in items],
    )

    promotions = _read_csv(data_dir, "promotions.csv")
    conn.executemany(
        """INSERT INTO store_promotions
           (promotion_id, product_id, discount_percent, description, is_active)
           VALUES (?, ?, ?, ?, ?)""",
        [
            (
                int(p["promotion_id"]),
                int(p["product_id"]),
                float(p["discount_percent"]),
                p["description"],
                int(p["is_active"]),
            )
            for p in promotions
        ],
    )
    conn.commit()


# --- session log -------------------------------------------------------------------


def start_session(conn: sqlite3.Connection, model: str, channel: str = "cli") -> str:
    session_id = uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO sessions (session_id, started_at, model, channel) VALUES (?, ?, ?, ?)",
        (session_id, _now(), model, channel),
    )
    conn.commit()
    return session_id


def append_message(
    conn: sqlite3.Connection,
    session_id: str,
    role: str,
    content: str | None = None,
    tool_calls: list[dict] | None = None,
    tool_call_id: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO messages (session_id, role, content, tool_calls, tool_call_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            role,
            content,
            json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
            tool_call_id,
            _now(),
        ),
    )
    conn.commit()


def history(conn: sqlite3.Connection, session_id: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
        )
    )


def bind_customer(
    conn: sqlite3.Connection, session_id: str, customer_id: int, order_id: int | None
) -> None:
    conn.execute(
        """INSERT INTO session_customer (session_id, customer_id, order_id, verified_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(session_id) DO UPDATE SET
             customer_id = excluded.customer_id,
             order_id = excluded.order_id,
             verified_at = excluded.verified_at""",
        (session_id, customer_id, order_id, _now()),
    )
    conn.commit()


def get_bound_order(conn: sqlite3.Connection, session_id: str) -> int | None:
    row = conn.execute(
        "SELECT order_id FROM session_customer WHERE session_id = ?", (session_id,)
    ).fetchone()
    return row["order_id"] if row and row["order_id"] is not None else None


def record_handoff(conn: sqlite3.Connection, session_id: str, reason: str) -> int:
    cur = conn.execute(
        "INSERT INTO handoffs (session_id, reason, created_at) VALUES (?, ?, ?)",
        (session_id, reason, _now()),
    )
    conn.commit()
    return int(cur.lastrowid or 0)
