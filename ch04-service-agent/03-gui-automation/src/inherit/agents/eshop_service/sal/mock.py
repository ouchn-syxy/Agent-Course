"""Mock 数据 — 与 eshop-service-workbench 平台接口结构一致。"""

from inherit.agents.eshop_service.sal.types import (
	AfterSales,
	Customer,
	Logistics,
	Order,
	OrderItem,
	Product,
)

# ══════════════════════════════════════════════
# 商品
# ══════════════════════════════════════════════

PRODUCTS: list[Product] = [
	Product(
		id="P001",
		name="红色连衣裙",
		price=299.00,
		stock=50,
		sizes=["S", "M", "L", "XL"],
		colors=["红色", "黑色"],
		category="女装",
		description="修身显瘦A字裙，适合春夏穿着。面料柔软顺滑，V领修饰脸型。",
		after_sales=AfterSales(
			warranty="自签收之日起7天内，如有质量问题可免费换新。",
			return_policy="支持7天无理由退换货，需保持商品原状、吊牌完整。退回运费由买家承担（质量问题除外）。",
			notes="深色款首次洗涤可能有轻微浮色，建议单独洗涤。",
		),
	),
	Product(
		id="P002",
		name="白色衬衫",
		price=199.00,
		stock=120,
		sizes=["S", "M", "L", "XL", "XXL"],
		colors=["白色", "浅蓝", "粉色"],
		category="女装",
		description="纯棉免烫衬衫，机洗甩干即穿。经典翻领，后腰收省设计。",
		after_sales=AfterSales(
			warranty="自签收之日起15天内，纽扣脱落、缝线开裂等做工问题免费换新。",
			return_policy="支持7天无理由退换货，需吊牌未剪、未经洗涤。",
			notes="白色款建议与深色衣物分开洗涤。",
		),
	),
	Product(
		id="P003",
		name="黑色休闲裤",
		price=259.00,
		stock=80,
		sizes=["S", "M", "L", "XL"],
		colors=["黑色", "深灰", "卡其"],
		category="女装",
		description="高腰直筒裤，弹力舒适。双面针织结构，内层磨毛亲肤。",
		after_sales=AfterSales(
			warranty="自签收之日起30天内，起球超标、严重褪色等质量问题免费退换。",
			return_policy="支持7天无理由退换货，需保持商品整洁、吊牌完整。",
			notes="深色款前两次建议单独或同色系洗涤。",
		),
	),
	Product(
		id="P005",
		name="运动跑鞋",
		price=459.00,
		stock=35,
		sizes=["36", "37", "38", "39", "40", "41"],
		colors=["白/粉", "黑/金", "灰/蓝"],
		category="鞋履",
		description="轻便透气跑步鞋，3D飞织鞋面，EVA+TPU双密度中底。",
		after_sales=AfterSales(
			warranty="自签收之日起30天内，鞋底开胶、鞋面脱线等质量问题免费换新。",
			return_policy="支持7天无理由退换货，需鞋底无磨损、不影响二次销售。",
			notes="日常清洁用湿布擦拭鞋面，勿机洗或暴晒。",
		),
	),
]

ORDERS: list[Order] = [
	Order(
		order_id="20260720-0005",
		date="2026-07-20",
		status="已签收",
		items=[
			OrderItem(product_id="P001", product_name="红色连衣裙", price=299.00, quantity=1, size="M", color="红色"),
		],
		total=299.00,
	),
	Order(
		order_id="20230615-0002",
		date="2026-06-15",
		status="已签收",
		items=[
			OrderItem(product_id="P005", product_name="运动跑鞋", price=459.00, quantity=1, size="38", color="白/粉"),
		],
		total=459.00,
	),
	Order(
		order_id="20230705-0003",
		date="2026-07-05",
		status="已签收",
		items=[
			OrderItem(product_id="P010", product_name="羽绒服", price=899.00, quantity=1, size="L", color="米白"),
		],
		total=899.00,
	),
	Order(
		order_id="20230620-0005",
		date="2026-06-20",
		status="已签收",
		items=[
			OrderItem(product_id="P002", product_name="白色衬衫", price=199.00, quantity=1, size="XL", color="白色"),
		],
		total=199.00,
	),
]

LOGISTICS: dict[str, Logistics] = {
	"TRK001": Logistics(
		tracking_no="TRK001",
		carrier="顺丰速运",
		status="已签收",
		history=["2026-07-11 揽件", "2026-07-12 运输中", "2026-07-13 派送中", "2026-07-13 已签收"],
	),
	"TRK002": Logistics(
		tracking_no="TRK002",
		carrier="中通快递",
		status="运输中",
		history=["2026-07-15 揽件", "2026-07-16 到达中转站"],
	),
	"TRK003": Logistics(
		tracking_no="TRK003",
		carrier="圆通速递",
		status="待揽件",
		history=[],
	),
}

RETURN_POLICY: dict[str, str] = {
	"general": "支持7天无理由退货，商品须保持原状（未穿着、未洗涤、吊牌完整）。退回运费由买家承担（质量问题除外）。退款在仓库签收后1-3个工作日到账。",
	"red_lines": "以下商品不支持退货：内衣/内裤、定制商品、已拆封的食品/化妆品。",
}

EXCHANGE_POLICY: dict[str, str] = {
	"general": "支持7天内换货（同款不同尺码/颜色）。退回运费由买家承担（质量问题除外）。如需换不同款式，请先退货再重新下单。",
}

ORDER_LOGISTICS_MAP: dict[str, str] = {
	"20260720-0005": "TRK001",
	"20230615-0002": "TRK002",
	"20230705-0003": "TRK003",
}

CUSTOMERS: list[Customer] = [
	Customer(
		id="cust_005",
		name="钱七",
		avatar="👨‍💼",
		level="普通会员",
		orders=[o for o in ORDERS if o.order_id == "20260720-0005"],
		persona="换货咨询型客户，希望把红色连衣裙 M 码换成黑色 L 码",
	),
	Customer(
		id="cust_002",
		name="李四",
		avatar="👨",
		level="普通会员",
		orders=[o for o in ORDERS if o.order_id == "20230615-0002"],
		persona="售后型客户，买的跑鞋开胶了要退货",
	),
	Customer(
		id="cust_003",
		name="王五",
		avatar="👩‍🦰",
		level="VIP会员",
		orders=[o for o in ORDERS if o.order_id == "20230705-0003"],
		persona="愤怒的投诉客户，要求赔偿，情绪激动",
	),
]

# ══════════════════════════════════════════════
# 快速索引
# ══════════════════════════════════════════════

PRODUCT_MAP: dict[str, Product] = {}
for p in PRODUCTS:
	PRODUCT_MAP[p.name] = p
	PRODUCT_MAP[p.id] = p

ORDER_MAP: dict[str, Order] = {o.order_id: o for o in ORDERS}

CUSTOMER_MAP: dict[str, Customer] = {c.id: c for c in CUSTOMERS}
