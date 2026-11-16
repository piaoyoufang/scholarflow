import request, { API_BASE_URL } from './request'
import { useAuthStore } from '../stores/auth'

export const authApi = {
  login: (payload) => request.post('/auth/login', payload),
  register: (payload) => request.post('/auth/register', payload),
  refresh: (refreshToken) => request.post('/auth/refresh', { refresh_token: refreshToken }),
  logout: (refreshToken) => request.post('/auth/logout', { refresh_token: refreshToken })
}

export const adminApi = {
  listInvites: () => request.get('/admin/teacher-invites'),
  createInvite: (payload) => request.post('/admin/teacher-invites', payload),
  reissueInvite: (inviteId, payload) => request.post(`/admin/teacher-invites/${inviteId}/reissue`, payload),
  revokeInvite: (inviteId) => request.delete(`/admin/teacher-invites/${inviteId}`),
  listUsers: () => request.get('/admin/users'),
  createUser: (payload) => request.post('/admin/users', payload),
  updateUserRole: (userId, payload) => request.patch(`/admin/users/${userId}/role`, payload),
  resetPassword: (userId, payload) => request.post(`/admin/users/${userId}/reset-password`, payload),
  setUserDisabled: (userId, payload) => request.post(`/admin/users/${userId}/disabled`, payload),
  revokeUserSessions: (userId) => request.post(`/admin/users/${userId}/revoke-sessions`),
  deleteUser: (userId) => request.delete(`/admin/users/${userId}`),
  listCourses: () => request.get('/admin/courses'),
  deleteCourse: (courseId) => request.delete(`/admin/courses/${courseId}`),
  stats: () => request.get('/admin/stats')
}

export const threadApi = {
  list: () => request.get('/threads'),
  detail: (threadId) => request.get(`/threads/${threadId}`),
  remove: (threadId) => request.delete(`/threads/${threadId}`)
}

export const courseApi = {
  create: (payload) => request.post('/courses', payload),
  join: (payload) => request.post('/courses/join', payload),
  list: () => request.get('/courses'),
  documents: (courseId) => request.get(`/courses/${courseId}/documents`),
  uploadDocument: (courseId, file) => {
    const form = new FormData()
    form.append('file', file)
    return request.post(`/courses/${courseId}/documents/upload-async`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000
    })
  },
  reingestDocument: (courseId, sourceId) => request.post(`/courses/${courseId}/documents/${sourceId}/reingest`),
  deleteDocument: (courseId, sourceId) => request.delete(`/courses/${courseId}/documents/${sourceId}`),
  ask: (courseId, payload) => request.post(`/courses/${courseId}/ask`, payload, { timeout: 180000 }),
  feedback: (courseId, payload) => request.post(`/courses/${courseId}/feedback`, payload),
  learningPlan: (courseId, payload) => request.post(`/courses/${courseId}/agents/learning-plan`, payload, { timeout: 180000 }),
  learningPlanHistory: (courseId) => request.get(`/courses/${courseId}/agents/learning-plan/history`),
  learningPlanHistoryDetail: (courseId, recordId) => request.get(`/courses/${courseId}/agents/learning-plan/history/${recordId}`),
  removeLearningPlanHistory: (courseId, recordId) => request.delete(`/courses/${courseId}/agents/learning-plan/history/${recordId}`),
  quiz: (courseId, payload) => request.post(`/courses/${courseId}/agents/quiz`, payload, { timeout: 180000 }),
  quizHistory: (courseId) => request.get(`/courses/${courseId}/agents/quiz/history`),
  quizHistoryDetail: (courseId, recordId) => request.get(`/courses/${courseId}/agents/quiz/history/${recordId}`),
  removeQuizHistory: (courseId, recordId) => request.delete(`/courses/${courseId}/agents/quiz/history/${recordId}`),
  retrievalDebug: (courseId, payload) => request.post(`/courses/${courseId}/retrieval/debug`, payload),
  tasks: (courseId) => request.get(`/courses/${courseId}/tasks`),
  dashboard: (courseId) => request.get(`/courses/${courseId}/dashboard`),
  topQuestions: (courseId) => request.get(`/courses/${courseId}/analytics/top-questions`),
  noCitation: (courseId) => request.get(`/courses/${courseId}/analytics/no-citation`),
  lowQuality: (courseId) => request.get(`/courses/${courseId}/analytics/low-quality`),
  downFeedback: (courseId) => request.get(`/courses/${courseId}/analytics/down-feedback`),
  updateQaEventStatus: (courseId, eventId, payload) => request.patch(`/courses/${courseId}/qa-events/${eventId}/status`, payload)
}

/**
 * 流式问答：EventSource 无法携带 Authorization 头，因此用 fetch + ReadableStream 手动解析 SSE。
 * handlers 支持 meta / delta / done / error 四个事件回调，signal 用于「停止生成」。
 */
export async function askCourseStream(courseId, payload, handlers = {}, signal) {
  const postStream = () => fetch(`${API_BASE_URL}/courses/${courseId}/ask/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(handlers.token ? { Authorization: `Bearer ${handlers.token}` } : {})
    },
    body: JSON.stringify(payload),
    signal
  })

  let response = await postStream()
  // fetch 不走 axios 拦截器：401 时手动用 refresh_token 静默续期并重试一次
  if (response.status === 401) {
    try {
      const auth = useAuthStore()
      await auth.refresh()
      handlers.token = auth.accessToken
      response = await postStream()
    } catch {
      // 续期失败沿用下面的错误提示，交给页面跳转登录
    }
  }

  if (!response.ok) {
    let detail = `请求失败（${response.status}）`
    try {
      const data = await response.json()
      if (data?.detail) detail = data.detail
    } catch {
      // 响应体不是 JSON 时沿用默认提示
    }
    throw new Error(detail)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let finished = false

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const raw = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      boundary = buffer.indexOf('\n\n')

      let event = 'message'
      const dataLines = []
      for (const line of raw.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      }
      if (!dataLines.length) continue

      let data
      try {
        data = JSON.parse(dataLines.join('\n'))
      } catch {
        continue
      }
      if (event === 'done') finished = true
      handlers[event]?.(data)
    }
  }
  return finished
}
