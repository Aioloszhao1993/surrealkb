import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { errMsg } from '../api'
import { useAuth } from '../store'
import WechatLogin from '../components/WechatLogin'

export default function Login() {
  const { login } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [showWx, setShowWx] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await login(username.trim(), password)
      nav(loc.state?.from || '/', { replace: true })
    } catch (err) {
      setError(errMsg(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-card">
      <h1 className="auth-title">登录</h1>
      <p className="auth-sub">登录以管理知识库、上传文档与提问</p>

      <form onSubmit={submit} className="form">
        <label className="field">
          <span>用户名</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </label>
        <label className="field">
          <span>密码</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>

        {error && <div className="alert">{error}</div>}

        <button className="btn primary block" disabled={busy}>
          {busy ? '登录中…' : '登录'}
        </button>
      </form>

      <div className="divider">
        <span>或</span>
      </div>

      <button className="btn wechat block" onClick={() => setShowWx(true)}>
        <span className="wx-logo">✆</span> 微信扫码登录
      </button>

      <p className="auth-foot">
        还没有账号？<Link to="/register">免费注册</Link>
      </p>

      {showWx && (
        <WechatLogin onClose={() => setShowWx(false)} onDone={() => nav(loc.state?.from || '/', { replace: true })} />
      )}
    </div>
  )
}
