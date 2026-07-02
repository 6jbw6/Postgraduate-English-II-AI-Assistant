<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-header">
        <div class="auth-icon">🎓</div>
        <h1>考研英语二 AI 助手</h1>
        <p class="auth-sub">创建新账号</p>
      </div>

      <form class="auth-form" @submit.prevent="handleRegister">
        <div class="form-group">
          <label>用户名</label>
          <input
            v-model="username"
            type="text"
            placeholder="请输入用户名"
            required
            minlength="2"
            :disabled="loading"
          />
        </div>
        <div class="form-group">
          <label>邮箱</label>
          <input
            v-model="email"
            type="email"
            placeholder="请输入邮箱"
            required
            :disabled="loading"
          />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input
            v-model="password"
            type="password"
            placeholder="至少 8 位密码"
            required
            minlength="8"
            :disabled="loading"
          />
        </div>

        <div v-if="error" class="form-error">{{ error }}</div>

        <button type="submit" class="btn-primary" :disabled="loading">
          {{ loading ? '注册中...' : '注册' }}
        </button>
      </form>

      <p class="auth-footer">
        已有账号？<router-link to="/login">立即登录</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiPost, setToken, setUser } from '../utils/api.js'

const router = useRouter()
const username = ref('')
const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)
const emailPattern = /^(?=.{5,128}$)(?!.*\.\.)[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$/
const commonEmailDomains = new Set([
  'qq.com',
  'foxmail.com',
  '163.com',
  '126.com',
  'yeah.net',
  'sina.com',
  'sina.cn',
  'sohu.com',
  '139.com',
  '189.cn',
  '21cn.com',
  'aliyun.com',
  'gmail.com',
  'outlook.com',
  'hotmail.com',
  'live.com',
  'icloud.com',
  'yahoo.com',
  'proton.me',
  'protonmail.com',
])

function isValidEmail(value) {
  const normalized = value.trim().toLowerCase()
  if (!emailPattern.test(normalized)) return false
  const domain = normalized.split('@').pop()
  return commonEmailDomains.has(domain)
}

async function handleRegister() {
  error.value = ''
  // 前端先给出即时提示；最终密码规则仍以后端校验为准。
  if (!isValidEmail(email.value)) {
    error.value = '邮箱格式不正确'
    return
  }
  if (password.value.length < 8) {
    error.value = '密码至少 8 位'
    return
  }
  loading.value = true
  try {
    // 注册成功后直接进入聊天页，减少一次手动登录流程。
    const data = await apiPost('/api/auth/register', {
      username: username.value,
      email: email.value,
      password: password.value,
    })
    setToken(data.access_token)
    setUser(data.user)
    router.push('/chat')
  } catch (e) {
    error.value = e.message || '注册失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
}

.auth-card {
  width: 400px;
  max-width: 90vw;
  background: var(--chat-bg);
  border-radius: var(--radius);
  padding: 40px;
  box-shadow: var(--shadow-lg);
  border: 1px solid var(--border);
}

.auth-header {
  text-align: center;
  margin-bottom: 32px;
}
.auth-icon {
  font-size: 48px;
  margin-bottom: 12px;
}
.auth-header h1 {
  font-size: 20px;
  color: var(--text);
  margin-bottom: 6px;
}
.auth-sub {
  font-size: 14px;
  color: var(--text-secondary);
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-group label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.form-group input {
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.2s;
  background: var(--bg);
  color: var(--text);
}
.form-group input:focus {
  border-color: var(--primary);
}

.form-error {
  font-size: 13px;
  color: var(--danger);
  background: #fef2f2;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
}

.btn-primary {
  width: 100%;
  padding: 12px;
  background: var(--primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}
.btn-primary:hover:not(:disabled) {
  background: var(--primary-light);
}
.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.auth-footer {
  text-align: center;
  margin-top: 24px;
  font-size: 14px;
  color: var(--text-secondary);
}
.auth-footer a {
  color: var(--primary);
  text-decoration: none;
  font-weight: 600;
}
.auth-footer a:hover {
  text-decoration: underline;
}
</style>
