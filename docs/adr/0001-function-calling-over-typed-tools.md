# Function calling over typed tools; policies live in the prompt

## Status

accepted

## Context

The agent must answer three materially different kinds of question:

1. **Live operational facts** — price, stock, order status, tracking code, active promotions.
2. **Policy interpretation** — return windows, payment instalments, opening hours, warranty.
3. **Off-catalogue conversation** — accessories, competitors, small talk.

Measured sizes of what was provided (2026-10-31, `chars / 4` estimate):

| Asset | Size |
|---|---|
| `políticas_da_loja.pdf` (8 pages, full text) | ~11,600 chars ≈ **2.9k tokens** |
| whole product catalogue as JSON | ~31,200 chars ≈ **7.8k tokens** |
| all orders as JSON | ~4,400 chars ≈ **1.1k tokens** |
| all customers as JSON | ~6,900 chars ≈ **1.7k tokens** |

## Decision

One LLM loop with **function calling** against typed tools backed by SQLite, plus the full policy manual
in the system prompt. The model never states a price, stock level, deadline or order status it did not
receive from a tool result in the same turn.

Tools are intentionally coarse-grained (one call answers a whole question) instead of exposing raw SQL.

## Considered options

- **RAG over everything (catalog + policies).** Rejected as the primary mechanism: vector search over 65
  products and 20 orders is strictly worse than an exact query — it can miss `stock_quantity = 0` or return
  an inactive promotion, which is the failure mode this case plants. RAG is also ~10k tokens of embedding
  infrastructure for data that fits in a query.
- **Text-to-SQL agent.** Genuinely attractive (the whole dataset is 10.6k tokens, one join answers
  anything), and it is the most impressive-sounding option. Rejected because arbitrary SQL over
  `customers` makes the privacy gate unenforceable — the gate has to sit *between* the model and the data,
  and generated SQL bypasses it. It also makes every answer non-reproducible for the eval suite.
- **Vector RAG over the policy manual only.** Rejected: the manual is 2.9k tokens, so chunking it adds a
  recall failure mode (a question about instalments landing on the frete chunk) in exchange for nothing.
  The threshold where this flips is documented in the README: a manual above ~20k tokens, or policies that
  change without redeploying the prompt.
- **ReAct with free-text reasoning and a search tool.** Rejected as the *shape* of the loop: with DeepSeek
  native function calling, the schema of the arguments is validated by the API and each tool call is
  inspectable in the transcript, which is exactly what the eval suite asserts on. Free-text ReAct gives no
  such handle.

## Consequences

- Every fact in an answer is traceable to a tool result; the example transcripts show the calls.
- Tool granularity becomes an API to maintain by hand: when the store adds "purchase history by customer",
  a new tool is needed rather than a prompt tweak.
- The dataset is small enough that a wrong tool answer is a bug in our code, never an approximation.
