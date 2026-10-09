import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { errMsg } from '../api'
import { useAuth } from '../store'
import PresetGrid from '../components/PresetGrid'

export default function Register() {
  const { register } = useAuth()
  const nav = useNavigate()
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [avatar, setAvatar] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    if (username.trim().length < 3) return setError('用户名至少 3 个字符')
    if (password.length < 6) return setError('密码至少 6 位')
    setBusy(true)
    try {
      await register(username.trim(), password, email.trim(), avatar)
      nav('/', { replace: true })
    } catch (err) {
      setError(errMsg(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-card">
      <h1 className="auth-title">加入梦境</h1>
      <p className="auth-sub">创建账号，开始记录你的影像</p>

      <form onSubmit={submit} className="form">
        <PresetGrid value={avatar} onChange={setAvatar} username={username} />

        <label className="field">
          <span>用户名 *</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </label>
        <label className="field">
          <span>邮箱（可选）</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </label>
        <label className="field">
          <span>密码 *</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
          />
        </label>

        {error && <div className="alert">{error}</div>}

        <button className="btn primary block" disabled={busy}>
          {busy ? '创建中…' : '创建账号'}
        </button>
      </form>

      <p className="auth-foot">
        已有账号？<Link to="/login">去登录</Link>
      </p>
    </div>
  )
}
