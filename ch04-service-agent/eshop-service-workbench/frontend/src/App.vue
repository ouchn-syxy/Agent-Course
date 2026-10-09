<script setup lang="ts">
import { ref, onMounted } from 'vue'
import CustomerList from './components/CustomerList.vue'
import ChatWindow from './components/ChatWindow.vue'
import ChatInput from './components/ChatInput.vue'
import CustomerInfoPanel from './components/CustomerInfoPanel.vue'
import {
  fetchCustomers,
  fetchCustomerDetail,
  fetchChatHistory,
  sendMessage,
  resetAll,
} from './api'
import type { CustomerSummary, CustomerDetail, ChatMessage } from './types'

const customers = ref<CustomerSummary[]>([])
const selectedCustomer = ref<CustomerDetail | null>(null)
const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const loading = ref(false)
const selectedId = ref<string | null>(null)

onMounted(() => refreshCustomers())

async function refreshCustomers() {
  customers.value = await fetchCustomers()
}

async function selectCustomer(id: string) {
  selectedId.value = id
  loading.value = true
  try {
    const [detail, chat] = await Promise.all([
      fetchCustomerDetail(id),
      fetchChatHistory(id),
    ])
    selectedCustomer.value = detail
    messages.value = chat.messages
  } finally {
    loading.value = false
  }
}

function nowStr(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

async function handleSend() {
  if (!selectedId.value || !inputText.value.trim() || loading.value) return

  const content = inputText.value.trim()
  inputText.value = ''
  loading.value = true

  // 乐观更新：立即在本地显示客服消息
  const optimisticMsg: ChatMessage = {
    id: 'temp-' + Date.now(),
    sender: 'agent',
    content,
    timestamp: nowStr(),
  }
  messages.value = [...messages.value, optimisticMsg]

  try {
    const res = await sendMessage(selectedId.value, content)
    messages.value = res.messages
    await refreshCustomers()
  } finally {
    loading.value = false
  }
}

async function handleReset() {
  if (!confirm('确定要重置所有会话吗？')) return
  await resetAll()
  selectedId.value = null
  selectedCustomer.value = null
  messages.value = []
  inputText.value = ''
  await refreshCustomers()
}
</script>

<template>
  <div class="app-container">
    <!-- 顶部工具栏 -->
    <header class="top-bar">
      <div class="top-bar-left">
        <h1>🛒 网店客服工作台</h1>
      </div>
      <div class="top-bar-right">
        <button class="reset-btn" @click="handleReset">🔄 重置</button>
      </div>
    </header>

    <!-- 主体三栏布局 -->
    <div class="main-layout">
      <CustomerList
        :customers="customers"
        :selectedId="selectedId"
        @select="selectCustomer"
      />

      <div class="chat-column">
        <ChatWindow
          :messages="messages"
          :customerName="selectedCustomer?.name ?? ''"
          :loading="loading"
        />
        <ChatInput
          v-model="inputText"
          :disabled="!selectedId || loading"
          @send="handleSend"
        />
      </div>

      <CustomerInfoPanel :customer="selectedCustomer" />
    </div>
  </div>
</template>

<style scoped>
.app-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #fff;
}

.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  height: 52px;
  background: #1e1b4b;
  color: #fff;
  flex-shrink: 0;
}

.top-bar-left h1 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.reset-btn {
  padding: 6px 14px;
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}

.reset-btn:hover {
  background: rgba(255, 255, 255, 0.25);
}

.main-layout {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.chat-column {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
</style>
