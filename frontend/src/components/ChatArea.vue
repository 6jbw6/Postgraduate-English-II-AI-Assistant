<!--
  ChatArea.vue - 聊天主区域（企业版）

  使用认证 API 封装发起请求，自动携带 JWT Token。
-->
<template>
  <div class="chat-main">
    <header class="chat-header">
      <div class="header-left">
        <div class="type-icon">{{ currentTypeObj.icon || '💬' }}</div>
        <div>
          <div class="current-type">{{ currentTypeObj.name || '自由对话' }}</div>
          <div class="current-type-desc">{{ currentTypeObj.description || '不限定题型，随意提问' }}</div>
        </div>
      </div>
    </header>

    <div class="chat-messages" ref="messagesContainer" @scroll="handleMessagesScroll">
      <div class="scroll-sentinel">
        <span v-if="isLoadingHistory">加载历史中...</span>
      </div>

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

    <div class="chat-input-area">
      <div v-if="uploadedImages.length > 0" class="image-preview-grid">
        <div v-for="(img, idx) in uploadedImages" :key="idx" class="image-preview-item">
          <img :src="img" alt="preview" />
          <button class="btn-remove-img" @click="removeImage(idx)">&times;</button>
        </div>
      </div>

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
import { ref, computed, nextTick, watch, onMounted, onActivated } from 'vue'
import MessageBubble from './MessageBubble.vue'
import { apiStream, apiGet } from '../utils/api.js'

const props = defineProps({
  currentType: { type: String, default: '' },
  sessionId: { type: String, default: '' },
})

const emit = defineEmits([
  'update-session-id',
  'thinking-changed',
  'change-type',
])

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

const messages = ref([])
const isStreaming = ref(false)
const inputText = ref('')
const messagesContainer = ref(null)
const textareaRef = ref(null)
const uploadedImages = ref([])
const fileInput = ref(null)
const isProcessingPaste = ref(false)

let abortController = null
const MAX_IMAGES = 9

const isLoadingHistory = ref(false)
const hasMoreHistory = ref(true)
const historyOffset = ref(0)
const HISTORY_PAGE = 10
const TOP_LOAD_THRESHOLD = 8
// 程序主动滚到底部时会触发 scroll 事件，这个开关用于避免误判为“用户滚到顶部”。
let suppressTopLoad = false

const internalSid = ref(props.sessionId)

watch(() => props.sessionId, (newSid) => {
  if (newSid === internalSid.value) return
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

onActivated(() => {
  // ChatArea 被 KeepAlive 缓存，重新进入题型时要恢复到最近消息位置。
  scrollToBottom()
})

async function loadLatestHistory() {
  // 首屏只取最近 10 条，后续由用户滚到顶部再分页加载更早消息。
  const sid = internalSid.value
  if (!sid || isLoadingHistory.value) return
  isLoadingHistory.value = true
  try {
    const data = await apiGet(`/api/session/${sid}?offset=0&limit=${HISTORY_PAGE}`)
    const msgs = (data.messages || []).map((m) => ({
      role: m.role === 'assistant' ? 'ai' : 'user',
      content: m.content,
    }))
    messages.value = msgs
    historyOffset.value = msgs.length
    hasMoreHistory.value = data.has_more
  } catch (err) { console.error(err) }
  finally {
    isLoadingHistory.value = false
    nextTick(() => scrollToBottom())
  }
}

function handleMessagesScroll() {
  if (suppressTopLoad) return
  const el = messagesContainer.value
  if (!el || el.scrollTop > TOP_LOAD_THRESHOLD) return
  // 只有真正接近顶部时才加载更早历史，避免初次渲染自动连续请求。
  loadOlderHistory()
}

async function loadOlderHistory() {
  const sid = internalSid.value
  if (!sid || isLoadingHistory.value || !hasMoreHistory.value) return
  isLoadingHistory.value = true
  try {
    const data = await apiGet(`/api/session/${sid}?offset=${historyOffset.value}&limit=${HISTORY_PAGE}`)
    const older = (data.messages || []).map((m) => ({
      role: m.role === 'assistant' ? 'ai' : 'user',
      content: m.content,
    }))
    if (older.length > 0) {
      const container = messagesContainer.value
      const prevHeight = container?.scrollHeight || 0
      messages.value = [...older, ...messages.value]
      nextTick(() => {
        // 前插历史后保持用户原来的阅读位置，不让视口跳到最顶部。
        if (container) container.scrollTop = container.scrollHeight - prevHeight
      })
    }
    historyOffset.value += older.length
    hasMoreHistory.value = data.has_more
  } catch (err) { console.error(err) }
  finally {
    isLoadingHistory.value = false
  }
}

function fileToBase64(file) {
  // 后端聊天接口接收 Base64 图片，前端预览也直接复用 Data URL。
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
  // 支持直接粘贴截图，体验上和选择文件保持一致。
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
        } finally { isProcessingPaste.value = false }
      }
      return
    }
  }
}

function triggerUpload() { fileInput.value?.click() }

async function handleFileChange(e) {
  const files = Array.from(e.target.files || [])
  if (files.length === 0) return
  isProcessingPaste.value = true
  try {
    const dataUrls = await Promise.all(files.map(fileToBase64))
    addImages(dataUrls)
  } finally { isProcessingPaste.value = false }
  e.target.value = ''
}

function removeImage(idx) { uploadedImages.value.splice(idx, 1) }

function scrollToBottom() {
  nextTick(() => {
    const el = messagesContainer.value
    if (!el) return
    suppressTopLoad = true
    el.scrollTop = el.scrollHeight
    requestAnimationFrame(() => {
      suppressTopLoad = false
    })
  })
}

async function sendMessage() {
  const message = inputText.value.trim()
  const hasImages = uploadedImages.value.length > 0
  if (!message && !hasImages) return
  if (isStreaming.value || isProcessingPaste.value) return

  if (abortController) {
    abortController.abort()
    abortController = null
  }

  isStreaming.value = true

  const imagesB64 = hasImages
    // 提交给后端时只需要 Base64 主体，页面展示仍保留完整 Data URL。
    ? uploadedImages.value.map(url => url.split(',')[1] || url)
    : null

  messages.value.push({
    role: 'user',
    content: message || '',
    images: [...uploadedImages.value],
  })
  inputText.value = ''
  uploadedImages.value = []

  messages.value.push({ role: 'ai', content: '' })
  scrollToBottom()

  const controller = new AbortController()
  abortController = controller

  try {
    const typeParam = props.currentType === 'free' ? '' : props.currentType
    const response = await apiStream('/api/chat', {
      session_id: internalSid.value,
      message,
      question_type: typeParam || null,
      images: imagesB64,
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
          // 后端以 SSE 形式逐段返回 JSON，这里按 data: 行解析并增量追加内容。
          const data = JSON.parse(line.slice(6))

          if (data.session_id && !internalSid.value) {
            internalSid.value = data.session_id
            emit('update-session-id', { type: props.currentType, sid: data.session_id })
          }

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
        } catch (e) { /* 跳过格式异常的 SSE 片段 */ }
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
.welcome-icon { font-size: 56px; line-height: 1; margin-bottom: 16px; }
.welcome-box h2 { font-size: 18px; color: var(--text); margin-bottom: 8px; }
.welcome-desc { color: var(--text-secondary); line-height: 1.8; font-size: 14px; }

.chat-input-area {
  padding: 16px 24px;
  background: var(--chat-bg);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.image-preview-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.image-preview-item { position: relative; width: 64px; height: 64px; border-radius: 8px; overflow: hidden; border: 1px solid var(--border); }
.image-preview-item img { width: 100%; height: 100%; object-fit: cover; }
.btn-remove-img {
  position: absolute; top: 2px; right: 2px; width: 18px; height: 18px;
  border-radius: 50%; background: rgba(0,0,0,0.5); color: #fff; border: none;
  font-size: 12px; cursor: pointer; display: flex; align-items: center;
  justify-content: center; padding: 0; line-height: 1;
}

.input-row { display: flex; gap: 10px; align-items: flex-end; }
.chat-textarea {
  flex: 1; padding: 10px 14px; border: 1px solid var(--border);
  border-radius: var(--radius-sm); font-size: 14px; font-family: inherit;
  line-height: 1.5; resize: none; outline: none; background: var(--bg);
  color: var(--text); transition: border-color 0.2s; max-height: 160px;
}
.chat-textarea:focus { border-color: var(--primary); }
.chat-textarea:disabled { opacity: 0.6; }

.action-buttons { display: flex; gap: 6px; flex-shrink: 0; }
.btn-icon, .btn-send {
  width: 40px; height: 40px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--bg); cursor: pointer; font-size: 18px; display: flex;
  align-items: center; justify-content: center; transition: all 0.15s;
}
.btn-icon:hover:not(:disabled) { background: var(--primary-bg); border-color: var(--primary); }
.btn-send { background: var(--primary); color: #fff; border-color: var(--primary); }
.btn-send:hover:not(:disabled) { background: var(--primary-light); }
.btn-send:disabled, .btn-icon:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
