<!--
  ChatArea.vue - 聊天主区域

  每个 ChatArea 实例对应一个题型会话。
  Props:
  - currentType: 当前题型 id（如 cloze, reading_a）
  - sessionId: 会话标识（空字符串 = 新会话）

  Emits:
  - update-session-id: 首次回复后告知父组件当前题型的 session_id
  - thinking-changed: AI 思考状态变化
  - change-type: 切换题型
-->
<template>
  <div class="chat-main">
    <!-- 顶部标题栏 -->
    <header class="chat-header">
      <div class="header-left">
        <div class="type-icon">{{ currentTypeObj.icon || '💬' }}</div>
        <div>
          <div class="current-type">{{ currentTypeObj.name || '自由对话' }}</div>
          <div class="current-type-desc">{{ currentTypeObj.description || '不限定题型，随意提问' }}</div>
        </div>
      </div>
      <div v-if="isStreaming" class="status-badge">AI 思考中...</div>
    </header>

    <!-- 消息列表（无限滚动） -->
    <div class="chat-messages" ref="messagesContainer">
      <!-- 顶部滚动哨兵：触发加载更早历史 -->
      <div class="scroll-sentinel">
        <span v-if="isLoadingHistory">加载历史中...</span>
      </div>

      <!-- 欢迎引导 -->
      <div v-if="messages.length === 0 && !isLoadingHistory" class="welcome-box">
        <div class="welcome-icon">🎓</div>
        <h2>你好！我是考研英语二 AI 学习助手</h2>
        <p class="welcome-desc">
          我可以帮你训练和讲解英二的全部题型。<br />
          发送消息或者直接粘贴/上传图片开始吧！
        </p>
      </div>

      <MessageBubble
        v-for="(msg, idx) in messages"
        :key="idx"
        :role="msg.role"
        :content="msg.content"
        :images="msg.images || null"
        :is-streaming="idx === messages.length - 1 && isStreaming && msg.role === 'ai'"
      />
    </div>

    <!-- 输入区域 -->
    <div class="chat-input-area">
      <!-- 图片预览 -->
      <div v-if="uploadedImages.length > 0" class="image-preview-grid">
        <div v-for="(img, idx) in uploadedImages" :key="idx" class="image-preview-item">
          <img :src="img" alt="preview" />
          <button class="btn-remove-img" @click="removeImage(idx)">&times;</button>
        </div>
      </div>

      <!-- 输入行 -->
      <div class="input-row">
        <textarea
          v-model="inputText"
          class="chat-textarea"
          :placeholder="uploadedImages.length > 0 ? '补充说明（可选）...' : '输入你的问题，支持粘贴或拖拽图片...'"
          :disabled="isStreaming"
          rows="1"
          @keydown.enter.exact.prevent="sendMessage"
          @paste="handlePaste"
          ref="textareaRef"
        ></textarea>
        <input
          ref="fileInput"
          type="file"
          accept="image/*"
          multiple
          style="display:none"
          @change="handleFileChange"
        />
        <div class="action-buttons">
          <button class="btn-icon" @click="triggerUpload" :disabled="isStreaming" title="上传图片">
            🖼️
          </button>
          <button
            class="btn-send"
            @click="sendMessage"
            :disabled="(!inputText.trim() && uploadedImages.length === 0) || isStreaming || isProcessingPaste"
            title="发送"
          >
            ➤
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch, onMounted } from 'vue'
import MessageBubble from './MessageBubble.vue'

const props = defineProps({
  currentType: { type: String, default: '' },
  sessionId: { type: String, default: '' },
})

const emit = defineEmits([
  'update-session-id',  // 首次回复后告知父组件当前题型的 session_id
  'thinking-changed',   // AI 思考状态变化
  'change-type',        // 切换题型
])

// ---- 题型元数据 ----
const questionTypes = [
  { id: 'cloze',      icon: '📝', name: '完形填空',  description: 'Use of English - 20题/10分' },
  { id: 'reading_a',  icon: '📖', name: '阅读理解A', description: '传统阅读 - 4篇/40分' },
  { id: 'reading_b',  icon: '🔗', name: '阅读理解B', description: '多项对应/小标题 - 5题/10分' },
  { id: 'translation',icon: '🌐', name: '翻译',      description: '短文英译汉 - 约150词/15分' },
  { id: 'writing_a',  icon: '✉️', name: '小作文',    description: '应用文写作 - 100词/10分' },
  { id: 'writing_b',  icon: '🖼️', name: '大作文',    description: '图表作文 - 约150词/15分' },
]

const currentTypeObj = computed(() => {
  const typeId = props.currentType === 'free' ? '' : props.currentType
  return questionTypes.find(t => t.id === typeId) || {}
})

// ---- 状态 ----
const messages = ref([])
const isStreaming = ref(false)
const inputText = ref('')
const messagesContainer = ref(null)
const textareaRef = ref(null)
const scrollObserver = ref(null)
const uploadedImages = ref([])
const fileInput = ref(null)
const isProcessingPaste = ref(false)

let abortController = null
const MAX_IMAGES = 9

// ---- 无限滚动 ----
const isLoadingHistory = ref(false)
const hasMoreHistory = ref(true)
const historyOffset = ref(0)
const HISTORY_PAGE = 10

// 内部 session_id（首次响应后从 SSE 获取）
const internalSid = ref(props.sessionId)

// 当 sessionId prop 变化时，重置并重新加载
watch(() => props.sessionId, (newSid) => {
  internalSid.value = newSid
  messages.value = []
  historyOffset.value = 0
  hasMoreHistory.value = true
  isLoadingHistory.value = false
  loadLatestHistory()
})

onMounted(() => {
  loadLatestHistory()
})

// ---- 滚动哨兵 ----
function setupScrollObserver() {
  nextTick(() => {
    const el = messagesContainer.value
    if (!el) return
    if (scrollObserver.value) scrollObserver.value.disconnect()

    const sentinel = el.querySelector('.scroll-sentinel')
    if (!sentinel) return

    scrollObserver.value = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMoreHistory.value && !isLoadingHistory.value) {
          loadOlderHistory()
        }
      },
      { root: el, rootMargin: '20px 0px 0px 0px', threshold: 0 },
    )
    scrollObserver.value.observe(sentinel)
  })
}

watch(() => messages.value.length, () => setupScrollObserver())

// ---- 历史加载 ----
async function loadLatestHistory() {
  const sid = internalSid.value
  if (!sid || isLoadingHistory.value) return
  isLoadingHistory.value = true
  try {
    const res = await fetch(`/api/session/${sid}?offset=0&limit=${HISTORY_PAGE}`)
    if (res.ok) {
      const data = await res.json()
      const msgs = (data.messages || []).map((m) => ({
        role: m.role === 'assistant' ? 'ai' : 'user',
        content: m.content,
      }))
      messages.value = msgs
      historyOffset.value = msgs.length
      hasMoreHistory.value = data.has_more
    }
  } catch (err) { console.error(err) }
  finally {
    isLoadingHistory.value = false
    nextTick(() => scrollToBottom())
  }
}

async function loadOlderHistory() {
  const sid = internalSid.value
  if (!sid || isLoadingHistory.value || !hasMoreHistory.value) return
  isLoadingHistory.value = true
  try {
    const res = await fetch(`/api/session/${sid}?offset=${historyOffset.value}&limit=${HISTORY_PAGE}`)
    if (res.ok) {
      const data = await res.json()
      const older = (data.messages || []).map((m) => ({
        role: m.role === 'assistant' ? 'ai' : 'user',
        content: m.content,
      }))
      if (older.length > 0) {
        const container = messagesContainer.value
        const prevHeight = container?.scrollHeight || 0
        messages.value = [...older, ...messages.value]
        nextTick(() => {
          if (container) container.scrollTop = container.scrollHeight - prevHeight
        })
      }
      historyOffset.value += older.length
      hasMoreHistory.value = data.has_more
    }
  } catch (err) { console.error(err) }
  finally {
    isLoadingHistory.value = false
  }
}

// ---- 图片上传 ----
function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

function addImages(dataUrls) {
  const remaining = MAX_IMAGES - uploadedImages.value.length
  const toAdd = dataUrls.slice(0, remaining)
  uploadedImages.value.push(...toAdd)
}

async function handlePaste(e) {
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      e.preventDefault()
      if (uploadedImages.value.length >= MAX_IMAGES) return
      const file = item.getAsFile()
      if (file) {
        isProcessingPaste.value = true
        try {
          const dataUrl = await fileToBase64(file)
          addImages([dataUrl])
        } finally {
          isProcessingPaste.value = false
        }
      }
      return
    }
  }
}

function triggerUpload() {
  fileInput.value?.click()
}

async function handleFileChange(e) {
  const files = Array.from(e.target.files || [])
  if (files.length === 0) return
  isProcessingPaste.value = true
  try {
    const dataUrls = await Promise.all(files.map(fileToBase64))
    addImages(dataUrls)
  } finally {
    isProcessingPaste.value = false
  }
  e.target.value = ''
}

function removeImage(idx) {
  uploadedImages.value.splice(idx, 1)
}

// ---- 滚动到底部 ----
function scrollToBottom() {
  nextTick(() => {
    const el = messagesContainer.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

// ---- 发送消息 ----
async function sendMessage() {
  const message = inputText.value.trim()
  const hasImages = uploadedImages.value.length > 0
  if (!message && !hasImages) return
  if (isStreaming.value) return
  if (isProcessingPaste.value) return

  if (abortController) {
    abortController.abort()
    abortController = null
  }

  isStreaming.value = true

  const imagesB64 = hasImages
    ? uploadedImages.value.map(url => url.split(',')[1] || url)
    : null

  // 添加用户消息
  messages.value.push({
    role: 'user',
    content: message || '',
    images: [...uploadedImages.value],
  })
  inputText.value = ''
  uploadedImages.value = []

  // 添加 AI 占位
  messages.value.push({ role: 'ai', content: '' })
  scrollToBottom()

  const controller = new AbortController()
  abortController = controller

  try {
    const typeParam = props.currentType === 'free' ? '' : props.currentType
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: internalSid.value,
        message,
        question_type: typeParam || null,
        images: imagesB64,
      }),
      signal: controller.signal,
    })

    if (!response.ok) throw new Error(`HTTP ${response.status}`)

    const reader = response.body?.getReader()
    if (!reader) throw new Error('Stream reader not available')

    const decoder = new TextDecoder()
    let buffer = ''
    const aiIdx = messages.value.length - 1

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const data = JSON.parse(line.slice(6))

          // 首次响应：获取 session_id
          if (data.session_id && !internalSid.value) {
            internalSid.value = data.session_id
            emit('update-session-id', { type: props.currentType, sid: data.session_id })
          }

          // 思考状态
          if (data.thinking === true) {
            messages.value[aiIdx].content = data.content
            emit('thinking-changed', { type: props.currentType, thinking: true })
            scrollToBottom()
            continue
          }
          if (data.thinking === false) {
            messages.value[aiIdx].content = ''
            emit('thinking-changed', { type: props.currentType, thinking: false })
            continue
          }

          if (data.content) {
            messages.value[aiIdx].content += data.content
            scrollToBottom()
          }
        } catch (e) { /* skip malformed SSE */ }
      }
    }
  } catch (err) {
    if (err.name === 'AbortError') return
    const lastMsg = messages.value[messages.value.length - 1]
    if (lastMsg && lastMsg.role === 'ai') {
      lastMsg.content = `请求失败：${err.message}`
    }
  } finally {
    abortController = null
    isStreaming.value = false
  }
}
</script>

<style scoped>
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: 100%;
}

.chat-header {
  padding: 14px 24px;
  background: var(--chat-bg);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: var(--shadow);
  z-index: 2;
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.type-icon {
  width: 36px;
  height: 36px;
  background: var(--bg);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}
.current-type { font-size: 15px; font-weight: 600; color: var(--text); }
.current-type-desc { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
.status-badge {
  font-size: 12px;
  color: var(--warning);
  background: #fffbeb;
  padding: 4px 12px;
  border-radius: 12px;
  animation: pulse 1.5s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.scroll-sentinel {
  display: flex;
  justify-content: center;
  padding: 4px 0;
  font-size: 12px;
  color: var(--text-muted);
}

.welcome-box {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}
.welcome-icon {
  font-size: 56px;
  line-height: 1;
  margin-bottom: 16px;
}
.welcome-box h2 {
  font-size: 18px;
  color: var(--text);
  margin-bottom: 8px;
}
.welcome-desc {
  color: var(--text-secondary);
  line-height: 1.8;
  font-size: 14px;
}

.chat-input-area {
  padding: 16px 24px;
  background: var(--chat-bg);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.image-preview-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.image-preview-item {
  position: relative;
  width: 64px;
  height: 64px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border);
}
.image-preview-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.btn-remove-img {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(0,0,0,0.5);
  color: #fff;
  border: none;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  line-height: 1;
}

.input-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.chat-textarea {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-family: inherit;
  line-height: 1.5;
  resize: none;
  outline: none;
  background: var(--bg);
  color: var(--text);
  transition: border-color 0.2s;
  max-height: 160px;
}
.chat-textarea:focus {
  border-color: var(--primary);
}
.chat-textarea:disabled {
  opacity: 0.6;
}

.action-buttons {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.btn-icon,
.btn-send {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg);
  cursor: pointer;
  font-size: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.btn-icon:hover:not(:disabled) {
  background: var(--primary-bg);
  border-color: var(--primary);
}
.btn-send {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
}
.btn-send:hover:not(:disabled) {
  background: var(--primary-light);
}
.btn-send:disabled,
.btn-icon:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
