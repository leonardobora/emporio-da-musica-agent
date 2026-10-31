# Empório da Música — AI Customer Service Agent

Technical case for the **AI Engineer – Full-Stack para Aplicações com IA Generativa** role at Artefact.

A text-message support agent for a fictional musical instrument store in Campo Grande/MS, Brazil.

> **Status:** work in progress. Decisions are being recorded as ADRs in `docs/adr/` and terminology in `GLOSSARY.md` before implementation starts.

## The brief (short version)

Build a Python text-message agent that:

- adopts a persona aligned with the store's identity and tone (informal but professional, PT-BR);
- answers from the provided context (CSVs + internal policy manual);
- knows **when to query data** (price, stock, order status) and **when to apply policy** (exchanges, hours, payment);
- handles out-of-scope questions properly (the store sells instruments only — no accessories).

Deliverables: public Git repo with real commit history, `README.md` with run instructions + decision rationale + known limitations + AI-assistant usage, and 3–5 example conversations (at least one non-trivial).

## Repository layout

```
data/            Case data as provided (CSVs + policy manual PDF). Not modified.
docs/case/       The original case brief.
docs/adr/        Architecture Decision Records — why each choice was made.
docs/notes/      Working notes: deadline, ambiguities and the assumption taken.
examples/        Example conversations with the agent (deliverable).
src/             Agent implementation.
tests/           Automated checks (tool-routing and policy scenarios).
```

## How to run

_TBD — filled once the implementation lands._

## Technical decisions

_TBD — summarized here, justified in `docs/adr/`._

| Decision | Choice | Rationale |
|---|---|---|
| Agent framework/approach | Function calling over typed tools (SQLite-backed); policy manual in the system prompt | Exact queries beat vector search on 65 products; the manual is ~2.9k tokens. Full comparison in [ADR 0001](docs/adr/0001-function-calling-over-typed-tools.md) |
| Model & provider | DeepSeek direct (`api.deepseek.com`), model from `MODEL` env var | Reliable tool calling, cheap, PT-BR fluent, provider swappable by one env var — [ADR 0002](docs/adr/0002-deepseek-direct-as-model-provider.md) |
| Interaction interface | CLI REPL + scripted scenario runner that writes the example transcripts | Every example in `examples/` is a real run, diffable in git — [ADR 0003](docs/adr/0003-cli-repl-with-scripted-scenario-runner.md) |
| Conversation persistence | SQLite (`sessions`, `messages`, `session_customer`), store data read-only next to it | Keeps the order under discussion between turns — [ADR 0004](docs/adr/0004-sqlite-for-conversation-persistence.md) |
| Data treatment | One authority per field; no silent corrections — [ADR 0006](docs/adr/0006-data-truth-rules.md) | The CSVs contain 2 orders whose totals disagree with their items |
| Order privacy gate | Order id + last four digits of the phone on file — [ADR 0005](docs/adr/0005-order-lookup-gated-by-phone-suffix.md) | Name-based lookup leaks: one e-mail belongs to two customers |
| Tests | pytest with the LLM mocked + a live eval script against real models — [ADR 0007](docs/adr/0007-pytest-with-mocked-llm-plus-live-eval.md) | Routing and policy rules asserted deterministically; model choice measured |

## Assumptions where the brief was ambiguous

- **Deadline**: received Saturday 2026-10-31, so the two business days are Mon 2026-11-02 and
  Tue 2026-11-03 — delivery target Tue 23:59 BRT (`docs/notes/00-briefing.md`).
- **Submission language**: the deliverable (code, README, ADRs, transcripts' narration) is English, per the
  recruiter's instruction. The agent itself speaks **PT-BR**, because that is what the store's customers
  speak; the transcripts are therefore PT-BR with an English header.
- **Data inconsistencies**: kept and documented rather than corrected, because the grader cannot audit a
  silent fix (`docs/notes/01-data-audit.md`, ADR 0006).
- **Unused data**: `customers` is never searched by name, only joined for the phone check; `specs` is used
  for product comparison, not for filtering by exact spec keys.


## Known limitations / next steps

_TBD._

## Use of AI coding assistants

_TBD._
