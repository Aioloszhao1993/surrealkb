import { useEffect, useState } from 'react'
import api, { errMsg } from '../api'
import { useAuth } from '../store'
import Avatar from './Avatar'
import portal from './Portal'

export default function EditProfile({ onClose }) {
  const { user, updateUser } = useAuth()
  const [username, setUsername] = useState(user?.username || '')
  const [bio, setBio] = useState(user?.bio || '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const save = async () => {
    setBusy(true)
    setErr('')
    try {
      const payload = {}
      if (username.trim() && username.trim() !== user.username) payload.username = username.trim()
      if (bio !== (user.bio || '')) payload.bio = bio
      if (Object.keys(payload).length === 0) return onClose?.()
      const { data } = await api.patch('/users/me', payload)
      updateUser(data)
      onClose?.()
    } catch (e) {
      setErr(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  return portal(
    <div className="modal-back" onClick={onClose}>
      <div className="avatar-modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-x" onClick={onClose} aria-label="关闭">
          ✕
        </button>
        <h2 className="wx-title">编辑资料</h2>

        <div className="edit-row">
          <Avatar user={user} size="lg" />
          <div className="edit-fields">
            <label className="field">
              <span>昵称</span>
              <input value={username} onChange={(e) => setUsername(e.target.value)} maxLength={50} />
            </label>
            <label className="field">
              <span>个性签名</span>
              <input
                value={bio}
                onChange={(e) => setBio(e.target.value)}
                maxLength={200}
                placeholder="介绍一下自己～"
              />
            </label>
          </div>
        </div>

        {err && <div className="alert">{err}</div>}
        <button className="btn primary block" onClick={save} disabled={busy}>
          {busy ? '保存中…' : '保存'}
        </button>
      </div>
    </div>
  )
}
