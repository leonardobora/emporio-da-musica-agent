# pytest with a mocked LLM, plus one live eval script

## Status

accepted

## Context

The behaviours worth defending are agent decisions, not string formatting: does it call the stock tool
before quoting availability, does it refuse to quote an inactive promotion, does it ask for the phone
suffix before revealing an order. Asserting on live model output makes those tests slow, costly and flaky;
asserting on nothing makes the README's claims unverifiable.

## Decision

Two layers:

- `tests/` — pytest, model **mocked** at the transport boundary with recorded tool-call scripts. Fast
  (no network), deterministic, and they fail when tool routing, the identity gate, the promotion rule or
  the policy windows regress. The tool implementations themselves are tested directly against the CSVs
  (e.g. order 3 reconciles, product 96 is not available, only 4 promotions are live).
- `scripts/eval.py` — runs the scenario suite against each real model, prints per-scenario pass/fail and the
  token cost, and produces the model comparison table quoted in the README.

## Considered options

- **LLM-as-judge for everything.** Rejected: it costs a second model opinion to answer questions a
  deterministic assertion settles, and it hides regressions behind judge variance.
- **Recorded cassette replay only.** Rejected as the whole strategy: cassettes prove the code still does
  the 2026-10-31 thing, not that today's model still routes correctly — hence the live eval alongside.

## Consequences

- `pytest` runs offline in under a second; the live eval is opt-in and needs a key.
- Scenario files are shared by both layers, so a new scenario automatically exercises both.
