import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// 请求拦截：附带 token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截：会话失效（401）时清理登录态并跳登录页
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err?.response?.status
    const url = err?.config?.url || ''
    // 「校验凭据」类接口的 401 是正常业务失败（密码输错、原密码不对），
    // 不是会话过期。必须排除掉，否则在弹窗里输错密码会被直接弹到登录页。
    const credentialCheck =
      url.includes('/auth/login') ||
      url.includes('/auth/token') ||
      url.includes('/auth/password')
    if (status === 401 && !credentialCheck) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      if (!location.pathname.startsWith('/login')) location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export function errMsg(err) {
  const d = err?.response?.data?.detail
  if (Array.isArray(d)) return d.map((x) => x.msg).join('；')
  return d || err?.message || '请求失败'
}

export default api
