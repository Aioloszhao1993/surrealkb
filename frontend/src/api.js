import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// 请求拦截：附带 token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截：401 时清理登录态
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 401) {
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
