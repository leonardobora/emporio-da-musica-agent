# Could a local System-1 decider route this agent?

**Question.** The agent spends two LLM calls per turn. Could a small local *decision* model — one that
returns calibrated probabilities over options instead of generating text — sit in front of it and decide
either "answer this from a template" (skipping the LLM) or "this needs the strong model with tools"?

**Short answer.** Not on this traffic, and not with this model out of the box. Measured on the agent's own
logged turns, both candidate gates land at or below the majority-class baseline, while adding ~0.5–0.7 s of
latency to every message. The decision is recorded in
[ADR 0008](../adr/0008-no-local-decider-in-the-loop.md), and the probe is reproducible:
`python scripts/jev_probe.py`.

## Setup

| Item | Value |
|---|---|
| Decider | `Decision-Jef-0.1`, a local System-1 typed decider (PT-BR state accepted, English criteria required) |
| Endpoint | `http://127.0.0.1:8088/v1/systemone`, `systemd --user`, CPU only |
| Ground truth | the tool calls this agent actually made for each logged customer turn (`emporio.sqlite`) |
| Sample | 203 logged customer turns = **13 distinct messages** (5 scenarios replayed ~16×) |
| Date | 2026-10-31 |

The sample size is the first finding: 13 distinct messages is a smoke test, not a distribution. It is enough
to reject "works out of the box", not enough to measure a production error rate.

## Results

Three tasks were put to the decider. Accuracies are against the truth derived from tool calls, with the
majority-class baseline beside them — a number without its baseline says nothing.

| Task asked of the decider | Accuracy | Baseline | Verdict |
|---|---|---|---|
| 6-class intent (`catalog_lookup` / `order_status` / `policy_question` / `store_info` / `smalltalk` / `out_of_scope`) | **1 of 17** messages correctly labelled | — | collapses to one class |
| binary: "needs live store data?" (generic criteria) | 69% | **69% (always `true`)** | no signal over the trivial answer |
| binary: "needs live store data?" (strict literal criteria) | 38% | 69% | collapses to `false`, recall 0% |
| binary: "should go to a human?" | 69% | **77% (always `false`)** | worse than never escalating |
| binary: "needs live store data?" — criteria written in PT-BR | 55% | 69% | worse |

Intent classification collapsed completely: "que horas vocês abrem no sábado?" → `catalog_lookup` 0.87,
"qual o endereço da loja?" → `catalog_lookup` 0.94, "bom dia, tudo bem?" → `catalog_lookup` 0.86, and
"quanto é 2+2?" → `catalog_lookup` **1.00**. Precision on the escalation gate was 33% (1 true positive,
2 false positives): it would push customers to a human for questions the bot answers correctly.

Latency: p50 **529–636 ms** across runs (max 694 ms) — against **2.95 s** for a full agent turn that also
produces the answer. So the decider would cost roughly a fifth of the turn to replace nothing.

## Why it fails — mechanism, not brand

1. **It is stateless.** `"Ah, desculpa — é 6543."` (a follow-up that carries the phone suffix) scored 0.36,
   and `"Beleza. E saxofone vocês têm?"` scored **0.02**, because the referent lives in the conversation
   history and the decider sees one message. In a chat, a large share of turns are continuations.
2. **A tool decision is argument extraction, not label classification.** `get_order` needs an order id plus
   the phone suffix; `search_products` needs a price ceiling. A classifier returns a label; the arguments
   still have to come from somewhere — and a regex gives them in microseconds, exactly, and auditable.
3. **Generic criteria flatten to the base rate.** "Does answering need data?" is true for two thirds of this
   traffic, so a model that always says `true` matches it; and when the criteria are made strict, the same
   model flips to always `false`. That is the signature of a decision boundary the model does not have,
   not of a badly worded prompt (the *catch-all confidence trap* known for this family of models does not
   apply here — the failure is separation, not inflated confidence).

## What a deterministic layer covers instead

Same 13 messages, matching literal signals only (`scripts/jev_probe.py` prints this): **77%** contain a
product name, an order number, a phone suffix, a price, a promotion mention, an hours/address phrase or an
accessory word. Those turns can be routed by pattern matching in ~0 ms, with no model and no risk of
hallucination — leaving the LLM only for the messages that carry no literal anchor at all.

## Where a decider would actually pay off (not what was asked, but what survives review)

1. **Narrow policy gates** with closed options and the manual's own wording as the criterion — "does this
   request fall under an exception to §4.1?" — validated against the 17 labelled escalations already in the
   database.
2. **Asynchronous post-hoc guardrail:** "does this answer assert a price or stock figure with no tool result
   behind it?" runs off the critical path, where +0.6 s costs nothing and a flag prevents the worst possible
   failure of this case.
3. **Risk scoring for the human queue**, not for the chat loop.

## Nuance found while checking thresholds: it abstains well, it routes badly

At `--threshold 0.9` the picture changes shape rather than improving in the same direction:

| Threshold | needed-data gate | Escalation gate |
|---|---|---|
| 0.5 | 69% accuracy (baseline 69%), precision 86%, recall 67% | 69% accuracy, precision 33% |
| **0.9** | **54% accuracy, precision 100%, recall 33%** (3 true / 0 false positives, abstains on 6) | 85% accuracy, precision 100%, recall 33% |

At 0.9 the decider commits on 7 of the 13 messages and is right every time, abstaining on the other 6 — i.e.
it is usable as an **abstention gate** ("when it is confident, trust it; otherwise fall through to the LLM"),
not as a router that must classify everything. With 13 messages, six abstentions and no error budget for
silent false negatives, this is a hypothesis to re-test on real traffic, not a result to build on. It is
recorded here because a future reader running the probe will see the same numbers and deserves the
interpretation instead of just the 0.5 table.

## What would change the verdict

- Real WhatsApp traffic (hundreds of distinct messages) as a labelled set, which this repo now logs but does
  not have.
- At that point the cheaper and more promising route is a supervised classifier over the logged turns
  (TF-IDF + logistic regression), not a zero-shot decider — 13 distinct samples cannot train anything, but
  500 can be measured.

Reproduce with: `python scripts/jev_probe.py [--variant literal] [--threshold 0.9]`.
