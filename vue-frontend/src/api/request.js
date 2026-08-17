import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'
import { useAuthStore } from '../stores/auth'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const request = axios.create({
  baseURL: API_BASE_URL,
  timeout: 180000
})

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
  (error) => {
    const auth = useAuthStore()
    const status = error?.response?.status
    if (status === 401) {
      auth.clearAuth()
      ElMessage.error('登录已过期，请重新登录')
      router.push('/login')
    }
    return Promise.reject(error)
  }
)

export function errorMessage(error) {
  const detail = error?.response?.data?.detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.slice(1).join('.') : ''
        return field ? `${field}：${item.msg}` : item.msg
      })
      .filter(Boolean)
      .join('；') || '请求参数不正确'
  }
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') return detail.msg || JSON.stringify(detail)
  return error?.message || '请求失败，请稍后重试'
}

export default request
