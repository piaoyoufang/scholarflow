import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from './auth'

// fetch 是全局函数，直接用 vi.stubGlobal 替换为可控 mock
// auth.refresh 特意用原生 fetch（不走 axios 拦截器防递归），所以 mock 全局 fetch 即可覆盖
const fetchMock = vi.fn()
vi.stubGlobal('fetch', fetchMock)

beforeEach(() => {
  setActivePinia(createPinia()) // 每个用例一个干净的 Pinia 实例
  localStorage.clear()
  fetchMock.mockReset()
})

describe('auth.refresh', () => {
  it('刷新成功后写入新双 token 并落盘', async () => {
    const store = useAuthStore()
    store.refreshToken = 'old-refresh'
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        user_id: 'u1',
        access_token: 'new-access',
        refresh_token: 'new-refresh',
        role: 'student'
      })
    })

    await store.refresh()

    expect(store.accessToken).toBe('new-access')
    expect(store.refreshToken).toBe('new-refresh') // 后端轮换：必须换新 refresh
    // persist() 落盘的是 camelCase 键（见 auth.js persist 实现）
    expect(JSON.parse(localStorage.getItem('course_ai_auth_state')).accessToken).toBe('new-access')
  })

  it('并发调用只发一次刷新请求（单例 Promise 去重）', async () => {
    const store = useAuthStore()
    store.refreshToken = 'old-refresh'
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ user_id: 'u1', access_token: 'a', refresh_token: 'r' })
    })

    // 模拟 3 个请求同时 401：三个 refresh 并发触发
    await Promise.all([store.refresh(), store.refresh(), store.refresh()])

    expect(fetchMock).toHaveBeenCalledTimes(1) // Token 静默刷新 bug 修复的回归保障
  })

  it('refresh token 失效时抛错（由拦截器决定登出）', async () => {
    const store = useAuthStore()
    fetchMock.mockResolvedValueOnce({ ok: false })
    await expect(store.refresh()).rejects.toThrow()
  })

  it('一次刷新失败后，后续调用能重新发起（Promise 复位）', async () => {
    const store = useAuthStore()
    store.refreshToken = 'old-refresh'
    fetchMock.mockResolvedValueOnce({ ok: false })
    await expect(store.refresh()).rejects.toThrow()

    // finally 复位 refreshPromise：失败后的下一次刷新应重新发请求，而不是复用 rejected Promise
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ user_id: 'u1', access_token: 'a2', refresh_token: 'r2' })
    })
    await store.refresh()
    expect(store.accessToken).toBe('a2')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
