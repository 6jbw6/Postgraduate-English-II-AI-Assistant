/**
 * Vue Router 路由配置
 *
 * 路由表：
 * - /login      登录页
 * - /register   注册页
 * - /chat       主页（需认证）
 * - /            重定向到 /chat
 */

import { createRouter, createWebHashHistory } from 'vue-router'
import { isAuthenticated } from '../utils/api.js'

// 懒加载视图，减少首屏 JS 体积。
const Login = () => import('../views/Login.vue')
const Register = () => import('../views/Register.vue')
const Chat = () => import('../views/Chat.vue')

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { guest: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: Register,
    meta: { guest: true },
  },
  {
    path: '/chat',
    name: 'Chat',
    component: Chat,
    meta: { requiresAuth: true },
  },
  {
    path: '/',
    redirect: '/chat',
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/chat',
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 全局导航守卫
router.beforeEach((to, from, next) => {
  const authenticated = isAuthenticated()

  if (to.meta.requiresAuth && !authenticated) {
    // 未登录访问受保护页面时，统一回到登录页。
    next('/login')
  } else if (to.meta.guest && authenticated) {
    // 已登录用户不需要再进入登录/注册页。
    next('/chat')
  } else {
    next()
  }
})

export default router
