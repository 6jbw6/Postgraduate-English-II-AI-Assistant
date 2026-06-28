<!--
  考研英语二 AI 学习助手 - 根组件

  每个题型 = 一个独立对话，切换题型不中断其他题型的 AI 思考。
  启动时不选中任何题型，显示首页欢迎界面。
  ChatArea 按 currentType 缓存，session_id = "type_" + type。
-->
<template>
  <div class="app-layout">
    <Sidebar
      :current-type="currentType"
      @select-type="handleSelectType"
      @clear-chat="handleClearChat"
    />

    <!-- 未选题型时：首页 -->
    <main v-if="currentType === null" class="home-page">
      <div class="home-content">
        <div class="home-icon">🎓</div>
        <h1>考研英语二 AI 学习助手</h1>
        <p class="home-subtitle">基于 DeepSeek 大模型的智能辅导系统</p>
        <p class="home-desc">
          左侧选择题型开始练习：完形填空、阅读理解A/B、翻译、小作文、大作文。<br />
          每个题型独立记忆，支持图片上传，AI 实时批改讲解。
        </p>
      </div>
    </main>

    <KeepAlive v-else :max="7">
      <ChatArea
        :key="currentType + '-' + (typeVersion[currentType] || 0)"
        :current-type="currentType"
        :session-id="'type_' + (currentType || 'free')"
        @update-session-id="handleSessionIdUpdate"
        @thinking-changed="handleThinkingChanged"
        @change-type="handleSelectType"
      />
    </KeepAlive>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import Sidebar from './components/Sidebar.vue'
import ChatArea from './components/ChatArea.vue'

/** null = 首页，非空 = 选中题型 */
const currentType = ref(null)
const typeVersion = reactive({
  '': 0,
  'free': 0,
  'cloze': 0, 'reading_a': 0, 'reading_b': 0,
  'translation': 0, 'writing_a': 0, 'writing_b': 0,
})
const thinkingTypes = reactive(new Set())

function handleSelectType(type) {
  currentType.value = type
  if (type !== null) {
    sessionStorage.setItem('currentType', type)
  } else {
    sessionStorage.removeItem('currentType')
  }
}

onMounted(() => {
  const saved = sessionStorage.getItem('currentType')
  if (saved) currentType.value = saved
})

function handleSessionIdUpdate({ type, sid }) {
  // 不再需要映射，session_id 由 "type_" + type 自动推导
}

function handleThinkingChanged({ type, thinking }) {
  if (thinking) {
    thinkingTypes.add(type)
  } else {
    thinkingTypes.delete(type)
  }
}

async function handleClearChat() {
  const type = currentType.value
  if (type === null) return
  const sid = 'type_' + (type || 'free')
  try { await fetch(`/api/session/${sid}`, { method: 'DELETE' }) } catch { /* ignore */ }
  typeVersion[type]++
}
</script>

<style scoped>
.app-layout {
  height: 100vh;
  display: flex;
  overflow: hidden;
  background-color: var(--bg);
}

.home-page {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--chat-bg);
}

.home-content {
  text-align: center;
  max-width: 480px;
  padding: 40px;
}

.home-icon {
  font-size: 64px;
  margin-bottom: 20px;
}

.home-content h1 {
  font-size: 24px;
  color: var(--text);
  margin-bottom: 12px;
  font-weight: 700;
}

.home-subtitle {
  font-size: 14px;
  color: var(--primary);
  margin-bottom: 16px;
  font-weight: 500;
}

.home-desc {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.8;
}
</style>
