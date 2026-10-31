# Order lookups are gated by the phone's last four digits

## Status

accepted

## Context

`get_order` is the one tool that can leak personal data: `orders` joins to `customers` (name, phone,
e-mail, city) and four orders carry notes about the customer. The provided data makes name-based lookup
actively dangerous — `bruno.martins@jmail.com` is on two customer rows (11 and 43), and short names repeat
across the catalogue of customers (`Thiago Barbosa Lima` vs `Thiago Costa`, `Lucas Mendes da Silva` vs
`Beatriz Mendes`). A "find my order by name" path would, with high probability, hand one customer
another's order.

The internal manual also binds the agent to LGPD (§9) — data used only for order processing and status
communication.

## Decision

An order is only readable after **order id + the last four digits of the phone on file** both match the
same order. Failures are answered in the same way regardless of which part failed ("não encontrei esse
pedido com esses dados"), so the tool cannot be used to discover whether an order id exists.

## Considered options

- **Order id alone.** Rejected: order ids are `1..20` and trivially guessable — a customer asking about
  "pedido 7" would get someone else's name, city and purchase.
- **Name + surname, or full phone, or e-mail.** Rejected as unnecessary: the last four digits already give
  ~10^4 combinations over 50 customers, are what the customer can recall without the invoice, and keep the
  demo conversation short. Full name matching also has the duplicate-name problem.
- **No gate.** Rejected outright: it is the failure this case is designed to catch.

## Consequences

- The agent must ask for two pieces of information before answering any order-status question; the
  transcripts show it doing so, including the "wrong digits" path.
- Everything the model sees about a customer is the fields it needs for the answer (first name, order
  status, items, tracking, dates) — never the full customer row.
