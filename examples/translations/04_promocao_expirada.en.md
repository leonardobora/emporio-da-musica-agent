# 04 — Expired promotion, current price, instalments (English translation)

> Translation of [`../04_promocao_expirada.md`](../04_promocao_expirada.md). The PT-BR file is the record of
> the actual run. Tool calls and results are unchanged.

**Run:** `deepseek-chat` · session `eb43b60cd7dc` · 2026-11-01T00:00:43Z

---

**Customer:** I saw a 30% promotion on the Taylor 110e last week. Is it still valid?

`list_active_promotions({})`
`get_product({"product_id_or_name": "Taylor 110e"})`

**Agent:** That 30% promotion is over. What is active on the Taylor 110e Dreadnought Natural today is an 8% discount:

• From R$ 5,999.00 for R$ 5,519.08
• 4 units in stock

Just a reminder that the 5% PIX discount does not stack on a promotional price (§6.2). Want me to check the instalment terms?

---

**Customer:** And what would the price be with the discount valid today? How much in 12 instalments?

`payment_options({"product_id": 94})`

**Agent:** The price with today's active discount is R$ 5,519.08 (8% off R$ 5,999.00).

On a credit card it comes to 12 interest-free instalments of R$ 459.92.

On PIX the amount is the same R$ 5,519.08, because the 5% discount does not stack on a promotional price (§6.2). Bank slip and debit also come to R$ 5,519.08 in cash.

Want me to set one aside for you, or can I help with anything else?

**Why this scenario exists:** 21 of the 25 promotions in the dataset have `is_active = 0`. Quoting a discount row without checking the flag is exactly the failure this case plants — §7.3 forbids promising a promotion that is no longer running. The 12 instalments are computed by the tool (§3.1 minimum-instalment rules), never by the model.
