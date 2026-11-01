# 05 — Out of scope, opening hours, empty category (English translation)

> Translation of [`../05_fora_de_escopo.md`](../05_fora_de_escopo.md). The PT-BR file is the record of the
> actual run. Tool calls and results are unchanged.

**Run:** `deepseek-chat` · session `b3085faed5b6` · 2026-11-01T00:04:00Z

---

**Customer:** Do you sell .012 guitar string sets?

**Agent:** Hi! This is the virtual assistant at Empório da Música. 😊

Strings we don't deal with, no — the store is specialised in musical instruments, and strings count as an accessory, outside our scope.

I can help you with a new acoustic guitar, for example. Want me to look at options?

---

**Customer:** And what time do you open on Saturday?

`store_info({})`

**Agent:** On Saturday we open from 09:00 to 13:00. Monday to Friday it's 09:00 to 18:00, and on Sundays and holidays the store is closed.

We're at Rua 14 de Maio, 3200 — Centro, Campo Grande-MS.

Can I help with anything else?

---

**Customer:** Cool. And do you have saxophones?

`search_products({"query": "saxofone"})`

**Agent:** A saxophone is unavailable at the moment — the wind category has no items in our catalogue right now.

If you want, I can show you alternatives in keyboards, acoustic or electric guitars. Would you like to take a look?

**Why this scenario exists:** three different kinds of "no". Accessories are **policy** (§7.1 — the store sells instruments only, and no partner store is invented because the case provides none); opening hours are **static data**; and saxophones are a category the manual lists but the catalogue does not stock — the agent says there is nothing available instead of inventing inventory or repeating the manual's "300+ instruments" claim.
