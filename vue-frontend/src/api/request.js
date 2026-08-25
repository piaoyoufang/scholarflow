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
  // 拦截器改 async：刷新是异步操作，await 之后才能决定重放还是登出
  async (error) => {
    const auth = useAuthStore()
    const status = error?.response?.status
    const config = error?.config
    // 三个条件同时满足才尝试「刷新 + 重放」：
    // 1) 是 401
    // 2) 本请求没重试过（_retried 防死循环：新 token 也 401 说明是权限问题，不是过期问题）
    // 3) 不是 /auth 下的接口（登录失败、刷新失败本身的 401 不该再触发刷新）
    if (status === 401 && config && !config._retried && !config.url.includes('/auth/')) {
      config._retried = true
      try {
        await auth.refresh()                                  // 静默续期；并发请求在此复用同一个刷新 Promise
        config.headers.Authorization = `Bearer ${auth.accessToken}`
        return request(config)                                // 用新 token 重放原请求，用户对过期无感知
      } catch {
        // refresh 也失效（30 天没活跃 / 被吊销）：彻底登出
        auth.clearAuth()
        ElMessage.error('登录已过期，请重新登录')
        router.push('/login')
      }
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
