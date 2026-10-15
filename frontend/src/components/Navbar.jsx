import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../store'
import AccountMenu from './AccountMenu'
import AuthModal from './AuthModal'

export default function Navbar() {
  const { user } = useAuth()
  const [q, setQ] = useState('')
  const [showAuth, setShowAuth] = useState(false)
  const nav = useNavigate()

  const search = (e) => {
    e.preventDefault()
    nav(q.trim() ? `/?q=${encodeURIComponent(q.trim())}` : '/')
  }

  return (
    <header className="navbar">
      <Link to="/" className="brand">
        <span className="brand-mark">◈</span>
        <span className="brand-text">
          Surreal<span className="accent">KB</span>
        </span>
      </Link>

      <form className="search" onSubmit={search}>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜索知识库里的文档…"
          aria-label="搜索"
        />
        <button type="submit">搜索</button>
      </form>

      <nav className="nav-actions">
        {user ? (
          <>
            <Link to="/upload" className="btn ghost">
              上传文档
            </Link>
            <Link to="/team" className="btn ghost">
              知识库
            </Link>
            <AccountMenu />
          </>
        ) : (
          // 未登录时只留这一个入口：账号登录 / 微信扫码 / 免费注册都在弹窗里
          <button className="btn primary" onClick={() => setShowAuth(true)}>
            登录
          </button>
        )}
      </nav>

      {showAuth && <AuthModal onClose={() => setShowAuth(false)} onDone={() => nav('/')} />}
    </header>
  )
}
