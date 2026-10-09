/** 客户摘要（列表用） */
export interface CustomerSummary {
  id: string
  name: string
  avatar: string
  level: string
  last_message: string
  last_message_time: string
  last_sender: 'customer' | 'agent'
  unread_count: number
  is_handled: boolean
  need_human: boolean
}

/** 订单商品项 */
export interface OrderItem {
  product_id: string
  product_name: string
  price: number
  quantity: number
  size: string
  color: string
}

/** 订单 */
export interface Order {
  order_id: string
  date: string
  status: string
  items: OrderItem[]
  total: number
}

/** 客户详情（个人信息 + 订单） */
export interface CustomerDetail {
  id: string
  name: string
  avatar: string
  level: string
  orders: Order[]
  persona: string
}

/** 聊天消息 */
export interface ChatMessage {
  id: string
  sender: 'customer' | 'agent'
  content: string
  timestamp: string
}

/** 聊天记录响应 */
export interface ChatHistoryResponse {
  customer_id: string
  customer_name: string
  messages: ChatMessage[]
}

/** 发送消息响应 */
export interface SendMessageResponse {
  customer_message: string
  messages: ChatMessage[]
  is_handled: boolean
}

/** 商品售后信息 */
export interface AfterSales {
  warranty: string
  return_policy: string
  notes: string
}

/** 商品 */
export interface Product {
  id: string
  name: string
  price: number
  stock: number
  sizes: string[]
  colors: string[]
  category: string
  description: string
  after_sales: AfterSales
  image_url: string
}

/** 商品搜索筛选条件 */
export type MessageType = '售前咨询' | '售后服务' | '投诉' | '垃圾广告'

/** 消息类型标签映射 */
export const MESSAGE_TYPE_LABELS: Record<MessageType, string> = {
  '售前咨询': '售前',
  '售后服务': '售后',
  '投诉': '投诉',
  '垃圾广告': '垃圾',
}

export const MESSAGE_TYPE_COLORS: Record<MessageType, string> = {
  '售前咨询': '#22c55e',
  '售后服务': '#eab308',
  '投诉': '#ef4444',
  '垃圾广告': '#6b7280',
}
