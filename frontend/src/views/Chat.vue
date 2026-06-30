<!--
  聊天主页面 - 包含 Sidebar + ChatArea 的完整布局

  每个题型 = 一个独立对话（KeepAlive 缓存）。
  所有 API 调用携带 JWT Token。
-->
<template>
  <div class="app-layout">
    <Sidebar
      :current-type="currentType"
      :user="currentUser"
      :save-profile="handleProfileUpdate"
      @select-type="handleSelectType"
      @clear-chat="handleClearChat"
      @logout="handleLogout"
    />

    <main v-if="currentType === null" class="home-page">
      <div class="home-content">
        <div class="home-icon">🎓</div>
        <h1>考研英语二 AI 学习助手</h1>
        <p class="home-subtitle">企业版 · 多用户智能辅导系统</p>
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
        :session-id="typeSessions[currentType] || ''"
        @update-session-id="handleSessionIdUpdate"
        @thinking-changed="handleThinkingChanged"
        @change-type="handleSelectType"
      />
    </KeepAlive>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import Sidebar from '../components/Sidebar.vue'
import ChatArea from '../components/ChatArea.vue'
import { removeToken, apiDelete, apiGet, apiPatch, apiPost, getUser, setUser } from '../utils/api.js'

const router = useRouter()

const currentType = ref(sessionStorage.getItem('currentType') || null)
const currentUser = ref(getUser())
// typeVersion 用来强制重建某个题型的 ChatArea，例如清空对话后刷新本地状态。
const typeVersion = reactive({
  '': 0, 'free': 0,
  'cloze': 0, 'reading_a': 0, 'reading_b': 0,
  'translation': 0, 'writing_a': 0, 'writing_b': 0,
})
const typeSessions = reactive({})
const thinkingTypes = reactive(new Set())

// ---- 加载用户历史会话 ----
async function loadUserSessions() {
  try {
    const data = await apiGet('/api/sessions')
    const sessions = data.sessions || []
    // 按 question_type 分组，每个题型取最近更新的会话
    const seen = {}
    for (const s of sessions) {
      const qt = s.question_type || 'free'
      if (!seen[qt]) {
        seen[qt] = true
        typeSessions[qt] = s.session_id
      }
    }
  } catch {
    // 忽略错误，不影响正常使用
  }
}

async function loadCurrentUser() {
  try {
    const user = await apiGet('/api/auth/me')
    currentUser.value = user
    setUser(user)
  } catch {
    // apiGet 会处理 401；这里保留缓存展示，不打断聊天页渲染
  }
}

onMounted(() => {
  loadCurrentUser()
  loadUserSessions()
})

function handleSelectType(type) {
  currentType.value = type
  if (type !== null) {
    sessionStorage.setItem('currentType', type)
    // 如果没有历史会话，标记为空让服务端自动创建
    if (typeSessions[type] === undefined) {
      typeSessions[type] = ''
    }
  } else {
    sessionStorage.removeItem('currentType')
  }
}

function handleSessionIdUpdate({ type, sid }) {
  // 新会话首次收到后端 session_id 后，记录到对应题型，后续继续沿用同一会话。
  typeSessions[type] = sid
}

function handleThinkingChanged({ type, thinking }) {
  if (thinking) thinkingTypes.add(type)
  else thinkingTypes.delete(type)
}

async function handleProfileUpdate(profile) {
  const user = await saveProfileWithFallback(profile)
  currentUser.value = user
  setUser(user)
  return user
}

async function saveProfileWithFallback(profile) {
  // 兼容不同部署环境/代理对 HTTP 方法的限制，优先使用主端点，失败后尝试兼容端点。
  const attempts = [
    () => apiPost('/api/profile', profile),
    () => apiPost('/api/auth/me/profile', profile),
    () => apiPost('/api/auth/me', profile),
    () => apiPatch('/api/auth/me', profile),
  ]

  let lastError = null
  for (const attempt of attempts) {
    try {
      return await attempt()
    } catch (error) {
      lastError = error
      if (!String(error.message || '').includes('Method Not Allowed')) {
        throw error
      }
    }
  }
  throw lastError || new Error('保存失败')
}

async function handleClearChat() {
  const type = currentType.value
  if (type === null) return
  const sid = typeSessions[type]
  if (sid) {
    try { await apiDelete(`/api/session/${sid}`) } catch { /* 清空失败不阻断本地重置 */ }
    typeSessions[type] = ''
  }
  // 递增版本号会改变 key，从而让 KeepAlive 丢弃旧组件实例。
  typeVersion[type]++
}

function handleLogout() {
  removeToken()
  router.push('/login')
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
