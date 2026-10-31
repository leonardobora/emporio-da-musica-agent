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
| Agent framework/approach | _TBD_ | |
| Model & provider | _TBD_ | |
| Interaction interface | _TBD_ | |
| Conversation persistence | _TBD_ | |
| Data treatment | _TBD_ | |

## Known limitations / next steps

_TBD._

## Use of AI coding assistants

_TBD._
