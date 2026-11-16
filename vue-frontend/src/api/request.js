import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'
import { useAuthStore } from '../stores/auth'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const request = axios.create({
  baseURL: API_BASE_URL,
  timeout: 180000
})

// 同一时间只发起一次刷新请求，其余 401 请求排队等待同一个结果
let refreshPromise = null

async function refreshAccessToken(auth) {
  const { data } = await axios.post(
    `${API_BASE_URL}/auth/refresh`,
    { refresh_token: auth.refreshToken },
    { timeout: 15000 }
  )
  auth.saveAuth(data)
  return data.access_token
}

function forceLogin(auth) {
  const onLoginPage = router.currentRoute.value?.path === '/login'
  auth.clearAuth()
  if (!onLoginPage) {
    ElMessage.error('登录已过期，请重新登录')
    router.push('/login')
  }
}

request.interceptors.request.use((config) => {
  const auth = useAuthStore()
  auth.restoreFromStorage()
  if (auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`
  }
  return config
})

request.interceptors.response.use(
  (response) => response,
  async (error) => {
    const auth = useAuthStore()
    const status = error?.response?.status
    const original = error?.config
    const isAuthCall = typeof original?.url === 'string' && original.url.includes('/auth/')

    // access_token 只有 15 分钟，过期后先用 refresh_token 静默续期，再自动重放原请求
    if (status === 401 && auth.refreshToken && original && !original._retried && !isAuthCall) {
      original._retried = true
      try {
        if (!refreshPromise) {
          refreshPromise = refreshAccessToken(auth).finally(() => {
            refreshPromise = null
          })
        }
        const token = await refreshPromise
        original.headers = original.headers || {}
        original.headers.Authorization = `Bearer ${token}`
        return request(original)
      } catch (refreshError) {
        forceLogin(auth)
        return Promise.reject(refreshError)
      }
    }

    if (status === 401) {
      forceLogin(auth)
    }
    return Promise.reject(error)
  }
)

const STATUS_TEXT = {
  400: '请求参数有误，请检查后重试',
  401: '登录已过期，请重新登录',
  403: '没有权限执行该操作',
  404: '请求的内容不存在或已被删除',
  405: '请求方式不被支持',
  409: '数据状态已变化，请刷新后重试',
  413: '上传的文件过大',
  415: '不支持的文件格式',
  422: '提交的数据格式不正确',
  429: '操作过于频繁，请稍后再试',
  500: '服务器内部错误，请稍后重试',
  502: '服务暂时不可用，请稍后重试',
  503: '服务暂时不可用，请稍后重试',
  504: '请求超时，请稍后重试'
}

const VALIDATION_TEXT = {
  'Field required': '不能为空',
  'Input should be a valid string': '必须是文本',
  'Input should be a valid integer': '必须是整数',
  'Input should be a valid number': '必须是数字',
  'Input should be a valid list': '必须是列表',
  'Input should be a valid dictionary': '格式不正确',
  'String should have at least 1 character': '不能为空'
}

const FIELD_TEXT = {
  username: '用户名',
  password: '密码',
  email: '邮箱',
  nickname: '昵称',
  course_id: '课程',
  course_name: '课程名称',
  description: '课程说明',
  invite_code: '邀请码',
  question: '问题',
  query: '检索问题',
  topic: '主题',
  goal: '学习目标',
  difficulty: '难度',
  count: '数量',
  event_id: '问答事件',
  filename: '文件名',
  file: '文件',
  thread_id: '会话'
}

const CJK = /[\u4e00-\u9fa5]/

function hasCJK(text) {
  return typeof text === 'string' && CJK.test(text)
}

function translateField(name) {
  if (!name) return ''
  return FIELD_TEXT[name] || (hasCJK(name) ? name : '该字段')
}

function translateValidation(message) {
  if (!message) return ''
  return hasCJK(message) ? message : VALIDATION_TEXT[message] || '格式不正确'
}

export function errorMessage(error) {
  const response = error?.response
  const status = response?.status
  const detail = response?.data?.detail

  if (!response) {
    if (error?.code === 'ECONNABORTED' || error?.code === 'ETIMEDOUT') {
      return '请求超时，请稍后重试'
    }
    return '无法连接服务器，请确认后端服务已启动'
  }

  if (Array.isArray(detail)) {
    const text = detail
      .map((item) => {
        const field = Array.isArray(item?.loc) ? item.loc.slice(1).map(translateField).filter(Boolean).join('.') : ''
        const message = translateValidation(item?.msg)
        return field && message ? `${field}：${message}` : message
      })
      .filter(Boolean)
      .join('；')
    if (text) return text
  }

  if (typeof detail === 'string' && detail.trim()) {
    return hasCJK(detail) ? detail : STATUS_TEXT[status] || '操作失败，请稍后重试'
  }

  if (detail && typeof detail === 'object') {
    const message = detail.msg || detail.message
    if (hasCJK(message)) return message
  }

  return STATUS_TEXT[status] || '操作失败，请稍后重试'
}

export default request
