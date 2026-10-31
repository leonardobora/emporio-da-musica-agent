# CLI REPL plus a scripted scenario runner

## Status

accepted

## Context

The brief accepts CLI, notebook, API or a simple UI, and grades the agent's behaviour. The deliverable
also demands **3–5 example conversations**, and hand-written examples are worthless as evidence: they
prove the author can write dialogue, not that the agent works.

## Decision

Two entry points over the same `Agent` class:

- `python -m emporio chat` — interactive REPL (one customer session per process, `--order` shortcut to seed
  the order under discussion).
- `python -m emporio run-scenario examples/scenarios/02_devolucao.json` — feeds a scripted list of customer
  turns and writes a Markdown transcript (customer line, agent line, every tool call with its arguments and
  a trimmed result) into `examples/`.

The transcripts shipped in `examples/` are the **output of the second command**, committed unedited apart
from a header noting the model, timestamp and token usage.

## Considered options

- **Streamlit UI.** Considered and rejected: a browser UI adds a dependency and a screenshot step for zero
  grading value, and it cannot be diffed in git the way a transcript can.
- **FastAPI service only.** Rejected as the primary surface: it makes the reviewer run a server and a curl
  to see one answer. Kept as a possible extra if time allows, since the agent loop is already
  transport-independent.

## Consequences

- Every demo is reproducible with one command and byte-diffable; a regression shows up as a changed
  transcript.
- The REPL keeps the "feels like WhatsApp" check cheap: paste a real customer sentence and look at the
  answer.
