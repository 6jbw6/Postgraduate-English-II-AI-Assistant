/**
 * 认证 HTTP 请求封装
 *
 * 自动附加 JWT Bearer Token，处理 401 跳转。
 */

const TOKEN_KEY = 'auth_token'
const USER_KEY = 'auth_user'

// ---- Token 管理 ----
export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function removeToken() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function getUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function isAuthenticated() {
  return !!getToken()
}

// ---- 通用请求 ----
export async function api(path, options = {}) {
  const token = getToken()
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(path, {
    ...options,
    headers,
  })

  // 401 自动跳转登录
  if (response.status === 401) {
    removeToken()
    window.location.hash = '#/login'
    throw new Error('登录已过期')
  }

  return response
}

function formatApiErrorDetail(detail) {
  // FastAPI 校验错误可能是字符串、对象或数组；统一转成可直接展示的文本。
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item?.msg) return item.msg
        return JSON.stringify(item)
      })
      .filter(Boolean)
      .join('；')
  }
  if (typeof detail === 'object') {
    if (detail.msg) return detail.msg
    if (detail.message) return detail.message
    return JSON.stringify(detail)
  }
  return String(detail)
}

async function getErrorMessage(res) {
  // 后端异常响应不一定是 JSON，因此这里要容错读取。
  const err = await res.json().catch(() => ({}))
  return formatApiErrorDetail(err.detail) || formatApiErrorDetail(err) || `HTTP ${res.status}`
}

// ---- 便捷方法 ----
export async function apiGet(path) {
  const res = await api(path)
  if (!res.ok) {
    throw new Error(await getErrorMessage(res))
  }
  return res.json()
}

export async function apiPost(path, body) {
  const res = await api(path, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new Error(await getErrorMessage(res))
  }
  return res.json()
}

export async function apiPatch(path, body) {
  const res = await api(path, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new Error(await getErrorMessage(res))
  }
  return res.json()
}

export async function apiDelete(path) {
  const res = await api(path, { method: 'DELETE' })
  if (!res.ok) {
    throw new Error(await getErrorMessage(res))
  }
  return res.json()
}

export async function apiStream(path, body) {
  // 流式接口只负责发起请求，响应体由调用方按 SSE/ReadableStream 逐段读取。
  return api(path, {
    method: 'POST',
    body: JSON.stringify(body),
    stream: true,
  })
}
