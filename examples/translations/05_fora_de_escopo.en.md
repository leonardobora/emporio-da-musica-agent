# 05 — Out of scope, opening hours, empty category (English translation)

> Translation of [`../05_fora_de_escopo.md`](../05_fora_de_escopo.md). The PT-BR file is the record of the
> actual run. Tool calls and results are unchanged.

**Run:** `deepseek-chat` · session `7a3cf21633ab` · 2026-11-01T00:00:50Z

---

**Customer:** Do you sell .012 guitar string sets?

**Agent:** Hi! This is the virtual assistant at Empório da Música. So, we only work with musical instruments — strings, picks, cables, cases and the like are outside our scope, so we don't have .012 string sets.

Can I help you with something inside the catalogue, like acoustic guitars, electric guitars, basses, keyboards or drums?

---

**Customer:** And what time do you open on Saturday?

`store_info({})`

**Agent:** On Saturday we open at 9am and close at 1pm. Monday to Friday it's 9am to 6pm, and on Sundays and holidays the store is closed.

WhatsApp support keeps the same hours. Can I help with anything else?

---

**Customer:** Cool. And do you have saxophones?

`search_products({"query": "saxofone", "only_available": false})`

**Agent:** A saxophone is a wind instrument (woodwind/brass) and that category is currently unavailable in our catalogue — I have no model to offer you right now.

If you want, I can show you alternatives from other categories, like keyboards, acoustic or electric guitars. Would you like to see any?

**Why this scenario exists:** three different kinds of "no". Accessories are **policy** (§7.1 — the store sells instruments only, and no partner store is invented because the case provides none); opening hours are **static data**; and saxophones are a category the manual lists but the catalogue does not stock — the agent says there is nothing available instead of inventing inventory or repeating the manual's "300+ instruments" claim.
