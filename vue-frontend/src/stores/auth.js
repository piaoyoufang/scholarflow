import { defineStore } from 'pinia'
import { v4Like } from '../utils/id'

const STORAGE_KEY = 'course_ai_auth_state'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    userId: '',
    accessToken: '',
    expiresAt: '',
    refreshToken: '',
    refreshExpiresAt: '',
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
    hasCourse: (state) => Boolean(state.currentCourseId)
  },
  actions: {
    restoreFromStorage() {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      try {
        const data = JSON.parse(raw)
        Object.assign(this, data)
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
      this.persist()
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
