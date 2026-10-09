import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import api, { errMsg } from '../api'
import VideoCard from '../components/VideoCard'
import Avatar from '../components/Avatar'
import AvatarPicker from '../components/AvatarPicker'
import EditProfile from '../components/EditProfile'
import { num } from '../components/format'
import { useAuth } from '../store'

const TABS = [
  { key: 'videos', label: '作品' },
  { key: 'likes', label: '点赞' },
  { key: 'favorites', label: '收藏' },
]

export default function Profile() {
  const { id } = useParams()
  const { user: me } = useAuth()
  const [profile, setProfile] = useState(null)
  const [tab, setTab] = useState('videos')
  const [data, setData] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [showAvatarPicker, setShowAvatarPicker] = useState(false)
  const [showEdit, setShowEdit] = useState(false)
  const [followBusy, setFollowBusy] = useState(false)

  const loadProfile = useCallback(async () => {
    try {
      const { data } = await api.get(`/users/${id}`)
      setProfile(data)
    } catch {
      setNotFound(true)
    }
  }, [id])

  const loadTab = useCallback(
    async (key) => {
      setLoading(true)
      try {
        const { data } = await api.get(`/users/${id}/${key}`, { params: { page_size: 60 } })
        setData(data)
      } finally {
        setLoading(false)
      }
    },
    [id]
  )

  useEffect(() => {
    loadProfile()
  }, [loadProfile])

  useEffect(() => {
    loadTab(tab)
  }, [loadTab, tab])

  const toggleFollow = async () => {
    if (!me) return
    setFollowBusy(true)
    try {
      const { data } = await api.post(`/users/${id}/follow`)
      setProfile((p) => ({ ...p, is_following: data.following, followers: data.followers }))
    } catch (e) {
      // ignore
    } finally {
      setFollowBusy(false)
    }
  }

  if (notFound) return <div className="empty">404 · 这位用户不存在于现实</div>
  if (!profile) return <div className="page-loading">正在加载主页…</div>

  const u = profile.user
  const isSelf = profile.is_self

  return (
    <div className="profile">
      <section className="profile-head">
        <div
          className={isSelf ? 'profile-avatar-wrap editable' : 'profile-avatar-wrap'}
          onClick={() => isSelf && setShowAvatarPicker(true)}
          title={isSelf ? '点击更换头像' : ''}
        >
          <Avatar user={u} size="xl" />
          {isSelf && <span className="avatar-edit-badge">更换</span>}
        </div>

        <div className="profile-info">
          <h1 className="profile-name">{u.username}</h1>
          <p className="profile-bio">{u.bio || '这个人很神秘，什么都没写～'}</p>
          <div className="profile-stats">
            <span>
              <b>{num(profile.followers)}</b> 粉丝
            </span>
            <span>
              <b>{num(profile.following)}</b> 关注
            </span>
            <span>
              <b>{num(profile.works)}</b> 作品
            </span>
            <span>
              <b>{num(profile.likes_received)}</b> 获赞
            </span>
            <span>
              <b>{num(profile.total_views)}</b> 播放
            </span>
          </div>
        </div>

        <div className="profile-actions">
          {isSelf ? (
            <button className="btn ghost" onClick={() => setShowEdit(true)}>
              编辑资料
            </button>
          ) : (
            <button
              className={profile.is_following ? 'btn ghost' : 'btn primary'}
              onClick={toggleFollow}
              disabled={followBusy || !me}
              title={me ? '' : '登录后可关注'}
            >
              {profile.is_following ? '已关注' : '+ 关注'}
            </button>
          )}
        </div>
      </section>

      <div className="tabs profile-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={tab === t.key ? 'tab active' : 'tab'}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="page-loading">加载中…</div>
      ) : data.items.length === 0 ? (
        <div className="empty">
          {tab === 'videos' ? '这位创作者还没有公开任何梦境。' : '这里还空空如也。'}
        </div>
      ) : (
        <div className="grid">
          {data.items.map((v) => (
            <VideoCard key={v.id} video={v} />
          ))}
        </div>
      )}

      {showAvatarPicker && <AvatarPicker onClose={() => setShowAvatarPicker(false)} />}
      {showEdit && (
        <EditProfile
          onClose={() => {
            setShowEdit(false)
            loadProfile()
          }}
        />
      )}
    </div>
  )
}
