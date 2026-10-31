# Data truth rules for the provided files

## Status

accepted

## Context

The CSVs are not internally consistent (measurements in `docs/notes/01-data-audit.md`). A prototype that
silently "fixes" them produces answers nobody can audit; one that ignores the inconsistencies promises
things the store cannot honour.

## Decision

Each field has one authority, and nothing is recomputed behind the customer's back:

1. **Order total** — `orders.total_brl` is what was charged and is the number spoken to the customer.
   Orders 3 (3,450.00 vs 3,498.00 of line items) and 20 (1,400.00 vs 1,488.00) are answered with the order
   total and flagged in `docs/notes/01-data-audit.md`; the agent never "corrects" the invoice.
2. **Order contents and status** — read from the order record, never re-derived from the current catalogue.
   Orders 3 and 14 contain a product that is now `coming_soon` and one of them was delivered: historical
   purchases stay answerable.
3. **Availability** — a product is offered as available only when `status = 'active' AND stock_quantity > 0`.
   `coming_soon` is described as arriving with no confirmed date (the data has no ETA field);
   `discontinued` is described as out of the catalogue with equivalents offered from the same category.
4. **Promotions** — only rows with `is_active = 1` are ever quoted (4 of 25 today). Inactive rows are
   treated as expired and answered per §7.3: state the promotion is over and present the current price.
   If a product has several *active* rows, the highest `discount_percent` wins and the choice is logged.
5. **Price display** — promotional price plus original price plus percentage, per §6.2. The 5% PIX discount
   is never stacked on a promotional price (§6.2, cumulative rule), and instalment offers respect the
   minimum-parcel rules of §3.1.
6. **Catalogue claims** — the agent describes only what the catalogue can verify (65 products). It does not
   repeat the manual's "300+ instruments", and for categories with zero products (sopro/madeiras, sopro/
   metais, cordas orquestrais) it says there is nothing available in that category right now instead of
   inventing inventory.

## Consequences

- Two of twenty orders show a total that disagrees with their items; the README lists it as a known data
  issue with the choice made, which is stronger than a silent correction.
- The rules are implemented as pure functions over the dataset (`src/emporio/datasource.py`) so tests
  assert them without an LLM in the loop.
