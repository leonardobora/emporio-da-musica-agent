# Data audit (as provided, before any cleaning)

Measured with plain Python over `data/*.csv` on 2026-10-31. These are facts about the files, not
decisions — decisions live in `docs/adr/`.

## Shape

| File | Rows | Notes |
|---|---|---|
| `products.csv` | 65 | `product_id` 81–145, `specs` is a JSON string column |
| `categories.csv` | 9 | only 6 of 9 categories have any product |
| `customers.csv` | 50 | `customer_id` 1–50, no CPF, no address, `city` only |
| `orders.csv` | 20 | 2025-10-15 … 2026-03-22, 7 delivered / 1 shipped / 4 confirmed / 4 pending / 4 cancelled |
| `order_items.csv` | 22 | one row per (order, product); order 3 has quantity 2 |
| `promotions.csv` | 25 | only **4** rows have `is_active = 1` |

## Quirks that shape the agent

1. **Promotions are mostly dead.** 21 of 25 promotions are inactive. An agent that reads
   `discount_percent` without checking `is_active` will promise discounts the store no longer honours —
   directly against §7.3 ("nunca prometer um desconto que não está mais vigente").
   Active: p127 −10%, p121 −20%, p90 −18%, p94 −8%.
2. **Duplicate promotion rows** for the same product: 99 (8% and 14%), 96 (18% and 40%), 93 (15% and 10%).
   All inactive today; the rule for picking one still has to be defined.
3. **Product lifecycle, not just stock.** `status` ∈ {active: 62, discontinued: 2, coming_soon: 1}.
   `stock_quantity = 0` for 96 (Giannini GF-3D, active) and 113 (Shelby SN-7C, discontinued).
   "Available" is therefore a conjunction: active **and** stock > 0.
4. **Categories advertised but empty.** The manual says the store sells wind instruments and orchestral
   strings (categories 6, 7, 8) — the catalog has zero products there. Agent must not invent entries.
   The manual's "300+ instruments" claim also exceeds the 65 rows: the agent should speak about the
   catalog it can actually verify.
5. **Order totals disagree with items.** Order 3: total 3450.00 vs items 2 × 1749.00 = 3498.00.
   Order 20: total 1400.00 vs items 799.00 + 689.00 = 1488.00. Every other order reconciles.
   Which number is authoritative is a decision, not a fact.
6. **A `coming_soon` product was sold.** Orders 3 and 14 both contain product 130 (Kala KA-ABP-CTG,
   `coming_soon`), one of them delivered. Historical orders must be answered from the order record,
   never re-derived from current product status.
7. **Orders are old.** Latest order date is 2026-03-22; "today" is 2026-10. Every 7-day return window
   (arrependimento) and every 30-day defect window from these orders is already closed — a policy answer
   must be computed against the order date, and the agent has to be able to say "this window is over".
8. **Ambiguous customer identity.** Names repeat in fragments (Thiago Barbosa Lima vs Thiago Costa;
   Lucas Mendes da Silva vs Larissa Mendes vs Beatriz Mendes). Emails: `bruno.martins@jmail.com` is used
   by two customer rows (11, 43). There is no order lookup key other than `order_id`, name, phone, email.
9. **Statuses have customer-visible semantics** and two of them (pending, cancelled) carry `notes`
   explaining why; `tracking_code` and `estimated_delivery` are empty until `shipped`.
10. **Prices are BRL floats**, range 159.90 – 19,567.00; `specs` needs `json.loads` per product.
