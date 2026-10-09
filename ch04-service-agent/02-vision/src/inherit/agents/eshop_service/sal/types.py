"""与 eshop-service-workbench 平台接口结构一致的数据类型定义。"""

from pydantic import BaseModel


# ══════════════════════════════════════════════
# 商品相关
# ══════════════════════════════════════════════

class AfterSales(BaseModel):
	"""商品售后信息。"""
	warranty: str
	return_policy: str
	notes: str


class Product(BaseModel):
	"""商品信息（与 GET /api/products 响应一致）。"""
	id: str
	name: str
	price: float
	stock: int
	sizes: list[str]
	colors: list[str]
	category: str
	description: str
	after_sales: AfterSales
	image_url: str = ""


class StockCheckResult(BaseModel):
	"""库存检查结果（与 ProductService.check_stock 返回值一致）。"""
	available: bool
	reason: str = ""
	product: Product | None = None
	stock: int = 0


# ══════════════════════════════════════════════
# 订单相关
# ══════════════════════════════════════════════

class OrderItem(BaseModel):
	"""订单商品明细。"""
	product_id: str
	product_name: str
	price: float
	quantity: int
	size: str
	color: str


class Order(BaseModel):
	"""订单信息（与 GET /api/customers/{id} 中 orders[] 一致）。"""
	order_id: str
	date: str
	status: str
	items: list[OrderItem]
	total: float


# ══════════════════════════════════════════════
# 客户相关
# ══════════════════════════════════════════════

class CustomerSummary(BaseModel):
	"""客户列表摘要（与 GET /api/customers 响应一致）。"""
	id: str
	name: str
	avatar: str
	level: str
	last_message: str
	last_message_time: str
	last_sender: str
	unread_count: int
	is_handled: bool
	need_human: bool


class Customer(BaseModel):
	"""客户详情（与 GET /api/customers/{id} 响应一致）。"""
	id: str
	name: str
	avatar: str
	level: str
	orders: list[Order]
	persona: str


# ══════════════════════════════════════════════
# 聊天相关
# ══════════════════════════════════════════════

class ChatMessage(BaseModel):
	"""单条聊天消息（与 GET /api/chat/{customer_id} 中 messages[] 一致）。"""
	id: str
	sender: str  # "customer" | "agent"
	content: str
	timestamp: str


class ChatHistory(BaseModel):
	"""聊天记录（与 GET /api/chat/{customer_id} 响应一致）。"""
	customer_id: str
	customer_name: str
	messages: list[ChatMessage]


class SendMessageResponse(BaseModel):
	"""发送客服消息响应（与 POST /api/chat/{customer_id}/send 响应一致）。"""
	customer_message: str
	messages: list[ChatMessage]
	is_handled: bool


# ══════════════════════════════════════════════
# 物流相关
# ══════════════════════════════════════════════

class Logistics(BaseModel):
	"""物流信息。"""
	tracking_no: str
	carrier: str
	status: str
	history: list[str]



