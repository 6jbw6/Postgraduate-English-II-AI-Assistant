<template>
  <aside class="sidebar">
    <div class="sidebar-header" @click="$emit('select-type', null)">
      <div class="logo-icon">🎓</div>
      <div class="logo-text">
        <h2>考研英语二 AI 助手</h2>
        <div class="subtitle">智能辅导系统 · 企业版</div>
      </div>
    </div>

    <nav class="sidebar-nav">
      <div class="nav-section-title">题型选择</div>

      <button
        v-for="item in questionTypes"
        :key="item.id"
        class="nav-item"
        :class="{ active: currentType === item.id }"
        @click="$emit('select-type', item.id)"
      >
        <span class="nav-item-icon">{{ item.icon }}</span>
        <div class="nav-item-content">
          <span class="nav-item-name">{{ item.name }}</span>
          <span class="nav-item-desc">{{ item.description }}</span>
        </div>
        <span class="nav-item-score">{{ item.score }}</span>
      </button>
    </nav>

    <div class="sidebar-footer">
      <button
        class="btn-clear"
        :disabled="currentType === null"
        @click="$emit('clear-chat')"
      >
        清空当前对话
      </button>

      <div class="account-menu">
        <button
          class="account-trigger"
          type="button"
          :aria-expanded="accountOpen"
          aria-label="打开账号菜单"
          @click="accountOpen = !accountOpen"
        >
          <span class="avatar-wrap">
            <span class="user-avatar">
              <img v-if="avatarUrl" :src="avatarUrl" alt="" />
              <span v-else>{{ userInitial }}</span>
            </span>
            <span class="status-dot" aria-hidden="true"></span>
          </span>
          <span class="account-summary">
            <span class="account-name" :title="displayName">{{ displayName }}</span>
            <span class="account-email" :title="displayEmail">{{ displayEmail }}</span>
          </span>
          <span class="chevron" :class="{ open: accountOpen }">⌃</span>
        </button>

        <section v-if="accountOpen" class="account-popover" aria-label="个人资料">
          <div v-if="!editingProfile">
            <div class="profile-header">
              <div class="profile-avatar">
                <img v-if="avatarUrl" :src="avatarUrl" alt="" />
                <span v-else>{{ userInitial }}</span>
              </div>
              <div class="profile-title">
                <div class="profile-name" :title="displayName">{{ displayName }}</div>
                <div class="profile-status">已登录</div>
              </div>
            </div>

            <div class="profile-list">
              <div class="profile-row">
                <span class="profile-key">邮箱</span>
                <span class="profile-value" :title="displayEmail">{{ displayEmail }}</span>
              </div>
              <div class="profile-row">
                <span class="profile-key">备考阶段</span>
                <span class="profile-value" :title="profileStage">{{ profileStage }}</span>
              </div>
              <div class="profile-row">
                <span class="profile-key">目标分数</span>
                <span class="profile-value">{{ profileScore }}</span>
              </div>
              <div class="profile-row profile-row-block">
                <span class="profile-key">学习目标</span>
                <span class="profile-value profile-goal" :title="profileGoal">{{ profileGoal }}</span>
              </div>
            </div>

            <div class="profile-actions">
              <button class="menu-secondary" type="button" @click="startEditProfile">
                编辑资料
              </button>
              <button class="menu-logout" type="button" @click="$emit('logout')">
                退出登录
              </button>
            </div>
          </div>

          <form v-else class="profile-form" @submit.prevent="submitProfile">
            <div class="avatar-editor">
              <div class="profile-avatar avatar-preview">
                <img v-if="draft.avatar_url" :src="draft.avatar_url" alt="" />
                <span v-else>{{ draftInitial }}</span>
              </div>
              <div class="avatar-controls">
                <button class="menu-secondary" type="button" @click="fileInput?.click()">
                  更换头像
                </button>
                <button class="text-button" type="button" @click="draft.avatar_url = ''">
                  移除
                </button>
                <input
                  ref="fileInput"
                  type="file"
                  accept="image/*"
                  hidden
                  @change="handleAvatarChange"
                />
              </div>
            </div>

            <label class="form-field">
              <span>昵称</span>
              <input v-model.trim="draft.display_name" maxlength="64" placeholder="例如：备考中的小王" />
            </label>
            <label class="form-field">
              <span>备考阶段</span>
              <select v-model="draft.exam_stage">
                <option value="">未设置</option>
                <option value="基础阶段">基础阶段</option>
                <option value="强化阶段">强化阶段</option>
                <option value="冲刺阶段">冲刺阶段</option>
                <option value="二战备考">二战备考</option>
              </select>
            </label>
            <label class="form-field">
              <span>目标分数</span>
              <input v-model.trim="draft.target_score" maxlength="16" placeholder="例如：75+" />
            </label>
            <label class="form-field">
              <span>学习目标</span>
              <textarea v-model.trim="draft.study_goal" maxlength="256" rows="3" placeholder="例如：阅读稳定 32 分，小作文减少语法错误"></textarea>
            </label>

            <div v-if="profileError" class="profile-error">{{ profileError }}</div>

            <div class="form-actions">
              <button class="menu-secondary" type="button" :disabled="savingProfile" @click="cancelEditProfile">
                取消
              </button>
              <button class="menu-primary" type="submit" :disabled="savingProfile">
                {{ savingProfile ? '保存中...' : '保存' }}
              </button>
            </div>
          </form>
        </section>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  currentType: { type: String, default: null },
  user: { type: Object, default: null },
  saveProfile: { type: Function, default: null },
})

defineEmits(['select-type', 'clear-chat', 'logout'])

const questionTypes = [
  { id: 'free',       icon: '💬', name: '自由对话',  description: '不限定题型，随意提问' },
  { id: 'cloze',      icon: '📝', name: '完形填空',  description: 'Use of English',         score: '10分' },
  { id: 'reading_a',  icon: '📖', name: '阅读理解A', description: '传统阅读 - 4篇',         score: '40分' },
  { id: 'reading_b',  icon: '🔗', name: '阅读理解B', description: '多项对应 / 小标题',      score: '10分' },
  { id: 'translation',icon: '🌐', name: '翻译',      description: '短文英译汉',             score: '15分' },
  { id: 'writing_a',  icon: '✉️', name: '小作文',    description: '应用文写作',             score: '10分' },
  { id: 'writing_b',  icon: '🖼️', name: '大作文',    description: '图表作文',               score: '15分' },
]

const accountOpen = ref(false)
const editingProfile = ref(false)
const savingProfile = ref(false)
const profileError = ref('')
const fileInput = ref(null)
// 前端先拦截过大的头像，后端仍会做同样限制，避免绕过客户端校验。
const AVATAR_MAX_BYTES = 2 * 1024 * 1024
const AVATAR_MAX_LABEL = '2MB'
// 编辑资料时使用草稿对象，用户点取消不会污染当前登录用户状态。
const draft = ref({
  display_name: '',
  avatar_url: '',
  exam_stage: '',
  target_score: '',
  study_goal: '',
})

const displayName = computed(() => props.user?.display_name || props.user?.username || '未命名用户')
const displayEmail = computed(() => props.user?.email || '邮箱未同步')
const avatarUrl = computed(() => props.user?.avatar_url || '')
const profileStage = computed(() => props.user?.exam_stage || '未设置')
const profileScore = computed(() => props.user?.target_score || '未设置')
const profileGoal = computed(() => props.user?.study_goal || '未设置')
const draftInitial = computed(() => {
  const name = draft.value.display_name || props.user?.username || props.user?.email || '?'
  return name.trim().slice(0, 1).toUpperCase()
})

const userInitial = computed(() => {
  const name = props.user?.display_name || props.user?.username || props.user?.email || '?'
  return name.trim().slice(0, 1).toUpperCase()
})

function startEditProfile() {
  profileError.value = ''
  // 每次进入编辑态都从最新用户信息复制一份，避免旧草稿残留。
  draft.value = {
    display_name: props.user?.display_name || props.user?.username || '',
    avatar_url: props.user?.avatar_url || '',
    exam_stage: props.user?.exam_stage || '',
    target_score: props.user?.target_score || '',
    study_goal: props.user?.study_goal || '',
  }
  editingProfile.value = true
}

function cancelEditProfile() {
  editingProfile.value = false
  profileError.value = ''
}

function handleAvatarChange(event) {
  const file = event.target.files?.[0]
  // 清空 input，保证连续选择同一个文件也能再次触发 change。
  event.target.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) {
    profileError.value = '请选择图片文件'
    return
  }
  if (file.size > AVATAR_MAX_BYTES) {
    profileError.value = `头像图片不能超过 ${AVATAR_MAX_LABEL}`
    return
  }

  const reader = new FileReader()
  reader.onload = () => {
    // 头像以 Data URL 保存，便于前端即时预览，也方便后端直接存储文本。
    draft.value.avatar_url = String(reader.result || '')
    profileError.value = ''
  }
  reader.onerror = () => {
    profileError.value = '头像读取失败'
  }
  reader.readAsDataURL(file)
}

async function submitProfile() {
  savingProfile.value = true
  profileError.value = ''
  try {
    if (!props.saveProfile) throw new Error('保存接口未配置')
    // 保存逻辑由父组件注入，Sidebar 只负责收集和展示个人资料。
    await props.saveProfile({
      display_name: draft.value.display_name,
      avatar_url: draft.value.avatar_url,
      exam_stage: draft.value.exam_stage,
      target_score: draft.value.target_score,
      study_goal: draft.value.study_goal,
    })
    editingProfile.value = false
  } catch (error) {
    profileError.value = error.message || '保存失败'
  } finally {
    savingProfile.value = false
  }
}
</script>

<style scoped>
.sidebar {
  width: 260px;
  min-width: 260px;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border);
  box-shadow: var(--shadow);
  z-index: 10;
}

.sidebar-header {
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.15s;
}
.sidebar-header:hover {
  background: var(--bg);
}

.logo-icon {
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, var(--primary), var(--primary-light));
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: #fff;
}

.logo-text h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}
.subtitle {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

.sidebar-nav {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
}

.nav-section-title {
  padding: 8px 20px 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.nav-item {
  width: calc(100% - 16px);
  margin: 2px 8px;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
  color: var(--text);
}
.nav-item:hover {
  background: var(--primary-bg);
}
.nav-item.active {
  background: var(--primary-bg);
  color: var(--primary);
}

.nav-item-icon {
  font-size: 18px;
  width: 28px;
  text-align: center;
  flex-shrink: 0;
}

.nav-item-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.nav-item-name {
  font-size: 13px;
  font-weight: 600;
}
.nav-item-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}
.nav-item.active .nav-item-desc {
  color: var(--primary);
}

.nav-item-score {
  font-size: 11px;
  color: var(--success);
  background: #ecfdf5;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
  flex-shrink: 0;
}

.sidebar-footer {
  position: relative;
  padding: 16px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.account-menu {
  position: relative;
}

.account-trigger {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #fff;
  color: var(--text);
  cursor: pointer;
  text-align: left;
  min-width: 0;
  transition: background 0.15s, border-color 0.15s, box-shadow 0.15s;
}

.account-trigger:hover {
  background: var(--bg);
  border-color: #cbd5e1;
}

.account-trigger:focus-visible {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-bg);
}

.avatar-wrap {
  position: relative;
  flex-shrink: 0;
}

.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  overflow: hidden;
  background: linear-gradient(135deg, var(--primary), var(--success));
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 700;
}

.user-avatar img,
.profile-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.status-dot {
  position: absolute;
  right: -1px;
  bottom: -1px;
  width: 11px;
  height: 11px;
  border: 2px solid #fff;
  border-radius: 50%;
  background: var(--success);
}

.account-summary {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.account-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.account-email {
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chevron {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 14px;
  transform: rotate(0deg);
  transition: transform 0.15s, background 0.15s, color 0.15s;
}

.chevron.open {
  transform: rotate(180deg);
  background: var(--primary-bg);
  color: var(--primary);
}

.account-popover {
  position: absolute;
  left: 0;
  right: 0;
  bottom: calc(100% + 10px);
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #fff;
  box-shadow: var(--shadow-lg);
  z-index: 20;
}

.profile-header {
  display: flex;
  gap: 10px;
  align-items: center;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

.profile-avatar {
  width: 42px;
  height: 42px;
  flex-shrink: 0;
  border-radius: 50%;
  overflow: hidden;
  background: linear-gradient(135deg, var(--primary), var(--success));
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 800;
}

.profile-title {
  min-width: 0;
  flex: 1;
}

.profile-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.profile-status {
  width: fit-content;
  margin-top: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #ecfdf5;
  color: var(--success);
  font-size: 11px;
  font-weight: 700;
}

.profile-list {
  padding: 10px 0;
}

.profile-row {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  padding: 6px 0;
}

.profile-row-block {
  align-items: start;
}

.profile-key {
  font-size: 11px;
  color: var(--text-muted);
}

.profile-value {
  min-width: 0;
  color: var(--text);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.profile-goal {
  white-space: normal;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.profile-actions,
.form-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.menu-secondary,
.menu-primary {
  width: 100%;
  padding: 9px 10px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}

.menu-secondary {
  border: 1px solid var(--border);
  background: #fff;
  color: var(--text-secondary);
}

.menu-secondary:hover:not(:disabled) {
  background: var(--bg);
  color: var(--text);
}

.menu-primary {
  border: 1px solid var(--primary);
  background: var(--primary);
  color: #fff;
}

.menu-primary:hover:not(:disabled) {
  background: var(--primary-light);
}

.menu-secondary:disabled,
.menu-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.menu-logout {
  width: 100%;
  padding: 9px 10px;
  border: 1px solid #fecaca;
  border-radius: var(--radius-sm);
  background: #fef2f2;
  color: var(--danger);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.menu-logout:hover {
  background: #fee2e2;
  border-color: #fca5a5;
}

.profile-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.avatar-editor {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}

.avatar-preview {
  width: 48px;
  height: 48px;
}

.avatar-controls {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}

.text-button {
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  padding: 6px 0;
}

.text-button:hover {
  color: var(--danger);
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.form-field span {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
}

.form-field input,
.form-field select,
.form-field textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text);
  font: inherit;
  font-size: 12px;
  outline: none;
  padding: 8px 9px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.form-field textarea {
  resize: none;
  line-height: 1.5;
}

.form-field input:focus,
.form-field select:focus,
.form-field textarea:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-bg);
}

.profile-error {
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: #fef2f2;
  color: var(--danger);
  font-size: 12px;
}

.btn-clear {
  width: 100%;
  padding: 10px;
  border: 1px solid var(--danger);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--danger);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-clear:hover:not(:disabled) {
  background: #fef2f2;
}
.btn-clear:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  border-color: var(--border);
  color: var(--text-muted);
}

</style>
