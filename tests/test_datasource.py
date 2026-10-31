"""Facts about the provided data and the rules of ADR 0006 — no LLM involved."""

from __future__ import annotations

from datetime import date

import pytest

from emporio import database, datasource, policies


@pytest.fixture()
def conn(tmp_path):
    connection = database.connect(tmp_path / "test.sqlite")
    database.load_store(connection, __import__("pathlib").Path(__file__).parents[1] / "data")
    return connection


def test_format_brl_uses_brazilian_separators():
    assert datasource.format_brl(1234.5) == "R$ 1.234,50"
    assert datasource.format_brl(599.9) == "R$ 599,90"
    assert datasource.format_brl(6899.08) == "R$ 6.899,08"


def test_availability_is_status_and_stock(conn):
    out_of_stock = datasource.get_product(conn, 96)
    assert out_of_stock["status"] == "active" and out_of_stock["stock_quantity"] == 0
    assert out_of_stock["availability"]["sellable"] is False

    discontinued = datasource.get_product(conn, 113)
    assert discontinued["availability"]["state"] == "discontinued"

    coming_soon = datasource.get_product(conn, 130)
    assert coming_soon["availability"]["state"] == "coming_soon"
    assert coming_soon["availability"]["sellable"] is False


def test_only_four_promotions_are_active(conn):
    promos = datasource.list_active_promotions(conn)
    assert promos["count"] == 4
    assert {p["product_id"] for p in promos["promotions"]} == {90, 94, 121, 127}


def test_inactive_promotion_is_never_quoted(conn):
    # product 102 has a 10% Black Friday row with is_active = 0
    product = datasource.get_product(conn, 102)
    assert product["price"]["is_promotional"] is False
    assert product["price"]["price_brl"] == 3899


def test_active_promotion_is_applied_to_final_price(conn):
    taylor = datasource.get_product(conn, 94)
    assert taylor["price"]["is_promotional"] is True
    assert taylor["price"]["discount_percent"] == 8
    assert taylor["price"]["price_formatted"] == "R$ 5.519,08"
    assert taylor["price"]["original_price_formatted"] == "R$ 5.999,00"


def test_search_filters_on_effective_price_and_availability(conn):
    result = datasource.search_products(conn, category="violões", max_price=1000)
    assert result["count"] > 0
    ids = {p["product_id"] for p in result["products"]}
    assert 96 not in ids, "produto sem estoque não deve aparecer no filtro padrão"
    assert all(p["price"]["price_brl"] <= 1000 for p in result["products"])

    with_unavailable = datasource.search_products(
        conn, category="violões", max_price=1000, only_available=False, limit=50
    )
    assert 96 in {p["product_id"] for p in with_unavailable["products"]}


@pytest.mark.parametrize(
    ("price", "expected_installments"),
    [
        (40, 1),  # below R$ 50: no instalments
        (150, 3),  # 1–3x without minimum
        (480, 6),  # 4–6x, R$ 80 minimum
        (700, 7),  # 7x, R$ 100 minimum
        (1199, 11),  # floor(1199/100) = 11
        (1200, 12),
        (7499, 12),
    ],
)
def test_installment_rules_follow_section_31(price, expected_installments):
    options = datasource.payment_options(price)
    assert options["credit"]["max_installments"] == expected_installments


def test_pix_discount_never_stacks_on_promotional_price():
    promo = datasource.payment_options(6899.08, is_promotional=True)
    assert promo["pix"]["discount_percent"] == 0
    assert promo["pix"]["final_formatted"] == "R$ 6.899,08"

    regular = datasource.payment_options(1000, is_promotional=False)
    assert regular["pix"]["discount_percent"] == 5
    assert regular["pix"]["final_formatted"] == "R$ 950,00"


def test_mixed_payment_only_above_two_thousand():
    assert datasource.payment_options(1999)["mixed_payment"]["allowed"] is False
    assert datasource.payment_options(2001)["mixed_payment"]["allowed"] is True


def test_order_gate_requires_matching_phone_suffix(conn):
    found = datasource.get_order(conn, 2, "6543")
    assert found["found"] is True
    assert found["tracking_code"] == "BRCX9876543BR"

    wrong = datasource.get_order(conn, 2, "4321")
    assert wrong == datasource.NOT_FOUND

    missing_order = datasource.get_order(conn, 999, "6543")
    assert missing_order == datasource.NOT_FOUND

    # same generic answer, so the tool cannot be used to probe which ids exist
    assert wrong == missing_order


def test_order_gate_rejects_non_four_digit_input(conn):
    result = datasource.get_order(conn, 2, "65")
    assert result["found"] is False


def test_order_total_is_the_charged_value_not_the_item_sum(conn):
    # order 3: total 3450.00 vs 2 x 1749.00 = 3498.00
    order = datasource.get_order(conn, 3, "9012")
    assert order["found"] is True
    assert order["total_formatted"] == "R$ 3.450,00"


def test_return_windows_are_closed_for_old_orders(conn):
    order = datasource.get_order(conn, 1, "1098", today=date(2026, 10, 31))
    windows = order["return_windows"]
    assert windows["right_of_withdrawal"]["open"] is False
    assert windows["defect_exchange"]["open"] is False
    assert windows["right_of_withdrawal"]["deadline"] == "2025-11-01"


def test_return_window_is_open_before_deadline(conn):
    order = datasource.get_order(conn, 1, "1098", today=date(2025, 10, 27))
    assert order["return_windows"]["right_of_withdrawal"]["open"] is True
    assert order["return_windows"]["right_of_withdrawal"]["days_remaining"] == 5


def test_historical_order_with_coming_soon_product_still_answers(conn):
    order = datasource.get_order(conn, 3, "9012")
    item = order["items"][0]
    assert item["current_status"] == "coming_soon"
    assert item["quantity"] == 2


def test_policy_sections_are_extractable():
    assert "parcela mínima de R$ 80,00" in policies.get_policy("3.1")["text"]
    assert "não se aplica sobre" in policies.get_policy("6.2")["text"]
    assert "4.1" in policies.get_policy("4")["text"]
    assert policies.get_policy("99")["found"] is False
