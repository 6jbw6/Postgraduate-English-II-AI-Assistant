<template>
  <div class="message" :class="role">
    <div class="message-avatar">
      <div class="avatar" :class="role">
        {{ role === 'user' ? '👤' : '🎓' }}
      </div>
    </div>

    <div class="message-content" :class="{ thinking: isStreaming && content === '思考中...' }">
      <template v-if="role === 'user'">
        <!-- 图片网格 -->
        <div v-if="imgs && imgs.length > 0" class="msg-images-grid">
          <div
            v-for="(img, idx) in imgs"
            :key="idx"
            class="msg-image-wrapper"
            @click="previewIdx = idx; showPreview = true"
          >
            <img :src="img" class="msg-image" alt="uploaded image" />
          </div>
        </div>
        <!-- 全屏预览 -->
        <Teleport to="body">
          <div v-if="showPreview" class="preview-overlay" @click="showPreview = false">
            <img :src="imgs[previewIdx]" class="preview-image" @click.stop />
            <button class="preview-close" @click="showPreview = false">&times;</button>
          </div>
        </Teleport>
        <span v-if="content" class="msg-text">{{ content }}</span>
      </template>

      <!-- AI 消息：Markdown 渲染 -->
      <div v-if="role === 'ai' && content" class="markdown-body" v-html="renderMarkdown(content)"></div>

      <!-- 加载动画 -->
      <span v-if="isStreaming && !content && role === 'ai'" class="typing-indicator">
        <span></span><span></span><span></span>
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { renderMarkdown } from '../utils/markdown.js'

const props = defineProps({
  role: { type: String, required: true },
  content: { type: String, default: '' },
  images: { type: Array, default: null },
  isStreaming: { type: Boolean, default: false },
})

const imgs = computed(() => props.images || [])

// 图片预览状态只在当前消息气泡内部维护，避免影响其他消息。
const showPreview = ref(false)
const previewIdx = ref(0)
</script>

<style scoped>
.message {
  display: flex;
  gap: 12px;
  max-width: 85%;
  animation: fadeIn 0.3s ease;
}
.message.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}
.message.ai {
  align-self: flex-start;
}

.message-avatar {
  flex-shrink: 0;
}
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}
.avatar.user {
  background: var(--bg);
  color: var(--text);
}
.avatar.ai {
  background: linear-gradient(135deg, var(--primary), var(--primary-light));
  color: #fff;
}

.message-content {
  padding: 12px 16px;
  border-radius: var(--radius);
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
  min-width: 0;
  box-shadow: var(--shadow);
}
.message.user .message-content {
  background: var(--user-bubble);
  color: var(--user-text);
  border-top-right-radius: 2px;
}
.message.ai .message-content {
  background: var(--ai-bubble);
  color: var(--ai-text);
  border-top-left-radius: 2px;
}

.msg-images-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.msg-image-wrapper {
  cursor: pointer;
}
.msg-image {
  width: 120px;
  height: 120px;
  object-fit: cover;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
}

.preview-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}
.preview-image {
  max-width: 90vw;
  max-height: 90vh;
  border-radius: 8px;
}
.preview-close {
  position: absolute;
  top: 20px;
  right: 30px;
  font-size: 36px;
  color: #fff;
  background: none;
  border: none;
  cursor: pointer;
}

.msg-text {
  white-space: pre-wrap;
}

/* 思考动画 */
.message-content.thinking {
  font-style: italic;
  color: var(--text-muted);
}

.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 4px 0;
}
.typing-indicator span {
  width: 6px;
  height: 6px;
  background: var(--text-muted);
  border-radius: 50%;
  animation: typing 1.4s infinite;
}
.typing-indicator span:nth-child(2) { animation-delay: .2s; }
.typing-indicator span:nth-child(3) { animation-delay: .4s; }

@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); opacity: .4; }
  30% { transform: translateY(-4px); opacity: 1; }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Markdown 基本样式适配 */
:deep(.markdown-body h1) { font-size: 1.3em; margin: 12px 0 8px; }
:deep(.markdown-body h2) { font-size: 1.15em; margin: 10px 0 6px; }
:deep(.markdown-body h3) { font-size: 1.05em; margin: 8px 0 4px; }
:deep(.markdown-body p) { margin: 6px 0; }
:deep(.markdown-body pre) {
  background-color: #282c34;
  color: #abb2bf;
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 13px;
}
:deep(.markdown-body code) {
  background-color: var(--bg);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 0.9em;
}
:deep(.markdown-body pre code) {
  background-color: transparent;
  padding: 0;
}
:deep(.markdown-body table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
}
:deep(.markdown-body th),
:deep(.markdown-body td) {
  border: 1px solid var(--border);
  padding: 6px 12px;
  text-align: left;
}
:deep(.markdown-body th) {
  background: var(--bg);
}
:deep(.markdown-body blockquote) {
  border-left: 3px solid var(--primary);
  margin: 8px 0;
  padding: 4px 12px;
  color: var(--text-secondary);
}
:deep(.markdown-body ul),
:deep(.markdown-body ol) {
  padding-left: 20px;
  margin: 6px 0;
}
</style>
