import request, { API_BASE_URL } from './request'
import { useAuthStore } from '../stores/auth'

export const authApi = {
  login: (payload) => request.post('/auth/login', payload),
  register: (payload) => request.post('/auth/register', payload),
  refresh: (refreshToken) => request.post('/auth/refresh', { refresh_token: refreshToken }),
  logout: (refreshToken) => request.post('/auth/logout', { refresh_token: refreshToken })
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

// 流式问答：EventSource 只支持 GET，问答是 POST，所以用 fetch + ReadableStream 手动解 SSE 帧
// callbacks: onStatus(节点进度) / onAnswer(完整答案与引用) / onError(错误信息)；signal 关联 AbortController 实现「停止生成」
export async function askCourseStream(courseId, payload, { onStatus, onAnswer, onError, signal }) {
  const auth = useAuthStore()
  // fetch 不走 axios 拦截器：token 要手动带，401 静默刷新也要自己做（失败后刷新一次并重试）
  const postStream = () => fetch(`${API_BASE_URL}/courses/${courseId}/ask/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${auth.accessToken}`
    },
    body: JSON.stringify(payload),
    signal
  })
  let resp = await postStream()
  if (resp.status === 401) {
    await auth.refresh()
    resp = await postStream()
  }
  if (!resp.ok) {
    // 响应头阶段就失败（401/403/404/429）：没有事件流可读，直接按普通错误抛出
    throw new Error(`请求失败：${resp.status}`)
  }

  const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    // SSE 帧以 \n\n 分隔；最后一帧可能不完整，留在 buffer 里等下一块
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const eventLine = frame.split('\n').find((l) => l.startsWith('event:'))
      const dataLine = frame.split('\n').find((l) => l.startsWith('data:'))
      if (!eventLine || !dataLine) continue
      const event = eventLine.slice(6).trim()
      const data = JSON.parse(dataLine.slice(5).trim())
      if (event === 'status') onStatus?.(data) // 节点进度：正在检索 / 正在生成……
      else if (event === 'answer') onAnswer?.(data) // 完整答案：结构化输出不支持逐 token，一次性下发
      else if (event === 'error') onError?.(data.msg)
    }
  }
}
