import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import useClickOutside from '../useClickOutside'
import { useAuth } from '../store'
import { num } from './format'
import Avatar from './Avatar'

const OPEN_DELAY = 320
const CLOSE_DELAY = 220

/**
 * B 站式头像悬停卡片。
 * 用法： <HoverUser user={u}><span>...</span></HoverUser>
 * 鼠标移入目标区（或卡片本身）时弹出资料卡，可移入卡片点击「关注」。
 */
export default function HoverUser({ user, children, place = 'right' }) {
  const { user: me } = useAuth()
  const [open, setOpen] = useState(false)
  const [profile, setProfile] = useState(null)
  const [pos, setPos] = useState({ top: 0, left: 0 })
  const [followBusy, setFollowBusy] = useState(false)
  const openTimer = useRef(null)
  const closeTimer = useRef(null)
  const cardRef = useRef(null)
  const wrapRef = useRef(null)

  const clearTimers = () => {
    clearTimeout(openTimer.current)
    clearTimeout(closeTimer.current)
  }

  const fetchProfile = useCallback(async () => {
    try {
      const { data } = await api.get(`/users/${user.id}`)
      setProfile(data)
    } catch {
      setProfile(null)
    }
  }, [user.id])

  const placeCard = (rect) => {
    const W = 300
    const H = 190
    let left = place === 'right' ? rect.right + 12 : rect.left - W - 12
    if (left + W > window.innerWidth - 12) left = window.innerWidth - W - 12
    if (left < 12) left = 12
    let top = rect.bottom + 8
    if (top + H > window.innerHeight - 12) top = Math.max(12, rect.top - H - 8)
    setPos({ top, left })
  }

  const scheduleOpen = (e) => {
    clearTimers()
    const rect = e.currentTarget.getBoundingClientRect()
    openTimer.current = setTimeout(() => {
      placeCard(rect)
      setOpen(true)
      fetchProfile()
    }, OPEN_DELAY)
  }

  const scheduleClose = () => {
    clearTimers()
    closeTimer.current = setTimeout(() => setOpen(false), CLOSE_DELAY)
  }

  const keepOpen = () => clearTimers()

  useEffect(() => () => clearTimers(), [])

  // 点击空白处也关掉资料卡（悬停移出本来就会关，这里补上「点空白」这条路径）
  useClickOutside(wrapRef, () => setOpen(false), open)

  const toggleFollow = async () => {
    if (!me) return
    setFollowBusy(true)
    try {
      const { data } = await api.post(`/users/${user.id}/follow`)
      setProfile((p) =>
        p ? { ...p, is_following: data.following, followers: data.followers } : p
      )
    } catch {
      /* ignore */
    } finally {
      setFollowBusy(false)
    }
  }

  const isSelf = me && me.id === user.id

  return (
    <span className="hover-user" ref={wrapRef} onMouseEnter={scheduleOpen} onMouseLeave={scheduleClose}>
      {children}
      {open && (
        <div
          ref={cardRef}
          className="hover-card"
          style={{ top: pos.top, left: pos.left }}
          onMouseEnter={keepOpen}
          onMouseLeave={scheduleClose}
        >
          {profile ? (
            <>
              <div className="hover-card-top">
                <Avatar user={profile.user} size="lg" />
                <div className="hover-card-id">
                  <Link to={`/user/${profile.user.id}`} className="hover-name">
                    {profile.user.username}
                  </Link>
                  <p className="hover-bio">{profile.user.bio || '这个人很神秘，什么都没写～'}</p>
                </div>
              </div>
              <div className="hover-stats">
                <span>
                  <b>{num(profile.followers)}</b> 粉丝
                </span>
                <span>
                  <b>{num(profile.following)}</b> 关注
                </span>
                <span>
                  <b>{num(profile.documents)}</b> 文档
                </span>
              </div>
              <div className="hover-card-actions">
                {isSelf ? (
                  <Link to={`/user/${profile.user.id}`} className="btn ghost block">
                    进入我的主页
                  </Link>
                ) : (
                  <>
                    <button
                      className={profile.is_following ? 'btn ghost' : 'btn primary'}
                      onClick={toggleFollow}
                      disabled={followBusy || !me}
                      title={me ? '' : '登录后可关注'}
                    >
                      {profile.is_following ? '已关注' : '+ 关注'}
                    </button>
                    <Link to={`/user/${profile.user.id}`} className="btn ghost">
                      主页
                    </Link>
                  </>
                )}
              </div>
            </>
          ) : (
            <div className="hover-loading">
              <Avatar user={user} size="lg" />
              <p className="faint">加载中…</p>
            </div>
          )}
        </div>
      )}
    </span>
  )
}
