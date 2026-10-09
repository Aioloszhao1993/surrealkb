import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import api from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('user') || 'null')
    } catch {
      return null
    }
  })
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) {
      setReady(true)
      return
    }
    api
      .get('/auth/me')
      .then(({ data }) => {
        setUser(data)
        localStorage.setItem('user', JSON.stringify(data))
      })
      .catch(() => setUser(null))
      .finally(() => setReady(true))
  }, [])

  const persist = useCallback((token, u) => {
    localStorage.setItem('token', token)
    localStorage.setItem('user', JSON.stringify(u))
    setUser(u)
  }, [])

  const login = useCallback(
    async (username, password) => {
      const { data } = await api.post('/auth/login', { username, password })
      persist(data.access_token, data.user)
      return data.user
    },
    [persist]
  )

  const register = useCallback(
    async (username, password, email, avatar) => {
      const { data } = await api.post('/auth/register', {
        username,
        password,
        email: email || null,
        avatar: avatar || null,
      })
      persist(data.access_token, data.user)
      return data.user
    },
    [persist]
  )

  const logout = useCallback(() => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    setUser(null)
  }, [])

  // 微信扫码登录成功 / 头像更新后回写用户信息
  const applyToken = useCallback((token, u) => persist(token, u), [persist])

  const updateUser = useCallback((u) => {
    setUser(u)
    localStorage.setItem('user', JSON.stringify(u))
  }, [])

  const value = useMemo(
    () => ({ user, ready, login, register, logout, applyToken, updateUser }),
    [user, ready, login, register, logout, applyToken, updateUser]
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth 必须在 AuthProvider 内使用')
  return ctx
}
