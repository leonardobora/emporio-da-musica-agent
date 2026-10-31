# Example conversations

These are **real runs**, not hand-written dialogues. Each file is produced by:

```bash
python -m emporio run-scenario examples/scenarios/<id>.json
```

and committed as generated. The header of each transcript records the model, session id, timestamp and token
usage of that specific run; the tool blocks show the arguments and the (truncated) result of every call the
agent made, which is how a reviewer can check that the price, the stock level and the order status really
came from the data.

| File | Scenario | Why it is here |
|---|---|---|
| `01_catalogo.md` | guitars up to R$ 1,000, then one specific out-of-stock item | catalogue filtering on the *effective* price; "in the catalogue" is not "available" |
| `02_pedido.md` | order status with the identity gate | **non-trivial**: refuses to answer, answers the same for wrong digits, reveals tracking only after verification |
| `03_devolucao.md` | "I regret my purchase" on an old order | **non-trivial**: applies §4.1 against real dates, reports the closed window, escalates the exception request |
| `04_promocao_expirada.md` | a 30% promotion that no longer exists | **non-trivial**: verifies promotion state, quotes the current 8%, computes 12x via the tool |
| `05_fora_de_escopo.md` | strings, Saturday hours, saxophone | scope §7.1, static store data, and a category the manual lists but the catalogue does not stock |

How to read a transcript:

```
**Cliente:** …            customer turn (scripted)
`tool_name({...})`        every tool call the model made before answering
```json … ```             the result the model saw (truncated at 700 chars)
**Agente:** …             the answer actually sent
```

The `## Checagens automáticas` block at the end of each file is the machine verdict for that run — the same
assertions `scripts/eval.py` uses for the model comparison.

The scenario definitions in `scenarios/` are the input: `turns` is the script, `expect` / `turn_expect` are the
machine-checked expectations (required tools, forbidden leaks, exact prices).
