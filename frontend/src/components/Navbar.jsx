import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../store'
import useWxStatus from '../useWxStatus'
import AccountMenu from './AccountMenu'
import WechatLogin from './WechatLogin'

export default function Navbar() {
  const { user } = useAuth()
  const [q, setQ] = useState('')
  const [showWx, setShowWx] = useState(false)
  const wxEnabled = useWxStatus()
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
          <>
            {wxEnabled && (
              <button className="btn ghost" onClick={() => setShowWx(true)}>
                微信登录
              </button>
            )}
            <Link to="/login" className="btn ghost">
              登录
            </Link>
            <Link to="/register" className="btn primary">
              免费使用
            </Link>
          </>
        )}
      </nav>

      {showWx && <WechatLogin onClose={() => setShowWx(false)} onDone={() => nav('/')} />}
    </header>
  )
}
