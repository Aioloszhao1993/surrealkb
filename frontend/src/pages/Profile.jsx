import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import api from '../api'
import DocCard from '../components/DocCard'
import Avatar from '../components/Avatar'
import AvatarPicker from '../components/AvatarPicker'
import EditProfile from '../components/EditProfile'
import { num } from '../components/format'
import { useAuth } from '../store'

export default function Profile() {
  const { id } = useParams()
  const { user: me } = useAuth()
  const [profile, setProfile] = useState(null)
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

  const loadDocs = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/documents', { params: { owner_id: id, page_size: 60 } })
      setData(data)
    } catch {
      setData({ items: [], total: 0 })
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    loadProfile()
    loadDocs()
  }, [loadProfile, loadDocs])

  const toggleFollow = async () => {
    if (!me) return
    setFollowBusy(true)
    try {
      const { data } = await api.post(`/users/${id}/follow`)
      setProfile((p) => ({ ...p, is_following: data.following, followers: data.followers }))
    } catch {
      /* ignore */
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
              <b>{num(profile.documents)}</b> 文档
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

      <h2 className="section-title">上传的文档（{data.total}）</h2>
      {loading ? (
        <div className="page-loading">加载中…</div>
      ) : data.items.length === 0 ? (
        <div className="empty">这位成员还没有上传任何文档。</div>
      ) : (
        <div className="grid">
          {data.items.map((d) => (
            <DocCard key={d.id} doc={d} />
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
