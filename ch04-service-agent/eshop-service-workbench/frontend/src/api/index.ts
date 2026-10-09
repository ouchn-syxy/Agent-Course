import type {
  CustomerSummary,
  CustomerDetail,
  ChatHistoryResponse,
  SendMessageResponse,
  Product,
} from '../types'

const BASE = '/api'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(err || `HTTP ${res.status}`)
  }
  return res.json()
}

/** 获取所有客户列表 */
export function fetchCustomers(): Promise<CustomerSummary[]> {
  return request('/customers')
}

/** 获取客户详情 */
export function fetchCustomerDetail(id: string): Promise<CustomerDetail> {
  return request(`/customers/${id}`)
}

/** 获取聊天记录 */
export function fetchChatHistory(customerId: string): Promise<ChatHistoryResponse> {
  return request(`/chat/${customerId}`)
}

/** 发送客服回复 */
export function sendMessage(
  customerId: string,
  content: string,
): Promise<SendMessageResponse> {
  return request(`/chat/${customerId}/send`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
}

/** 获取商品列表（可选搜索） */
export function fetchProducts(search?: string): Promise<Product[]> {
  const query = search ? `?search=${encodeURIComponent(search)}` : ''
  return request(`/products${query}`)
}

/** 获取商品详情 */
export function fetchProduct(id: string): Promise<Product> {
  return request(`/products/${id}`)
}

/** 重置所有会话 */
export function resetAll(): Promise<{ status: string; message: string }> {
  return request('/reset', { method: 'POST' })
}
