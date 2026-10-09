import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import api, { errMsg } from '../api'
import { useAuth } from '../store'
import { num, sizeFmt, timeAgo } from '../components/format'
import Avatar from '../components/Avatar'
import HoverUser from '../components/UserHoverCard'

export default function Watch() {
  const { id } = useParams()
  const { user } = useAuth()
  const nav = useNavigate()
  const [video, setVideo] = useState(null)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')

  const flash = (m) => {
    setToast(m)
    setTimeout(() => setToast(''), 1800)
  }

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/videos/${id}`)
      setVideo(data)
    } catch (e) {
      setError(errMsg(e))
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  const requireLogin = () => {
    if (user) return true
    nav('/login', { state: { from: `/watch/${id}` } })
    return false
  }

  const act = async (kind) => {
    if (!requireLogin()) return
    const { data } = await api.post(`/videos/${id}/${kind}`)
    if (kind === 'like') setVideo((v) => ({ ...v, liked: data.active, likes: data.count }))
    if (kind === 'favorite')
      setVideo((v) => ({ ...v, favorited: data.active, favorites: data.count }))
  }

  const share = async () => {
    try {
      const { data } = await api.post(`/videos/${id}/share`)
      setVideo((v) => ({ ...v, views: data.count }))
      const url = `${location.origin}/watch/${id}`
      if (navigator.share) {
        await navigator.share({ title: video?.title, url })
      } else {
        await navigator.clipboard.writeText(url)
        flash('链接已复制到剪贴板')
      }
    } catch (e) {
      flash(errMsg(e))
    }
  }

  const remove = async () => {
    if (!confirm('确定删除这个视频吗？此操作不可撤销。')) return
    try {
      await api.delete(`/videos/${id}`)
      nav('/')
    } catch (e) {
      flash(errMsg(e))
    }
  }

  if (error) return <div className="empty">{error}</div>
  if (!video) return <div className="page-loading">正在打捞这段梦境…</div>

  const mine = user && video.owner.id === user.id

  return (
    <div className="watch">
      <div className="player-wrap">
        <video className="player" src={video.url} controls playsInline poster={video.cover ? `/media/${video.cover}` : undefined} />
        <div className="player-aura" />
      </div>

      <h1 className="watch-title">{video.title}</h1>

      <div className="watch-bar">
        <div className="author">
          <HoverUser user={video.owner}>
            <Link to={`/user/${video.owner.id}`} className="author-avatar-link">
              <Avatar user={video.owner} size="md" />
            </Link>
          </HoverUser>
          <div>
            <HoverUser user={video.owner}>
              <Link to={`/user/${video.owner.id}`} className="author-name">
                {video.owner.username}
              </Link>
            </HoverUser>
            <div className="faint">{timeAgo(video.created_at)} · {sizeFmt(video.size)}</div>
          </div>
        </div>

        <div className="actions">
          <button className={video.liked ? 'btn action active' : 'btn action'} onClick={() => act('like')}>
            ♥ 点赞 {num(video.likes)}
          </button>
          <button
            className={video.favorited ? 'btn action active' : 'btn action'}
            onClick={() => act('favorite')}
          >
            ★ 收藏 {num(video.favorites)}
          </button>
          <button className="btn action" onClick={share}>
            ⇪ 转发 {num(video.shares)}
          </button>
          <button
            className="btn action ai-ask-btn"
            onClick={() =>
              window.dispatchEvent(
                new CustomEvent('ai-ask', {
                  detail: `介绍一下《${video.title}》这个视频，它讲了什么？`,
                })
              )
            }
          >
            ✦ 问问 AI
          </button>
          {mine && (
            <button className="btn danger" onClick={remove}>
              删除
            </button>
          )}
        </div>
      </div>

      <div className="watch-meta">
        <span>▶ {num(video.views)} 次播放</span>
      </div>

      <p className="watch-desc">{video.description || '这段梦境没有留下描述…'}</p>

      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
