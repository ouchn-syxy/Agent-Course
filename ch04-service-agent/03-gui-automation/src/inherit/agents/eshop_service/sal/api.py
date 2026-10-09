"""SAL（Service Abstraction Layer）— 查询接口实现。

提供商品、订单、物流、售后政策、库存等查询接口。
数据结构与 eshop-service-workbench 平台接口保持一致。
Mock 数据定义在 mock.py 中。
"""

from inherit.agents.eshop_service.sal.mock import (
	EXCHANGE_POLICY,
	LOGISTICS,
	ORDER_LOGISTICS_MAP,
	ORDER_MAP,
	PRODUCTS,
	RETURN_POLICY,
)
from inherit.agents.eshop_service.sal.types import Product
from inherit.llm.tool_registry import ToolDef


# ══════════════════════════════════════════════
# 查询函数
# ══════════════════════════════════════════════

def _find_product(name: str) -> Product | None:
	"""模糊匹配商品名称。"""
	name_lower = name.lower()
	for p in PRODUCTS:
		if name_lower in p.name.lower() or p.name.lower() in name_lower:
			return p
	return None


def query_product_info(product_name: str) -> str:
	"""查询商品详细信息。"""
	p = _find_product(product_name)
	if not p:
		return f"未找到「{product_name}」的商品信息，请确认商品名称是否正确。"
	return (
		f"【{p.name}】\n"
		f"价格: ¥{p.price:.0f}\n"
		f"品类: {p.category}\n"
		f"可选尺码: {', '.join(p.sizes)}\n"
		f"可选颜色: {', '.join(p.colors)}\n"
		f"库存: {p.stock}件\n"
		f"简介: {p.description}"
	)


def query_inventory(product_name: str, size: str = "", color: str = "") -> str:
	"""查询商品库存。"""
	p = _find_product(product_name)
	if not p:
		return f"未找到「{product_name}」的库存信息。"

	if size and size not in p.sizes:
		return f"【{p.name}】不支持 {size} 码。"
	if color and color not in p.colors:
		return f"【{p.name}】不支持{color}。"
	if size and color:
		return f"【{p.name}】{color} {size} 码有货，当前商品库存记录为 {p.stock} 件。"

	return (
		f"【{p.name}】库存查询（未指定完整颜色和尺码组合）:\n"
		f"  可选尺码: {', '.join(p.sizes)}\n"
		f"  可选颜色: {', '.join(p.colors)}\n"
		f"  商品总库存记录: {p.stock} 件\n"
		"  如需确认具体款式，请同时提供颜色和尺码。"
	)


def query_order_info(order_id: str) -> str:
	"""查询订单详情。"""
	order = ORDER_MAP.get(order_id)
	if not order:
		return f"未找到订单「{order_id}」，请确认订单号是否正确。"

	items_text = ", ".join(
		f"{it.product_name} {it.size}码 {it.color} ×{it.quantity}"
		for it in order.items
	)
	return (
		f"【订单 {order.order_id}】\n"
		f"商品: {items_text}\n"
		f"金额: ¥{order.total:.0f}\n"
		f"状态: {order.status}\n"
		f"下单时间: {order.date}"
	)


def query_return_policy(product_name: str = "") -> str:
	"""查询退货政策。"""
	result = RETURN_POLICY["general"]
	if product_name:
		p = _find_product(product_name)
		if p:
			result += f"\n\n「{p.name}」适用普通退货规则（7天无理由，保持原状）。"
			return result
	result += f"\n\n{RETURN_POLICY['red_lines']}"
	return result


def query_exchange_policy(product_name: str = "") -> str:
	"""查询换货政策。"""
	result = EXCHANGE_POLICY["general"]
	if product_name:
		p = _find_product(product_name)
		if p:
			result += f"\n\n「{p.name}」可换尺码: {', '.join(p.sizes)}；可换颜色: {', '.join(p.colors)}。"
			return result
	return result


# ══════════════════════════════════════════════
# Tool Definitions（函数 + OpenAI Function Calling 格式合并）
# ══════════════════════════════════════════════

TOOLS: dict[str, ToolDef] = {
	"query_product_info": ToolDef(
		name="query_product_info",
		description="查询商品详细信息（价格、材质、尺码、颜色、简介等），当客户询问商品相关问题时调用",
		parameters={
			"product_name": {"type": "string", "description": "商品名称，如 红色连衣裙、运动鞋"},
		},
		func=query_product_info,
		required=["product_name"],
	),
	"query_order_info": ToolDef(
		name="query_order_info",
		description="查询客户订单详情（商品、金额、状态、地址等），当客户询问订单相关问题时调用",
		parameters={
			"order_id": {"type": "string", "description": "订单号，如 ORD123456"},
		},
		func=query_order_info,
		required=["order_id"],
	),
	"query_inventory": ToolDef(
		name="query_inventory",
		description="查询商品库存情况（各尺码是否有货），当客户询问有没有货、是否有某尺码时调用",
		parameters={
			"product_name": {"type": "string", "description": "商品名称"},
			"size": {"type": "string", "description": "具体尺码（可选），如 M、42码"},
			"color": {"type": "string", "description": "具体颜色（可选），如 红色"},
		},
		func=query_inventory,
		required=["product_name"],
	),
	"query_return_policy": ToolDef(
		name="query_return_policy",
		description="查询退货政策和条件，当客户询问退货、退款规则时调用",
		parameters={
			"product_name": {"type": "string", "description": "商品名称（可选），用于判断是否属于特殊品类"},
		},
		func=query_return_policy,
		required=[],
	),
	"query_exchange_policy": ToolDef(
		name="query_exchange_policy",
		description="查询换货政策和可选尺码/颜色，当客户询问换货、换尺码时调用",
		parameters={
			"product_name": {"type": "string", "description": "商品名称（可选）"},
		},
		func=query_exchange_policy,
		required=[],
	),
}
