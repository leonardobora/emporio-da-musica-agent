"""Pure functions over the store data.

Every fact the agent is allowed to state about price, stock, promotions, orders or payment terms
comes from here. No LLM arithmetic, no guessing: the rules of ADR 0006 live in this file.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta

STATUS_MEANING = {
    "pending": "aguardando confirmação de pagamento",
    "confirmed": "pagamento confirmado, aguardando separação para envio",
    "shipped": "enviado, em transporte",
    "delivered": "entregue",
    "cancelled": "cancelado",
}

ACTIVE = "active"
DISCONTINUED = "discontinued"
COMING_SOON = "coming_soon"


def format_brl(value: float) -> str:
    """R$ 1.234,56 — pt-BR formatting, always two decimals."""
    text = f"{value:,.2f}"  # 1,234.56
    text = text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"R$ {text}"


def _today() -> date:
    return date.today()


# --- promotions & pricing ----------------------------------------------------------


def active_promotion(conn: sqlite3.Connection, product_id: int) -> dict | None:
    """Best *active* promotion for a product, or None.

    Rows with is_active = 0 are expired and must never be quoted (ADR 0006, rule 4).
    When several active rows exist, the highest discount wins and the choice is returned so it
    can be logged.
    """
    row = conn.execute(
        """SELECT promotion_id, discount_percent, description
           FROM store_promotions
           WHERE product_id = ? AND is_active = 1
           ORDER BY discount_percent DESC, promotion_id ASC
           LIMIT 1""",
        (product_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "promotion_id": row["promotion_id"],
        "discount_percent": row["discount_percent"],
        "label": row["description"],
    }


def price_view(conn: sqlite3.Connection, product_id: int, list_price: float) -> dict:
    promo = active_promotion(conn, product_id)
    if not promo:
        return {
            "price_brl": list_price,
            "price_formatted": format_brl(list_price),
            "original_price_brl": None,
            "discount_percent": None,
            "promotion": None,
            "is_promotional": False,
        }
    factor = 1 - promo["discount_percent"] / 100
    final = round(list_price * factor, 2)
    return {
        "price_brl": final,
        "price_formatted": format_brl(final),
        "original_price_brl": list_price,
        "original_price_formatted": format_brl(list_price),
        "discount_percent": promo["discount_percent"],
        "promotion": promo["label"],
        "is_promotional": True,
    }


def _product_row(row: sqlite3.Row) -> dict:
    specs = {}
    if row["specs"]:
        try:
            specs = json.loads(row["specs"])
        except json.JSONDecodeError:
            specs = {"raw": row["specs"]}
    return {
        "product_id": row["product_id"],
        "name": row["name"],
        "category": row["category_name"],
        "status": row["status"],
        "stock_quantity": row["stock_quantity"],
        "list_price_brl": row["price_brl"],
        "description": row["description"],
        "specs": specs,
        "created_at": row["created_at"],
    }


def availability(row_or_product: dict) -> dict:
    """Availability is status='active' AND stock>0 — never stock alone (ADR 0006, rule 3)."""
    status = row_or_product["status"]
    stock = row_or_product["stock_quantity"]
    if status == ACTIVE and stock > 0:
        state, message = "available", f"disponível em estoque ({stock} unidade(s))"
    elif status == ACTIVE and stock == 0:
        state, message = "out_of_stock", "temporariamente sem estoque"
    elif status == COMING_SOON:
        state, message = "coming_soon", "ainda não disponível, sem data de chegada confirmada"
    else:
        state, message = "discontinued", "fora do catálogo (produto descontinuado)"
    return {"state": state, "sellable": state == "available", "message": message}


def search_products(
    conn: sqlite3.Connection,
    query: str | None = None,
    category: str | None = None,
    max_price: float | None = None,
    min_price: float | None = None,
    only_available: bool = True,
    limit: int = 8,
) -> dict:
    """Search the catalogue. Price filters compare the *effective* price (promotion applied)."""
    clauses, params = [], []
    if category:
        clauses.append("(LOWER(category_name) LIKE ? OR LOWER(name) LIKE ?)")
        params += [f"%{category.lower()}%", f"%{category.lower()}%"]
    if query:
        # every token must appear somewhere in name/description/specs
        for token in [t for t in query.lower().split() if len(t) > 2]:
            clauses.append("LOWER(name || ' ' || description || ' ' || specs) LIKE ?")
            params.append(f"%{token}%")
    if only_available:
        clauses.append("status = 'active' AND stock_quantity > 0")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(f"SELECT * FROM store_products {where} ORDER BY price_brl", params).fetchall()

    results = []
    for row in rows:
        product = _product_row(row)
        price = price_view(conn, row["product_id"], row["price_brl"])
        effective = price["price_brl"]
        if max_price is not None and effective > max_price:
            continue
        if min_price is not None and effective < min_price:
            continue
        product["price"] = price
        product["availability"] = availability(product)
        results.append(product)

    total = len(results)
    results = results[:limit]
    return {
        "count": total,
        "returned": len(results),
        "only_available_filter": only_available,
        "products": results,
        "note": (
            "Filtro de disponibilidade ativo: produtos sem estoque, em breve ou descontinuados "
            "não aparecem. Refine a busca ou use get_product para checar um item específico."
        ),
    }


def _match_product(conn: sqlite3.Connection, ref: str | int) -> sqlite3.Row | None:
    ref_str = str(ref).strip()
    if ref_str.isdigit():
        row = conn.execute(
            "SELECT * FROM store_products WHERE product_id = ?", (int(ref_str),)
        ).fetchone()
        if row:
            return row
    row = conn.execute(
        "SELECT * FROM store_products WHERE LOWER(name) = ?", (ref_str.lower(),)
    ).fetchone()
    if row:
        return row
    return conn.execute(
        "SELECT * FROM store_products WHERE LOWER(name) LIKE ? ORDER BY LENGTH(name) LIMIT 1",
        (f"%{ref_str.lower()}%",),
    ).fetchone()


def get_product(conn: sqlite3.Connection, product_id_or_name: str | int) -> dict:
    row = _match_product(conn, product_id_or_name)
    if not row:
        return {"found": False, "query": product_id_or_name}
    product = _product_row(row)
    product["price"] = price_view(conn, row["product_id"], row["price_brl"])
    product["availability"] = availability(product)
    product["found"] = True
    return product


def check_availability(conn: sqlite3.Connection, product_id: int) -> dict:
    row = _match_product(conn, product_id)
    if not row:
        return {"found": False, "query": product_id}
    product = _product_row(row)
    return {
        "found": True,
        "product_id": product["product_id"],
        "name": product["name"],
        "status": product["status"],
        "stock_quantity": product["stock_quantity"],
        **availability(product),
    }


def list_active_promotions(conn: sqlite3.Connection, category: str | None = None) -> dict:
    rows = conn.execute(
        """SELECT p.product_id, p.discount_percent, p.description AS promotion,
                  s.name, s.price_brl, s.stock_quantity, s.status, s.category_name
           FROM store_promotions p JOIN store_products s ON s.product_id = p.product_id
           WHERE p.is_active = 1
           ORDER BY p.discount_percent DESC"""
    ).fetchall()
    promos = []
    for row in rows:
        if category and category.lower() not in (row["category_name"] or "").lower():
            continue
        final = round(row["price_brl"] * (1 - row["discount_percent"] / 100), 2)
        promos.append(
            {
                "product_id": row["product_id"],
                "name": row["name"],
                "category": row["category_name"],
                "promotion": row["promotion"],
                "discount_percent": row["discount_percent"],
                "original_price_formatted": format_brl(row["price_brl"]),
                "promotional_price_formatted": format_brl(final),
                "sellable": row["status"] == ACTIVE and row["stock_quantity"] > 0,
            }
        )
    return {
        "count": len(promos),
        "scope": "somente promoções ativas hoje",
        "promotions": promos,
    }


# --- payment terms (§3 and §3.1 of the manual) -------------------------------------


def payment_options(price_brl: float, is_promotional: bool = False) -> dict:
    """Payment terms from the manual, computed in code so the model never does arithmetic.

    §3.1: up to 3x without a minimum (except purchases below R$ 50), 4x–6x with an R$ 80 minimum
    instalment, 7x–12x with an R$ 100 minimum instalment.
    """
    price = round(float(price_brl), 2)
    if price < 50:
        max_installments = 1
    elif price >= 1200:
        max_installments = 12
    elif price >= 700:
        max_installments = min(11, int(price // 100))
    elif price >= 480:
        max_installments = 6
    elif price >= 320:
        max_installments = min(5, int(price // 80))
    else:
        max_installments = 3

    installment = round(price / max_installments, 2) if max_installments > 1 else price
    pix_discount = 0.0 if is_promotional else round(price * 0.05, 2)

    return {
        "price_formatted": format_brl(price),
        "is_promotional": is_promotional,
        "pix": {
            "available": True,
            "discount_percent": 0 if is_promotional else 5,
            "discount_formatted": format_brl(pix_discount),
            "final_formatted": format_brl(round(price - pix_discount, 2)),
            "note": (
                "O desconto de 5% do PIX não se acumula com preço promocional (§6.2)."
                if is_promotional
                else "5% de desconto para pagamento à vista via PIX (§3)."
            ),
        },
        "debit": {"available": True, "final_formatted": format_brl(price), "note": "à vista, todas as bandeiras"},
        "credit": {
            "available": max_installments > 1,
            "max_installments": max_installments,
            "installment_formatted": format_brl(installment),
            "note": (
                f"até {max_installments}x sem juros"
                if max_installments > 1
                else "parcelamento não disponível nesta faixa de preço (§3.1)"
            ),
        },
        "boleto": {
            "available": True,
            "final_formatted": format_brl(price),
            "note": "à vista, compensação em até 3 dias úteis",
        },
        "mixed_payment": {
            "allowed": price > 2000,
            "note": "combinação de formas permitida para compras acima de R$ 2.000,00 (§3.1)",
        },
    }


# --- orders ------------------------------------------------------------------------

def _last4(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits[-4:]


def _order_items(conn: sqlite3.Connection, order_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT i.product_id, i.quantity, p.name, p.price_brl, p.status, p.category_name
           FROM store_order_items i JOIN store_products p ON p.product_id = i.product_id
           WHERE i.order_id = ?""",
        (order_id,),
    ).fetchall()
    return [
        {
            "product_id": r["product_id"],
            "name": r["name"],
            "category": r["category_name"],
            "quantity": r["quantity"],
            "unit_price_formatted": format_brl(r["price_brl"]),
            "line_total_formatted": format_brl(r["price_brl"] * r["quantity"]),
            "current_status": r["status"],
        }
        for r in rows
    ]


def _window(anchor: str | None, days: int, today: date) -> dict:
    if not anchor:
        return {"deadline": None, "open": None, "note": "não é possível calcular sem data de referência"}
    try:
        start = datetime.strptime(anchor, "%Y-%m-%d").date()
    except ValueError:
        return {"deadline": None, "open": None, "note": "data de referência inválida"}
    deadline = start + timedelta(days=days)
    left = (deadline - today).days
    return {
        "anchor": anchor,
        "deadline": deadline.isoformat(),
        "open": left >= 0,
        "days_remaining": max(left, 0),
        "note": f"prazo de {days} dias contado de {anchor}",
    }


NOT_FOUND = {"found": False, "error": "pedido não localizado com os dados informados"}


def get_order(conn: sqlite3.Connection, order_id: int | str, phone_last4: str, today: date | None = None) -> dict:
    """Order lookup behind the identity gate: order id + last four digits of the phone on file.

    Any mismatch returns the same generic answer, so the tool cannot be used to probe which
    order ids exist (ADR 0005).
    """
    today = today or _today()
    try:
        oid = int(str(order_id).strip().lstrip("#"))
    except (TypeError, ValueError):
        return NOT_FOUND
    digits = "".join(ch for ch in str(phone_last4 or "") if ch.isdigit())[-4:]
    if len(digits) != 4:
        return {"found": False, "error": "informe os quatro últimos dígitos do telefone cadastrado"}

    order = conn.execute("SELECT * FROM store_orders WHERE order_id = ?", (oid,)).fetchone()
    if not order:
        return NOT_FOUND
    customer = conn.execute(
        "SELECT customer_id, name, phone, city FROM store_customers WHERE customer_id = ?",
        (order["customer_id"],),
    ).fetchone()
    if not customer or _last4(customer["phone"]) != digits:
        return NOT_FOUND

    items = _order_items(conn, oid)
    status = order["status"]
    reference_delivery = order["estimated_delivery"] if status == "delivered" else None

    return {
        "found": True,
        "order_id": order["order_id"],
        "customer_first_name": customer["name"].split()[0],
        "customer_city": customer["city"],
        "status": status,
        "status_meaning": STATUS_MEANING.get(status, status),
        "order_date": order["order_date"],
        "payment_method": order["payment_method"],
        "total_formatted": format_brl(order["total_brl"]),
        "total_brl": order["total_brl"],
        "items": items,
        "tracking_code": order["tracking_code"] or None,
        "estimated_delivery": order["estimated_delivery"] or None,
        "notes": order["notes"] or None,
        "return_windows": {
            "right_of_withdrawal": _window(reference_delivery, 7, today),
            "defect_exchange": _window(order["order_date"], 30, today),
            "note": (
                "Arrependimento (§4.1) conta do recebimento e só existe para compras online; "
                "defeito (§4.2) conta da compra. Garantia legal de 90 dias (§8.1) é distinta."
            ),
        },
        "data_note": "total do pedido é o valor cobrado; não recalcule a partir dos itens",
    }


def store_info() -> dict:
    """Static store information from the manual (§1.2, §2, §7)."""
    return {
        "name": "Empório da Música",
        "tagline": "Sua música começa aqui.",
        "address": "Rua 14 de Maio, 3200 — Centro, Campo Grande-MS, 79202-333",
        "phone_whatsapp": "(67) 3341-4444",
        "whatsapp_support": "(67) 3321-4500",
        "email": "contato@emporiodamusica.com.br",
        "founded": 2008,
        "hours": {
            "monday_to_friday": "09:00–18:00",
            "saturday": "09:00–13:00",
            "sunday_and_holidays": "fechado",
            "note": "atendimento por WhatsApp segue o mesmo horário, com respostas automáticas fora do expediente",
        },
        "scope": (
            "a loja trabalha exclusivamente com instrumentos musicais; não comercializa acessórios "
            "(cordas, palhetas, cabos, cases, pedais, amplificadores)"
        ),
        "delivery": {
            "campo_grande_metro": "frete grátis acima de R$ 500,00; R$ 35,00 abaixo disso; 1 a 3 dias úteis por motoboy",
            "other_cities": "Correios PAC (5–12 dias úteis), SEDEX (2–5 dias úteis) ou Jadlog (3–8 dias úteis)",
        },
        "human_handoff": {
            "contact": "(67) 3341-4444",
            "sla": "retorno em até 24 horas úteis para reclamações registradas (§7.3)",
        },
    }
