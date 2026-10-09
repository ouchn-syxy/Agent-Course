"""SAL（Service Abstraction Layer）— 查询接口实现（对接真实后端）。

提供商品、订单、物流、售后政策、库存等查询接口。
所有数据来自 eshop-service-workbench 后端 HTTP API。
"""

from __future__ import annotations

from urllib.parse import quote

from agents.eshop_service.sal.api_client import APIClient
from config import Config
from inherit.agents.eshop_service.sal.types import Order, Product
from inherit.llm.tool_registry import ToolDef


# ══════════════════════════════════════════════
# 查询函数（闭包捕获 APIClient）
# ══════════════════════════════════════════════

def query_product_info(product_name: str) -> str:
	data: list = client.get(f"/api/products?search={product_name}")
	if not data:
		# 无精确匹配 → 获取全部商品做客户端模糊匹配
		data = client.get("/api/products")

	best: Product | None = None
	name_lower = product_name.lower()
	for item in data:
		p = Product(**item)
		if name_lower in p.name.lower() or p.name.lower() in name_lower:
			best = p
			break

	if not best:
		return f"未找到「{product_name}」的商品信息，请确认商品名称是否正确。"

	return (
		f"【{best.name}】\n"
		f"价格: ¥{best.price:.0f}\n"
		f"品类: {best.category}\n"
		f"可选尺码: {', '.join(best.sizes)}\n"
		f"可选颜色: {', '.join(best.colors)}\n"
		f"库存: {best.stock}件\n"
		f"简介: {best.description}"
	)


def query_inventory(product_name: str, size: str = "", color: str = "") -> str:
	data: list = client.get(f"/api/products?search={quote(product_name)}")
	if not data:
		data = client.get("/api/products")

	best: Product | None = None
	name_lower = product_name.lower()
	for item in data:
		p = Product(**item)
		if name_lower in p.name.lower() or p.name.lower() in name_lower:
			best = p
			break

	if not best:
		return f"未找到「{product_name}」的库存信息。"

	if size and color:
		result: dict = client.get(
			f"/api/products/{best.id}/stock"
			f"?size={quote(size)}&color={quote(color)}"
		)
		if not result.get("available"):
			return f"【{best.name}】{color} {size} 码不可换：{result.get('reason', '库存不足')}"
		return (
			f"【{best.name}】{color} {size} 码有货，"
			f"当前商品库存记录为 {result.get('stock', best.stock)} 件。"
		)

	lines = [f"【{best.name}】库存查询（未指定完整颜色和尺码组合）:"]
	if size:
		lines.append(f"  尺码 {size}: {'支持' if size in best.sizes else '不支持'}")
	if color:
		lines.append(f"  颜色 {color}: {'支持' if color in best.colors else '不支持'}")
	if not size and not color:
		lines.append(f"  可选尺码: {', '.join(best.sizes)}")
		lines.append(f"  可选颜色: {', '.join(best.colors)}")
	lines.append(f"  商品总库存记录: {best.stock} 件")
	lines.append("  如需确认具体款式，请同时提供颜色和尺码。")
	return "\n".join(lines)


def get_all_orders() -> dict[str, Order]:
	"""遍历所有客户获取订单索引。"""
	order_map: dict[str, Order] = {}
	customers: list = client.get("/api/customers")
	for c in customers:
		cust_id: str = c["id"]
		try:
			detail: dict = client.get(f"/api/customers/{cust_id}")
			for o in detail.get("orders", []):
				order_map[o["order_id"]] = Order(**o)
		except Exception:
			pass
	return order_map


def query_order_info(order_id: str) -> str:
	order_map: dict[str, Order] = get_all_orders()
	order = order_map.get(order_id)
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
	result = "支持7天无理由退货，商品须保持原状（未穿着、未洗涤、吊牌完整）。退回运费由买家承担（质量问题除外）。"

	if product_name:
		try:
			data: list = client.get(f"/api/products?search={product_name}")
			if data:
				p = Product(**data[0])
				result += f"\n\n「{p.name}」售后说明: {p.after_sales.return_policy}"
				result += f"\n注意事项: {p.after_sales.notes}"
				return result
		except Exception:
			pass

	result += "\n\n以下商品不支持退货：内衣/内裤、定制商品、已拆封的食品/化妆品。"
	return result


def query_exchange_policy(product_name: str = "") -> str:
	result = "支持7天内换货（同款不同尺码/颜色）。退回运费由买家承担（质量问题除外）。如需换不同款式，请先退货再重新下单。"

	if product_name:
		try:
			data: list = client.get(f"/api/products?search={product_name}")
			if data:
				p = Product(**data[0])
				result += f"\n\n「{p.name}」可换尺码: {', '.join(p.sizes)}；可换颜色: {', '.join(p.colors)}。"
				result += f"\n售后政策: {p.after_sales.return_policy}"
				return result
		except Exception:
			pass

	return result


# ══════════════════════════════════════════════
# 初始化
# ══════════════════════════════════════════════

cfg: Config = Config.from_yaml()
client: APIClient = APIClient(cfg.backend.host)

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
			"order_id": {"type": "string", "description": "订单号，如 20260720-0005"},
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

# ═══════════════════════════════════════════════════════════════════════
# Demo
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

	# 逐个测试
	for name in [
		"query_product_info",
		"query_inventory",
		"query_order_info",
		"query_return_policy",
		"query_exchange_policy"
	]:
		tool = TOOLS[name]
		print("=" * 60)
		print(f"🔧 {name}")
		print("=" * 60)
		try:
			if name == "query_product_info":
				print(tool.func("连衣裙"))
			elif name == "query_inventory":
				print(tool.func("连衣裙", "M"))
			elif name == "query_order_info":
				print(tool.func("20260720-0005"))
			elif name == "query_return_policy":
				print(tool.func("连衣裙"))
			elif name == "query_exchange_policy":
				print(tool.func("连衣裙"))
		except Exception as e:
			print(f"❌ {type(e).__name__}: {e}")
		print()

	print("✅ 全部工具接口 demo 完成")
