"""Tool schemas exposed to the model, and the dispatcher that executes them."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from . import database, datasource, policies

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": (
                "Busca produtos no catálogo da loja. Use para perguntas de catálogo, faixa de preço, "
                "categoria ou 'o que vocês têm de X'. O preço retornado já considera promoção ativa."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "termos livres: marca, modelo, tipo (ex.: 'violão nylon')"},
                    "category": {"type": "string", "description": "guitarras, baixos, baterias, teclados, violões, ukuleles"},
                    "max_price": {"type": "number", "description": "preço máximo em BRL (comparado ao preço final)"},
                    "min_price": {"type": "number", "description": "preço mínimo em BRL"},
                    "only_available": {
                        "type": "boolean",
                        "description": "default true; false inclui itens sem estoque, em breve e descontinuados",
                    },
                    "limit": {"type": "integer", "description": "máximo de itens retornados (default 8)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product",
            "description": "Detalhe de um produto por id ou nome: preço, promoção, estoque, specs, descrição.",
            "parameters": {
                "type": "object",
                "properties": {"product_id_or_name": {"type": "string", "description": "id numérico ou nome do produto"}},
                "required": ["product_id_or_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Checa disponibilidade de um produto (ativo E com estoque). Use antes de afirmar que algo está disponível.",
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "integer"}},
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_active_promotions",
            "description": "Lista as promoções ATIVAS hoje. Promoções vencidas não aparecem: se o cliente citar uma, use esta ferramenta para verificar antes de responder.",
            "parameters": {
                "type": "object",
                "properties": {"category": {"type": "string", "description": "filtra por categoria (opcional)"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "payment_options",
            "description": (
                "Formas de pagamento e parcelamento cálculados para um valor: PIX (5% só sem promoção), "
                "débito, crédito (parcelas conforme mínimo de parcela) e boleto. Use SEMPRE para falar de "
                "parcelas ou desconto de PIX — não calcule você mesmo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "use o produto para pegar o preço final automaticamente"},
                    "amount_brl": {"type": "number", "description": "ou informe um valor já obtido de outra ferramenta"},
                    "is_promotional": {"type": "boolean", "description": "obrigatório quando amount_brl é informado e o valor é promocional"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": (
                "Consulta um pedido. Exige número do pedido E os 4 últimos dígitos do telefone cadastrado. "
                "Retorna status, itens, total, rastreio e os prazos de devolução/defeito calculados."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer"},
                    "phone_last4": {"type": "string", "description": "quatro últimos dígitos do telefone do cadastro"},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_policy",
            "description": "Texto exato de uma seção do manual interno (ex.: '4.1', '6.2', '3.1') para citar com precisão.",
            "parameters": {
                "type": "object",
                "properties": {"section": {"type": "string"}},
                "required": ["section"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "store_info",
            "description": "Dados fixos da loja: endereço, telefones, horário de funcionamento, frete, escopo e contato humano.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": (
                "Registra um handoff para atendente humano. Use em reclamação, pedido de exceção a política, "
                "negociação de preço ou quando faltar informação que você não pode verificar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "motivo curto e específico do encaminhamento"},
                    "summary": {"type": "string", "description": "resumo do que o cliente precisa, em 1-2 frases"},
                },
                "required": ["reason"],
            },
        },
    },
]


class ToolBox:
    """Executes tool calls against the database, enforcing the identity gate and side effects."""

    def __init__(self, conn: sqlite3.Connection, session_id: str):
        self.conn = conn
        self.session_id = session_id

    # -- helpers ------------------------------------------------------------------
    def _bound_last4(self, order_id: int) -> str | None:
        """Last four digits of the phone on file, only if this session already verified this order."""
        if database.get_bound_order(self.conn, self.session_id) != order_id:
            return None
        row = self.conn.execute(
            """SELECT c.phone FROM store_orders o JOIN store_customers c ON c.customer_id = o.customer_id
               WHERE o.order_id = ?""",
            (order_id,),
        ).fetchone()
        if not row:
            return None
        digits = "".join(ch for ch in row["phone"] if ch.isdigit())
        return digits[-4:]

    def _bind(self, order_id: int) -> None:
        row = self.conn.execute(
            "SELECT customer_id FROM store_orders WHERE order_id = ?", (order_id,)
        ).fetchone()
        if row:
            database.bind_customer(self.conn, self.session_id, row["customer_id"], order_id)

    # -- dispatch -----------------------------------------------------------------
    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            handler = getattr(self, f"_tool_{name}", None)
            if handler is None:
                return {"error": f"ferramenta desconhecida: {name}"}
            return handler(**(arguments or {}))
        except TypeError as exc:
            return {"error": f"argumentos inválidos para {name}: {exc}"}
        except Exception as exc:  # noqa: BLE001 - a tool failure must not kill the conversation
            return {"error": f"falha ao executar {name}: {exc}"}

    # -- tools --------------------------------------------------------------------
    def _tool_search_products(
        self,
        query: str | None = None,
        category: str | None = None,
        max_price: float | None = None,
        min_price: float | None = None,
        only_available: bool = True,
        limit: int = 8,
    ) -> dict[str, Any]:
        return datasource.search_products(
            self.conn,
            query=query,
            category=category,
            max_price=max_price,
            min_price=min_price,
            only_available=only_available,
            limit=int(limit),
        )

    def _tool_get_product(self, product_id_or_name: str) -> dict[str, Any]:
        return datasource.get_product(self.conn, product_id_or_name)

    def _tool_check_availability(self, product_id: int) -> dict[str, Any]:
        return datasource.check_availability(self.conn, product_id)

    def _tool_list_active_promotions(self, category: str | None = None) -> dict[str, Any]:
        return datasource.list_active_promotions(self.conn, category=category)

    def _tool_payment_options(
        self,
        product_id: int | None = None,
        amount_brl: float | None = None,
        is_promotional: bool | None = None,
    ) -> dict[str, Any]:
        if product_id is not None:
            product = datasource.get_product(self.conn, product_id)
            if not product.get("found"):
                return {"error": "produto não encontrado", "product_id": product_id}
            price = product["price"]
            options = datasource.payment_options(price["price_brl"], price["is_promotional"])
            options["product"] = {"product_id": product_id, "name": product["name"]}
            return options
        if amount_brl is None:
            return {"error": "informe product_id ou amount_brl"}
        return datasource.payment_options(float(amount_brl), bool(is_promotional))

    def _tool_get_order(self, order_id: int, phone_last4: str | None = None) -> dict[str, Any]:
        digits = phone_last4
        if not digits:
            digits = self._bound_last4(int(order_id))
            if digits is None:
                return {
                    "found": False,
                    "error": "informe os quatro últimos dígitos do telefone cadastrado",
                }
        result = datasource.get_order(self.conn, order_id, digits)
        if result.get("found"):
            self._bind(int(order_id))
        return result

    def _tool_get_policy(self, section: str) -> dict[str, Any]:
        return policies.get_policy(section)

    def _tool_store_info(self) -> dict[str, Any]:
        return datasource.store_info()

    def _tool_escalate_to_human(self, reason: str, summary: str | None = None) -> dict[str, Any]:
        handoff_id = database.record_handoff(self.conn, self.session_id, f"{reason} — {summary or ''}".strip(" —"))
        info = datasource.store_info()["human_handoff"]
        return {
            "registered": True,
            "handoff_id": handoff_id,
            "contact": info["contact"],
            "sla": info["sla"],
            "note": "avise o cliente que um atendente humano vai retomar a conversa pelo WhatsApp do cadastro",
        }


def tool_call_record(name: str, arguments: str | dict, result: dict) -> dict[str, Any]:
    """Compact record for the committed transcripts."""
    args = arguments
    if isinstance(arguments, str):
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            args = {"raw": arguments}
    return {"tool": name, "arguments": args, "result": result}
