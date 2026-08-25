import { defineStore } from 'pinia'
import { v4Like } from '../utils/id'

const STORAGE_KEY = 'course_ai_auth_state'

// 模块级单例 Promise：并发的多个 401 只触发一次刷新，其余请求复用同一个 Promise 等结果
// 注意：不能放进 state——Promise 不可序列化，persist() 写 localStorage 时会把它写坏
let refreshPromise = null

export const useAuthStore = defineStore('auth', {
  state: () => ({
    userId: '',
    accessToken: '',
    expiresAt: '',
    refreshToken: '',
    refreshExpiresAt: '',
    role: '',
    currentCourseId: '',
    currentCourseName: '',
    currentCourseRole: '',
    threadId: v4Like(),
    lastQuestion: '',
    lastAnswer: '',
    messages: []
  }),
  getters: {
    isLoggedIn: (state) => Boolean(state.accessToken),
    hasCourse: (state) => Boolean(state.currentCourseId),
    isTeacher: (state) => state.role === 'teacher',
    isStudent: (state) => state.role === 'student'
  },
  actions: {
    restoreFromStorage() {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      try {
        const data = JSON.parse(raw)
        Object.assign(this, data)
        if (!this.role && this.accessToken) this.role = 'teacher'
        if (!this.threadId) this.threadId = v4Like()
        if (!Array.isArray(this.messages)) this.messages = []
      } catch {
        localStorage.removeItem(STORAGE_KEY)
      }
    },
    persist() {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        userId: this.userId,
        accessToken: this.accessToken,
        expiresAt: this.expiresAt,
        refreshToken: this.refreshToken,
        refreshExpiresAt: this.refreshExpiresAt,
        role: this.role,
        currentCourseId: this.currentCourseId,
        currentCourseName: this.currentCourseName,
        currentCourseRole: this.currentCourseRole,
        threadId: this.threadId,
        lastQuestion: this.lastQuestion,
        lastAnswer: this.lastAnswer,
        messages: this.messages
      }))
    },
    saveAuth(data) {
      this.userId = data.user_id
      this.accessToken = data.access_token
      this.expiresAt = data.expires_at
      this.refreshToken = data.refresh_token
      this.refreshExpiresAt = data.refresh_expires_at
      this.role = data.role || 'student'
      this.persist()
    },
    // 用 refresh token 静默换新 access token（双令牌续期）
    // 后端 /auth/refresh 返回 AccountSessionResponse，结构与登录响应一致，可直接复用 saveAuth
    async refresh() {
      // 已有刷新在进行：直接复用，防止并发刷新——第一次刷新后旧 refresh token 已被后端轮换作废，
      // 第二次刷新必然 401，会把本不该登出的用户踢出去
      if (refreshPromise) return refreshPromise
      refreshPromise = (async () => {
        // 用原生 fetch 而不是 axios 实例：避免刷新请求自己也走进 response 拦截器造成递归
        const resp = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: this.refreshToken })
        })
        // refresh token 也过期/被吊销：抛错，由调用方（拦截器）决定登出
        if (!resp.ok) throw new Error('refresh token 已失效')
        const data = await resp.json()
        // 复用现有动作：写入新双 token（后端已轮换，旧 refresh 作废）并 persist 落盘
        this.saveAuth(data)
      })()
      try {
        await refreshPromise
      } finally {
        // 无论成败都复位，否则一次失败后所有后续请求都会拿到这个 rejected Promise
        refreshPromise = null
      }
    },
    setCourse(course) {
      this.currentCourseId = course?.course_id || ''
      this.currentCourseName = course?.course_name || ''
      this.currentCourseRole = course?.role_in_course || course?.role || ''
      this.persist()
    },
    setThread(threadId, messages = []) {
      this.threadId = threadId || v4Like()
      this.messages = messages
      this.persist()
    },
    newThread() {
      this.threadId = v4Like()
      this.messages = []
      this.lastQuestion = ''
      this.lastAnswer = ''
      this.persist()
    },
    clearAuth() {
      this.$reset()
      this.threadId = v4Like()
      localStorage.removeItem(STORAGE_KEY)
    }
  }
})
