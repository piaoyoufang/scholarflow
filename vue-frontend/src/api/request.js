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
  return error?.response?.data?.detail || error?.message || '请求失败，请稍后重试'
}

export default request
