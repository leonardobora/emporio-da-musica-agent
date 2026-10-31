# SQLite for sessions, messages and customer binding

## Status

accepted

## Context

The brief makes persistence optional, but a support agent that forgets the customer's order between
messages re-asks for the same order number on every turn — the most common failure in chat support, and
one the reviewer will notice in the example transcripts.

## Decision

One SQLite file (`emporio.sqlite`, gitignored) holding three tables: `sessions`, `messages`,
`session_customer`. The conversation sent to the model is rebuilt from `messages` on every turn; the
customer binding (once the identity gate passes) is stored per session and reused.

The store data stays in **separate, read-only** tables generated from `data/*.csv` at startup — same file,
different tables, so a session can never be tricked into writing to the catalogue.

## Considered options

- **In-memory only.** Rejected: losing the order under discussion after one restart makes the demo worse,
  and the history would be invisible to the tests.
- **JSON files per session.** Rejected: the eval suite needs "give me all messages of session X, in order"
  in one line, and append-only JSON grows a hand-rolled reader for what SQLite gives free.

## Consequences

- Tests can inspect the persisted history directly, and `python -m emporio history <session>` is a
  two-line debug tool.
- Sessions are single-user by construction (one REPL process = one session), which is honest for a
  prototype; multi-user routing would need a channel id in `sessions`.
