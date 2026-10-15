import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import { useAuth } from '../store'
import { num } from './format'
import Avatar from './Avatar'
import ChangePassword from './ChangePassword'

/**
 * B 站式「账号头像」入口：
 * - 顶栏只显示头像（不放昵称）
 * - 悬停：头像放大 + 弹出个人信息卡（粉丝/关注/作品、个性签名、快捷入口）
 * - 点击：在触屏/无悬停环境下切换展开
 */
export default function AccountMenu() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const [stats, setStats] = useState(null)
  const [tenant, setTenant] = useState(null)
  const [showPwd, setShowPwd] = useState(false)
  const timer = useRef(null)
  const wrapRef = useRef(null)

  const load = () => {
    api
      .get(`/users/${user.id}`)
      .then(({ data }) => setStats(data))
      .catch(() => setStats(null))
    api
      .get('/tenants/current')
      .then(({ data }) => setTenant(data))
      .catch(() => setTenant(null))
  }

  useEffect(() => {
    if (open && !stats) load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('click', onDoc)
    return () => document.removeEventListener('click', onDoc)
  }, [])

  const enter = () => {
    clearTimeout(timer.current)
    setOpen(true)
  }
  const leave = () => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setOpen(false), 160)
  }

  if (!user) return null

  return (
    <div className="account" ref={wrapRef} onMouseEnter={enter} onMouseLeave={leave}>
      <button
        type="button"
        className={open ? 'account-trigger open' : 'account-trigger'}
        onClick={() => setOpen((v) => !v)}
        aria-label="账号菜单"
        title={user.username}
      >
        <Avatar user={user} size="sm" className="account-avatar" />
      </button>

      {open && (
        <div className="account-card">
          <div className="account-head">
            <Avatar user={user} size="lg" />
            <div className="account-id">
              <span className="account-name">{user.username}</span>
              <p className="account-bio">{user.bio || '这个人很神秘，什么都没写～'}</p>
            </div>
          </div>

          <div className="account-stats">
            <span>
              <b>{stats ? num(stats.following) : '—'}</b> 关注
            </span>
            <span>
              <b>{stats ? num(stats.followers) : '—'}</b> 粉丝
            </span>
            <span>
              <b>{stats ? num(stats.documents) : '—'}</b> 文档
            </span>
          </div>

          {tenant && (
            <Link to="/team" className="account-tenant" onClick={() => setOpen(false)}>
              <span className="account-tenant-label">知识库</span>
              <span className="account-tenant-name">{tenant.name}</span>
            </Link>
          )}

          <div className="account-links">
            <Link to={`/user/${user.id}`} onClick={() => setOpen(false)}>
              <span>☾</span> 我的主页
            </Link>
            <Link to="/upload" onClick={() => setOpen(false)}>
              <span>⇪</span> 上传文档
            </Link>
            <Link to="/team" onClick={() => setOpen(false)}>
              <span>◈</span> 知识库团队
            </Link>
            <button
              type="button"
              onClick={() => {
                setOpen(false)
                setShowPwd(true)
              }}
            >
              <span>⚿</span> 修改密码
            </button>
          </div>

          <button className="account-logout" onClick={logout}>
            退出登录
          </button>
        </div>
      )}

      {showPwd && <ChangePassword onClose={() => setShowPwd(false)} />}
    </div>
  )
}
