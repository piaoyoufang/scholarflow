import request from './request'

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
  updateQaEventStatus: (courseId, eventId, payload) => request.patch(`/courses/${courseId}/qa-events/${eventId}/status`, payload)
}
