<script setup lang="ts">
import type { CustomerDetail, Product } from '../types'
import { ref, watch } from 'vue'
import { fetchProducts } from '../api'

const props = defineProps<{
  customer: CustomerDetail | null
}>()

const products = ref<Product[]>([])
const productSearch = ref('')
const showProductSearch = ref(false)

watch(() => props.customer, async () => {
  if (props.customer?.orders.length) {
    showProductSearch.value = false
  }
})

async function searchProducts() {
  if (!productSearch.value.trim()) {
    products.value = []
    return
  }
  products.value = await fetchProducts(productSearch.value.trim())
}

function formatPrice(p: number): string {
  return `¥${p.toFixed(2)}`
}
</script>

<template>
  <div class="info-panel">
    <!-- 客户信息 -->
    <div class="panel-section" v-if="customer">
      <h4>客户信息</h4>
      <div class="customer-card">
        <div class="card-avatar">{{ customer.avatar }}</div>
        <div class="card-name">{{ customer.name }}</div>
        <div class="card-level">{{ customer.level }}</div>
      </div>

      <!-- 订单信息 -->
      <div v-if="customer.orders.length" class="orders-section">
        <h4>历史订单</h4>
        <div v-for="order in customer.orders" :key="order.order_id" class="order-card">
          <div class="order-header">
            <span class="order-id">{{ order.order_id }}</span>
            <span class="order-status">{{ order.status }}</span>
          </div>
          <div class="order-date">{{ order.date }}</div>
          <div v-for="item in order.items" :key="item.product_id" class="order-item">
            <span>{{ item.product_name }}</span>
            <span>{{ item.color }} / {{ item.size }} × {{ item.quantity }}</span>
          </div>
          <div class="order-total">合计：{{ formatPrice(order.total) }}</div>
        </div>
      </div>

      <div v-else class="no-orders">
        <p>暂无历史订单</p>
      </div>
    </div>

    <div class="panel-section" v-else>
      <h4>客户信息</h4>
      <p class="empty-hint">选择左侧客户查看详情</p>
    </div>

    <!-- 商品查询 -->
    <div class="panel-section product-search-section">
      <h4>商品查询</h4>
      <div class="search-row">
        <input
          v-model="productSearch"
          @keydown.enter="searchProducts"
          placeholder="输入商品名称搜索..."
          class="search-input"
        />
        <button @click="searchProducts" class="search-btn">搜索</button>
      </div>
      <div v-if="products.length" class="product-results">
        <div v-for="p in products" :key="p.id" class="product-card">
          <div class="product-name">{{ p.name }}</div>
          <div class="product-info">
            <span class="product-price">{{ formatPrice(p.price) }}</span>
            <span class="product-stock" :class="{ low: p.stock < 20 }">
              库存 {{ p.stock }}
            </span>
          </div>
          <div class="product-meta">
            {{ p.category }} | 尺码: {{ p.sizes.join('/') }} | 颜色: {{ p.colors.join('、') }}
          </div>
          <div class="product-desc">{{ p.description }}</div>
          <div class="product-after-sales">
            <div class="as-item">
              <span class="as-label">🛡️ 保修</span>
              <span class="as-text">{{ p.after_sales.warranty }}</span>
            </div>
            <div class="as-item">
              <span class="as-label">↩️ 退换</span>
              <span class="as-text">{{ p.after_sales.return_policy }}</span>
            </div>
            <div class="as-item" v-if="p.after_sales.notes">
              <span class="as-label">📝 提示</span>
              <span class="as-text">{{ p.after_sales.notes }}</span>
            </div>
          </div>
        </div>
      </div>
      <div v-else-if="productSearch && !products.length" class="no-results">
        未找到匹配商品
      </div>
    </div>
  </div>
</template>

<style scoped>
.info-panel {
  width: 280px;
  min-width: 280px;
  background: #f8f9fb;
  border-left: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
}

.panel-section {
  padding: 16px;
  border-bottom: 1px solid #e5e7eb;
}

.panel-section h4 {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.customer-card {
  text-align: center;
  padding: 12px 0;
}

.card-avatar {
  font-size: 40px;
  margin-bottom: 6px;
}

.card-name {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.card-level {
  font-size: 12px;
  color: #6366f1;
  margin-top: 2px;
}

.orders-section h4 {
  margin-top: 8px;
}

.order-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.order-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.order-id {
  font-size: 12px;
  font-weight: 600;
  color: #374151;
  font-family: monospace;
}

.order-status {
  font-size: 11px;
  color: #22c55e;
  background: #f0fdf4;
  padding: 1px 6px;
  border-radius: 3px;
}

.order-date {
  font-size: 11px;
  color: #9ca3af;
  margin-bottom: 6px;
}

.order-item {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #6b7280;
  padding: 2px 0;
}

.order-total {
  font-size: 12px;
  font-weight: 600;
  color: #1f2937;
  text-align: right;
  margin-top: 4px;
  padding-top: 4px;
  border-top: 1px dashed #e5e7eb;
}

.no-orders p {
  font-size: 13px;
  color: #9ca3af;
  text-align: center;
  padding: 20px 0;
}

.empty-hint {
  font-size: 13px;
  color: #9ca3af;
  text-align: center;
  padding: 20px 0;
}

.product-search-section {
  flex: 1;
}

.search-row {
  display: flex;
  gap: 6px;
}

.search-input {
  flex: 1;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  padding: 7px 10px;
  font-size: 13px;
  outline: none;
}

.search-input:focus {
  border-color: #6366f1;
}

.search-btn {
  padding: 7px 12px;
  background: #6366f1;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
}

.search-btn:hover {
  background: #4f46e5;
}

.product-results {
  margin-top: 10px;
}

.product-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px;
  margin-bottom: 6px;
}

.product-name {
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 4px;
}

.product-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 3px;
}

.product-price {
  font-size: 14px;
  font-weight: 600;
  color: #ef4444;
}

.product-stock {
  font-size: 11px;
  color: #22c55e;
}

.product-stock.low {
  color: #f59e0b;
}

.product-meta {
  font-size: 11px;
  color: #9ca3af;
}

.no-results {
  font-size: 13px;
  color: #9ca3af;
  text-align: center;
  padding: 16px 0;
}

.product-desc {
  font-size: 11px;
  color: #6b7280;
  line-height: 1.6;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed #e5e7eb;
}

.product-after-sales {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed #e5e7eb;
}

.as-item {
  display: flex;
  gap: 4px;
  margin-bottom: 3px;
  font-size: 11px;
  line-height: 1.5;
}

.as-label {
  flex-shrink: 0;
  color: #6366f1;
  font-weight: 500;
}

.as-text {
  color: #6b7280;
}
</style>
