# Empório da Música — AI customer-service agent

[![tests](https://github.com/leonardobora/emporio-da-musica-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/leonardobora/emporio-da-musica-agent/actions/workflows/tests.yml)

A text-message support agent for a fictional musical instrument store in Campo Grande/MS, Brazil. It answers
customers in **PT-BR** over WhatsApp-style chat, and it may only state a price, stock level, order status or
promotion after querying the store's data — never from the model's memory.

## In 90 seconds

```bash
git clone https://github.com/leonardobora/emporio-da-musica-agent && cd emporio-da-musica-agent
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
cp .env.example .env            # add a DEEPSEEK_API_KEY
python -m emporio chat          # or: python -m emporio run-scenario
pytest -q                       # 45 tests, offline, no key
```

| | |
|---|---|
| **What it is** | one LLM loop with 9 typed tools over SQLite; the policy manual lives in the prompt (~3k tokens) |
| **What it guarantees** | no price/stock/order fact without a tool result in the same conversation; no order data before order id + last 4 digits of the phone |
| **What it proves** | 45 offline tests (81% coverage), 5 live conversations committed as real runs, a 3-model bake-off, and one measured negative result (a local decision model that did not beat the baseline) |
| **What it costs** | ~US$0.0014 per conversation turn, ~3 s per turn with 96% prompt-cache hits |
| **Where the reasoning is** | `docs/adr/` (8 decisions with rejected alternatives), `docs/notes/` (deadline, data audit, model bake-off, QA log, decider experiment) |

The rest of this README is the long version: decisions, the data problems and how each is handled, the
examples, and what is still missing.

Built as a technical case for an **AI Engineer** role (Python, LLM tool calling). Decisions and rejected
alternatives live in [`docs/adr/`](docs/adr/); the vocabulary is in [`GLOSSARY.md`](GLOSSARY.md).

```
src/emporio/
  agent.py       the loop: message -> tool calls -> answer, with history replay
  tools.py       9 tool schemas exposed to the model + the dispatcher that enforces the gate
  datasource.py  pure functions over the data: prices, promotions, availability, orders, payment terms
  policies.py    the internal manual, split by section for exact citation
  database.py    SQLite: store tables (read-only) + sessions/messages/handoffs (writable)
  runner.py      scripted scenarios -> committed Markdown transcripts
  cli.py         chat, run-scenario, history, rebuild
data/            the case data, verbatim
examples/        5 real conversations (generated, not written by hand) + scenario definitions
tests/           45 tests, LLM mocked at the transport boundary (+ tests/scenarios for regressions)
scripts/         eval.py (live model comparison), csv_profile.py (data profiler),
                 jev_probe.py (local-decider experiment)
```

## Quickstart

Requires Python ≥ 3.11 and a DeepSeek API key.

```bash
git clone https://github.com/leonardobora/emporio-da-musica-agent && cd emporio-da-musica-agent
python -m venv .venv && . .venv/bin/activate     # or: uv venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env        # put your DEEPSEEK_API_KEY in it
python -m emporio chat      # talk to the agent in the terminal
```

Other entry points:

```bash
python -m emporio chat --order 2 --phone 6543   # start with that order already verified
python -m emporio run-scenario                  # run every scenario, refresh examples/*.md
python -m emporio run-scenario 03_devolucao     # one scenario, by name
python -m emporio history <session_id>          # replay a persisted conversation
python -m emporio rebuild                       # reload data/*.csv into SQLite, print counts
pytest -q                                       # 45 tests, offline, ~2s
pytest -q --cov=emporio --cov-report=term      # same tests + coverage (81%)
python scripts/eval.py --models deepseek-chat,deepseek-flash \
    --report docs/notes/03-model-bakeoff.md     # live model comparison, costs cents
```

`MODEL`, `DEEPSEEK_BASE_URL` and `TEMPERATURE` are env vars, so any OpenAI-compatible endpoint can be swapped
in without touching code.

## How it works

One LLM loop with native function calling. The policy manual (~3k tokens) sits in the system prompt; every
factual claim about the store's operation comes from a tool result in the same conversation.

| Tool | Answers | Notes |
|---|---|---|
| `search_products` | catalogue, price range, category | filters on the **effective** price (promotion applied); hides unsellable items by default |
| `get_product` | one product's price, stock, specs | |
| `check_availability` | is it sellable today | `status = active AND stock > 0` |
| `list_active_promotions` | what is really on sale | only `is_active = 1` rows |
| `payment_options` | PIX, instalments, boleto | §3.1 computed in code, never by the model |
| `get_order` | status, tracking, return windows | requires order id **+ last 4 digits of the phone on file** |
| `get_policy` | exact text of a manual section | so citations are literal, not paraphrased |
| `store_info` | address, hours, shipping, scope | |
| `escalate_to_human` | handoff + SLA | writes a row in SQLite before answering |

Two rules do most of the safety work: **no fact without a tool call**, and **no order data before the
identity gate**. Both are asserted in tests and visible as tool blocks in every transcript.

## Technical decisions

Each row links to the ADR holding the alternatives that were rejected.

| Decision | Choice | Why |
|---|---|---|
| Agent approach | Function calling over typed tools; manual in the prompt | 65 products and 20 orders want exact queries, not vector similarity; the manual is ~2.9k tokens — [ADR 0001](docs/adr/0001-function-calling-over-typed-tools.md) |
| Model & provider | DeepSeek direct, `MODEL` env var | reliable tool calling, PT-BR fluent, ~US$0.01 per scenario; verified by a live call before any code — [ADR 0002](docs/adr/0002-deepseek-direct-as-model-provider.md) |
| Interface | CLI REPL + scripted scenario runner | the examples are real runs, diffable in git — [ADR 0003](docs/adr/0003-cli-repl-with-scripted-scenario-runner.md) |
| Persistence | SQLite (`sessions`, `messages`, `session_customer`, `handoffs`) | the verified order survives between turns — [ADR 0004](docs/adr/0004-sqlite-for-conversation-persistence.md) |
| Order privacy gate | order id + last 4 digits of the phone | names collide and one e-mail belongs to two customers — [ADR 0005](docs/adr/0005-order-lookup-gated-by-phone-suffix.md) |
| Data treatment | one authority per field, no silent fixes | 2 orders have totals that disagree with their items — [ADR 0006](docs/adr/0006-data-truth-rules.md) |
| Tests | pytest with the LLM mocked + live eval | routing and policy regressions asserted deterministically; model choice measured — [ADR 0007](docs/adr/0007-pytest-with-mocked-llm-plus-live-eval.md) |

### Data problems found, and how they are handled

Measured in [`docs/notes/01-data-audit.md`](docs/notes/01-data-audit.md) before any code was written:

| Problem | Handling |
|---|---|
| 21 of 25 promotions are `is_active = 0` | never quoted; asking about an expired promotion gets the current price (§7.3) — example `04` |
| "available" is ambiguous | `status = active AND stock > 0`: product 96 has stock 0 while `active`, 113 is `discontinued`, 130 is `coming_soon` — example `01` |
| orders 3 and 20: total ≠ sum of items | `total_brl` is the charged amount; the discrepancy is documented, not "fixed" |
| orders 3 and 14 sold a product that is now `coming_soon` | past orders are answered from the order record — `test_historical_order_with_coming_soon_product_still_answers` |
| every order is 7+ months old | return windows are computed against real dates and reported as closed — example `03` |
| categories 6/7/8 (wind, brass, orchestral) have zero products | the agent says that category has nothing available instead of inventing inventory — example `05` |
| the manual claims "300+ instruments"; the catalogue has 65 | the agent speaks only about what it can verify |

## Example conversations

All five in [`examples/`](examples/), generated by the scenario runner — each file names the model, session
and token usage of the run that produced it:

English translations of the same runs are in [`examples/translations/`](examples/translations/) — the PT-BR
files are the record, the translations exist so an English-speaking reviewer can read the dialogue.

1. [`01_catalogo.md`](examples/01_catalogo.md) — guitars under R$ 1,000, then a specific item that is in the catalogue but out of stock.
2. [`02_pedido.md`](examples/02_pedido.md) — **non-trivial**: order status behind the identity gate; wrong digits first, then the real tracking code.
3. [`03_devolucao.md`](examples/03_devolucao.md) — **non-trivial**: "I regret my purchase" on an order whose 7-day window closed; policy applied, human handoff for the exception.
4. [`04_promocao_expirada.md`](examples/04_promocao_expirada.md) — **non-trivial**: the 30% promotion the customer "saw" is expired; current price and 12x instalments come from tools.
5. [`05_fora_de_escopo.md`](examples/05_fora_de_escopo.md) — guitar strings (out of scope), Saturday hours, and a saxophone category with no catalogue items.

A sixth conversation — shipping quote for a CEP outside the metro area, which the system cannot compute —
lives in [`tests/scenarios/06_frete_por_cep.md`](tests/scenarios/06_frete_por_cep.md) instead of `examples/`,
because the brief asks for 3–5 examples and this one is a regression guard. It found a real defect: see the
QA log.

## Evaluation

- **45 offline tests** (`pytest -q`, no network, 81% line coverage, run in CI on Python 3.11 and 3.12):
  data rules, promotion activity, availability, instalment maths, identity gate, tool dispatch, history
  replay, transport retry semantics, transcript rendering, max-round fallback.
- **5 live scenarios** with machine-checked expectations (`expect` / `turn_expect` in each scenario file):
  required tools, forbidden leaks (e.g. the tracking code before verification), exact prices.
- **Model bake-off**: same scenarios, same prompts, three models, temperature 0 —
  [`docs/notes/03-model-bakeoff.md`](docs/notes/03-model-bakeoff.md).

Latest bake-off (2026-10-31, one snapshot — see `docs/notes/04-qa-log.md` for why a snapshot and not a score):

| Model | Scenarios passed | Est. cost for the 5 | Notes |
|---|---|---|---|
| `deepseek-chat` | 5/5 | US$ 0.007 | default: shortest answers (≈400 completion tokens/scenario), lowest cost |
| `deepseek-flash` | 5/5 | US$ 0.010 | correct but chattier (≈890 tokens/scenario) |
| `deepseek-v4-pro` | 5/5 | US$ 0.009 | correct; occasionally over-explains the scope rule |

All three pass, so the default stays `deepseek-chat`: same correctness, a third of the verbosity. The cost
column is computed from the provider's token counts (`scripts/eval.py`), not estimated by hand — a full
scenario suite costs about one cent.

Two honest caveats: the earlier runs of the same table had red checks that were mostly **wrong assertions**
(fixed, see the QA log), and temperature 0 is not determinism — the same prompt can produce a different
sentence on the next call, so these are pass *rates*, not proofs.

### Rejected after measuring: a local decision model as pre-router

The obvious way to cut calls — a small local *decision* model (calibrated probabilities, no generation)
routing messages to templates or to the strong model — was measured against this agent's own logged turns
and did not beat the majority-class baseline, while adding 0.5–0.7 s per message: "needs live data?" 69%
versus always-`true` 69%; "needs a human?" 69% versus always-`false` 77% (precision 33%); six-class intent
1 of 17 correct. A regex layer already finds literal anchors in 77% of the distinct messages in
microseconds. Full numbers, method and what would change the verdict:
[`docs/notes/05-jev-router-experiment.md`](docs/notes/05-jev-router-experiment.md) and
[ADR 0008](docs/adr/0008-no-local-decider-in-the-loop.md); reproduce with `python scripts/jev_probe.py`.

## Known limitations / what I would do next

- **Single channel, single user per process.** WhatsApp is the real deployment target: webhook plus a
  message queue, with sessions keyed on the phone number instead of a CLI session id.
- **No write path.** The agent reads stock and registers a handoff, but cannot reserve a product, create an
  order or change an address — deliberate for a prototype, and the first thing to add.
- **Policies in the prompt stop scaling** past ~20k tokens, and a policy change needs a redeploy. With a real
  manual I would chunk by section (`get_policy` is already the seam), embed, and retrieve per question while
  keeping exact citation text.
- **Ambiguous duplicate identities** (`bruno.martins@jmail.com` on two customer rows) are neutralised by
  using the order id as the lookup key, but a real CRM needs a unique customer key.
- **No answer-quality judge.** The scenario checks assert facts and routing, not tone. With more time: an
  LLM-as-judge pass on tone/persona, plus a small human-labelled set of real WhatsApp conversations.
- **Thin observability.** Beyond the token counts recorded per transcript there are no metrics; production
  would want structured traces (tool latency, tool error rate, handoff rate, escalation reasons).

## Use of AI coding assistants

This project was built in pair-programming mode with **Hermes Agent** (open-source CLI agent) driving
**DeepSeek** as the coding model. The workflow, honestly:

1. The case PDF, CSVs and policy manual were read and audited first; `docs/notes/01-data-audit.md` combines
   a generated profile (`scripts/csv_profile.py`) with hand-written checks for the planted traps.
2. The design was settled in a structured interview *before* code: each decision, alternative and rejected
   option became an ADR, so the reasoning is reviewable independent of who typed it.
3. Code came in small commits (bootstrap → ADRs → data layer → tools → loop → runner → transcripts → tests),
   each one run by me. The first live scenario run failed three assertions; deciding whether the assertion
   or the agent was wrong was the actual work: two were harness bugs (an over-strict regex, an order id I had
   misread from the CSVs), one was a real prompt gap (markdown formatting leaking into WhatsApp replies),
   which became an explicit rule in the system prompt.
4. The example transcripts are **not** written by an assistant: they are `run-scenario` output, committed as
   produced.

Where AI was *not* used: choosing what the agent must refuse to answer, and which data inconsistencies to
keep — those came from reading the manual and the data, then locking the rule into an ADR.

## Assumptions where the brief was ambiguous

- **Deadline**: case received Saturday 2026-10-31 → the two business days are Mon 2026-11-02 and
  Tue 2026-11-03; delivery target **Tue 2026-11-03 23:59 BRT** ([`docs/notes/00-briefing.md`](docs/notes/00-briefing.md)).
- **Language of the deliverable**: English (per the recruitment instructions) for code, README and
  documentation; the **agent speaks PT-BR** because that is what the store's customers speak, so the
  transcripts are PT-BR under an English header.
- **Data inconsistencies are documented, not corrected** (ADR 0006) — a silent fix cannot be audited.
- **Unused data**: `customers` is only joined for the phone-suffix check, never searched by name; `specs` is
  used for product comparison in the answer, not for filtering by exact spec keys.
- **Partner shops**: the manual suggests pointing customers to partner stores, but the case provides no
  partner data, so the agent states that the store does not sell accessories instead of inventing names.

## How this maps to Artefact's approach

Three of Artefact's stated pillars structure this repo rather than decorate it:

- **Shape AI strategy** → `docs/adr/` and `docs/notes/`: the decision and its rejected alternatives are
  written before code, and the data audit is the input to those decisions.
- **Deploy AI at scale** → typed tools instead of free-form SQL, an identity gate the model cannot bypass,
  deterministic evaluation, provider swap by env var, and cost measured per scenario instead of guessed.
- **Drive AI adoption** → transcripts as the artefact the store's team can read and correct, a handoff path
  that keeps a human in the loop for exceptions, and rules written where an attendant can check them.

## Repository history

The commit log is the work: bootstrap and data audit → decisions as ADRs → data layer → tools and agent loop
→ CLI and runner → generated transcripts → tests → evaluation → README. Nothing was force-pushed and nothing
was amended into a single "initial commit".
