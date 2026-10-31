# DeepSeek direct API as the model provider

## Status

accepted

## Context

The provider is graded on the justification, not on the brand. Requirements: reliable tool calling,
PT-BR fluency, low latency for a chat loop, and low cost for a demo that gets run dozens of times
(including the model bake-off and the eval suite).

Verified locally on 2026-10-31: the key in `~/.hermes/.env` authenticates against
`https://api.deepseek.com`, `deepseek-chat` returns a well-formed `tool_calls` payload for a PT-BR prompt,
and the response carries `prompt_cache_hit_tokens` (automatic context caching — the 2.9k-token policy
manual is charged at cache prices after the first turn).

## Decision

Talk to DeepSeek directly, `base_url=https://api.deepseek.com`, model name from `MODEL` env var
(`deepseek-chat` as the default, `deepseek-v4-pro` available for the bake-off). No OpenAI SDK-specific
features beyond the tool-calling contract; the client is a thin `httpx` wrapper so the provider is one
env var away from being swapped.

## Considered options

- **OpenRouter** (tested: key valid, $245.73 of $250 remaining). Rejected for this project only because the
  user asked for direct DeepSeek; it stays the documented fallback, and the code is provider-agnostic
  enough that switching is a `BASE_URL` + `MODEL` change.
- **Local model.** Rejected: no GPU inference running on this machine and a 2-day budget; a 7B model's
  tool-calling reliability in PT-BR is the exact thing that would sink the demo, and the README would have
  to claim "it usually works".

## Consequences

- Cost is a non-issue: the whole case, including the bake-off and repeated eval runs, is under US$1.
- Model choice is measured, not asserted: `scripts/eval.py` runs the same scenarios against every model in
  `MODELS` and the README reports the table.
