<script setup lang="ts">
import type { ChatMessage } from '../types'
import { ref, watch, nextTick } from 'vue'

const props = defineProps<{
  messages: ChatMessage[]
  customerName: string
  loading: boolean
}>()

const listRef = ref<HTMLDivElement>()

function scrollToBottom() {
  nextTick(() => {
    if (listRef.value) {
      listRef.value.scrollTop = listRef.value.scrollHeight
    }
  })
}

watch(() => props.messages.length, scrollToBottom)
watch(() => props.loading, (val) => { if (val) scrollToBottom() })
</script>

<template>
  <div class="chat-window">
    <div class="chat-header" v-if="customerName">
      <span>💬 {{ customerName }}</span>
      <span v-if="loading" class="typing-indicator">对方正在输入...</span>
    </div>
    <div class="chat-header chat-header-empty" v-else>
      <span>请选择一个客户开始对话</span>
    </div>
    <div class="chat-messages" ref="listRef">
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="message-row"
        :class="msg.sender"
      >
        <div class="message-bubble" :class="msg.sender">
          <div class="message-text">{{ msg.content }}</div>
          <div class="message-time">{{ msg.timestamp }}</div>
        </div>
      </div>
      <div v-if="loading" class="message-row customer">
        <div class="message-bubble customer loading-bubble">
          <span class="dot-pulse"></span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-window {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: #fff;
}

.chat-header {
  padding: 14px 20px;
  border-bottom: 1px solid #e5e7eb;
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.chat-header-empty {
  color: #9ca3af;
  font-weight: 400;
}

.typing-indicator {
  font-size: 12px;
  color: #6366f1;
  font-weight: 400;
}

.chat-messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 20px;
  background: #fafbfc;
}

.message-row {
  display: flex;
  margin-bottom: 14px;
}

.message-row.customer {
  justify-content: flex-start;
}

.message-row.agent {
  justify-content: flex-end;
}

.message-bubble {
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
}

.message-bubble.customer {
  background: #f3f4f6;
  color: #1f2937;
  border-bottom-left-radius: 4px;
}

.message-bubble.agent {
  background: #6366f1;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.message-time {
  font-size: 10px;
  margin-top: 4px;
  opacity: 0.6;
}

.message-bubble.agent .message-time {
  text-align: right;
}

.loading-bubble {
  padding: 14px 18px;
}

.dot-pulse {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #9ca3af;
  animation: pulse 1.2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}
</style>
