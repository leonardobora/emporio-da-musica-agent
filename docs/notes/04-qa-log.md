# First live runs: what failed and what it changed

A record of the first three live executions of the scenario suite, kept because the interesting part of this
case was not writing the agent — it was deciding, for each red check, whether the agent or the check was wrong.

## Run 1 — three red checks, one real defect

| Check | Verdict | Action |
|---|---|---|
| `02_pedido` turn 1 must call `get_order` | **check was wrong** | The agent asked for the last four digits *before* calling anything, which is the correct order of operations (no order id lookup should happen without the second factor being requested). The assertion was rewritten to require the question (`4 últimos dígitos`), not the call. |
| `03_devolucao` turn 1 must state the window is closed | **check was wrong** | The answer read "o prazo de 7 dias corridos (§4.1) venceu em 01/11/2025, então ele não está mais aberto" — correct, but 36 characters separated "prazo" from "venceu", and the regex allowed 20. Widened, and later widened again with more phrasings. |
| `05_fora_de_escopo` must state the scope | **check was wrong** | The regex expected "exclusivamente instrumentos"; the agent wrote "trabalha exclusivamente **com** instrumentos musicais". |
| Markdown leaking into WhatsApp replies | **agent was wrong** | Transcript `01` came back with `**Nylon (clássico)**` and `-` bullets — raw asterisks in a WhatsApp window. This became an explicit rule in the system prompt ("texto puro, sem markdown; listas com •"), and the regenerated transcript uses it. |

## Data mistakes made while writing the tests

Two assumptions survived from skimming the CSVs and were only caught because the tests failed:

- **Order ≠ customer id.** `get_order(7, "6543")` returned "não encontrado" because order 7 belongs to
  customer 14; the phone ending in 6543 belongs to customer 7, who owns order 2. The identity scenarios now
  use order 2 (`BRCX9876543BR`), and the mistake is why `docs/notes/01-data-audit.md` insists on measuring
  rather than eyeballing.
- **Product 94 is R$ 5.999,00, not R$ 7.499,00.** The 8% promotion therefore gives R$ 5.519,08; the Taylor at
  R$ 7.499,00 is product 106. The scenario expectation and two tests were corrected against the data.

## Model variance

At `TEMPERATURE=0.3` the `03_devolucao` wording check passed on one run of `deepseek-chat` and failed on the
next, and `deepseek-flash` sometimes forgot to escalate the exception request. Evaluation now runs at
**temperature 0** (`scripts/eval.py`), so a model comparison measures the model and not the dice; the
interactive REPL keeps 0.3 because a support agent should not sound like a template.

**Temperature 0 is not determinism.** In the second bake-off run the same model, same prompt, same data
produced a different sentence for the same scenario: `deepseek-flash` failed `02_pedido` turn 2 in the batch
run and passed it verbatim on a rerun minutes later. The lesson recorded here: a scenario suite gives you a
*rate over runs*, not a proof. The report in `03-model-bakeoff.md` is one snapshot with its timestamp, which
is why the timestamp is in the header.

That rerun also exposed two more over-strict checks, both fixed:

- `05_fora_de_escopo` expected `não temos`; `deepseek-v4-pro` wrote "no momento a gente **não tem**
  saxofones no catálogo" — same meaning, different conjugation.
- `03_devolucao` expected `prazo … venceu`; one answer said "o prazo é de 7 dias … e **o seu terminou** em
  01/11/2025", which is the same claim with the subject elided.

## A real defect the scenarios found later: the agent invented today's date

Added after the first delivery pass, as a sixth scenario kept in `tests/scenarios/` (the brief asks for
3–5 example conversations, so the regression scenario does not sit in `examples/`).

Prompt: *"Se eu comprar hoje o Yamaha F310, chega antes do dia 20 em Dourados?"* — the reply in the first run:

> "Como hoje é dia 10, o SEDEX chega com folga antes do dia 20."

Two violations in one sentence, and both are the case's core failure mode:

1. **It invented the current date** (the run happened on 2026-10-31).
2. **It converted a policy window into a delivery promise** — §7.1 forbids quoting deadlines without the
   system, and §5.2 only publishes estimated windows counted from dispatch.

The fix went to the two places that own the fact, not to the scenario:

- `store_info()` now serves the clock (`today_iso`, `today_human`); a model that can look up today does not
  invent it.
- prompt rule 12: never state today's date without `store_info`, never turn §5.2's windows into a promised
  date, and hand freight quotes to a human because this system has no CEP calculator.

After the fix the same scenario reads "não consigo calcular frete nem data por aqui, e a data exata quem
confirma é a equipe", cites the windows as estimates counted from dispatch, and escalates only when the
customer accepts. That is the whole value of the scenario suite: it caught a hallucination that no unit test
would have found, and the fix landed in data and prompt rather than in the assertion.

## A committed transcript with a red check (caught in the final review)

After the examples were regenerated for the last time, `examples/05_fora_de_escopo.md` shipped with one
failing check: the agent said "a loja é especializada em instrumentos musicais… cordas entram como acessório,
fora do nosso escopo", and the assertion only accepted `só instrumentos` / `exclusivamente instrumentos` /
`não trabalhamos com acessórios`. Correct behaviour, fourth variant of the same brittleness (the optional
"com", again).

Two changes, both in the check rather than the prose: the pattern now accepts `só (com )instrumentos`,
`fora do nosso escopo`, `não vendemos` and `não comercializamos`; and the transcript was regenerated so the
file committed is a run where every check is green. The English translation was re-done against that new run
(session id and timestamp included), because a translation of an older run would be a quiet lie.

The rule this keeps re-teaching: **an assertion over generated prose should match the meaning, not the
sentence you happened to read first.**

## Observations kept from the first runs, because they are the kind of thing a checklist will not catch

- The agent spontaneously offered the human handoff *before* the customer asked for an exception (turn 1 of
  `03`) and then escalated when asked (turn 2) — the intended behaviour, arrived at from the prompt rules
  alone. That is also why the escalation check was moved from "turn 2" to "somewhere in the conversation":
  escalating early is better support, and the check was punishing it.
- `get_order` failures never leaked the existence of the order: both an existing order with wrong digits and
  a non-existent order id produce the identical message.
- When asked for a category with no products (`05`, saxophone), every model said the category has nothing
  available instead of inventing inventory — but two of them first had to call `search_products` and see an
  empty result, which is the intended path.
