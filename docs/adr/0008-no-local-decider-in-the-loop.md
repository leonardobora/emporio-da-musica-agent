# No local decision model in the loop

## Status

accepted (measured, see `docs/notes/05-jev-router-experiment.md`)

## Context

The agent makes two LLM calls per turn: one to choose tools, one to write the answer. A tempting
optimisation is a local System-1 *decision* model — calibrated probabilities over options instead of
generated text — acting as a pre-router: "this is a static-hours question, answer from a template"; "this
needs the strong model with tools"; "this should go straight to a human".

The idea was measured against the agent's own logged turns (203 turns, 13 distinct customer messages) using
`Decision-Jef-0.1` locally, with ground truth taken from the tool calls the agent actually made.

## Decision

No decision model in the loop, neither as router nor as gate. The binary gates did not beat the
majority-class baseline ("needs data?" 69% = always-true 69%; "needs a human?" 69% < always-false 77%,
precision 33%), six-class intent collapsed to a single label (1 of 17 correct), and each call would add
0.5–0.7 s to a 2.95 s turn. A deterministic regex layer already identifies literal anchors in 77% of the
distinct messages, in microseconds, where it is exact and auditable.

## Considered options

- **Pre-router skipping the LLM for template intents.** Rejected: the classifier could not separate the
  intents, and the templates would have to cover purchase-specific answers the data does not template well.
- **Guard gate before the answer.** Rejected for the synchronous path: 33% precision means blocking or
  escalating correct answers.
- **Post-hoc asynchronous guardrail** ("does this answer assert a price with no tool result behind it?").
  Not rejected — deferred. It runs off the critical path and is the one use with a clear failure it
  prevents; it needs a labelled set to calibrate, which this prototype does not have yet.
- **Regex/template layer only, no LLM.** Rejected: 23% of distinct messages carry no literal anchor and the
  remainder still need the persona and the policy reasoning.

## Consequences

- Latency stays at ~3 s per turn with two LLM calls, and cost stays at ~US$0.0014 per turn; the money was
  never the problem, so there is nothing to win by adding a model that only saves calls.
- The pattern-matching seam exists (`datasource`/`tools` are already deterministic), so a future router can
  be inserted without touching the prompt.
- Revisit when there is real WhatsApp traffic: with a few hundred labelled messages the right experiment is a
  supervised classifier over the logged turns, not a zero-shot decider.
