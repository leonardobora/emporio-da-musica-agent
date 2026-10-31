# Empório da Música — agent context

A Portuguese-speaking chat support agent for a fictional instrument store. The vocabulary below is the
one the agent, the code and the transcripts must use; the store's customers never see the internal names.

## Language

**Cliente**:
A person messaging the store. Identified for order purposes by order id plus the last four digits of the
phone on file. Never looked up by name alone.
_Avoid_: Usuário, contato, lead

**Pedido**:
A purchase record in `orders`, with a status (`pending`, `confirmed`, `shipped`, `delivered`, `cancelled`),
a total, and — once shipped — a tracking code.
_Avoid_: Compra, transação, venda (in agent-facing text)

**Status do pedido**:
The single current state of a `Pedido`. The agent speaks it verbatim and never infers it from stock or from
the products it contains.
_Avoid_: Situação, etapa

**Disponibilidade**:
The conjunction `status = 'active'` **and** `stock_quantity > 0`. Neither condition alone is availability.
_Avoid_: Estoque (the raw column), "em linha"

**Produto descontinuado**:
A catalogue item with `status = 'discontinued'`: no longer sold, may still appear in past orders.
_Avoid_: Esgotado, fora de linha

**Produto em breve**:
A catalogue item with `status = 'coming_soon'`: not sellable yet, no confirmed arrival date in the data.
_Avoid_: Pré-venda, lançamento (implies a commitment the data cannot support)

**Promoção ativa**:
A `promotions` row with `is_active = 1`. Only these may be quoted to a customer; anything else is treated as
expired.
_Avoid_: Desconto (unqualified), oferta

**Preço promocional**:
The `price_brl` of a product with an active promotion applied. Always presented together with the original
price and the discount percentage.
_Avoid_: Preço final, preço de custo

**Política**:
A rule from the internal manual (`data/políticas_da_loja.pdf`), cited by section when applied — e.g. the
7-day right of withdrawal (§4.1) or the no-stacking rule (§6.2).
_Avoid_: Regra (in agent-facing text), diretriz

**Fora de escopo**:
A request the store cannot serve: accessories (strings, cables, picks, pedals, amps, cases), other
retailers, or anything unrelated to musical instruments. Answered by stating the store's scope, never by
inventing a partner or a product.
_Avoid_: Recusa, não posso ajudar (as the whole answer)

**Identidade verificada**:
The session state reached after order id + phone suffix match. Until then, no order detail leaves the
system.
_Avoid_: Autenticado, login

**Handoff**:
Transfer of the conversation to a human attendant, used for complaints and for anything the agent is not
authorised to decide.
_Avoid_: Escalação (in agent-facing text), transferência

**Transcrição**:
A committed Markdown record of a scripted run, produced by the scenario runner, showing customer turns,
agent turns and every tool call.
_Avoid_: Exemplo (when referring to the file), log
