import { useEffect, useState } from 'react'
import api, { errMsg } from '../api'
import { useAuth } from '../store'
import { PRESET_AVATARS } from '../presets'
import Avatar from './Avatar'
import portal from './Portal'

export default function AvatarPicker({ onClose }) {
  const { user, updateUser } = useAuth()
  const [tab, setTab] = useState('preset') // preset | upload
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState('')

  useEffect(() => {
    if (!file) {
      setPreview('')
      return
    }
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const choosePreset = async (preset) => {
    setBusy(true)
    setErr('')
    try {
      const { data } = await api.patch('/auth/avatar', { avatar: preset })
      updateUser(data)
      onClose?.()
    } catch (e) {
      setErr(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  const upload = async () => {
    if (!file) return setErr('请先选择一张图片')
    setBusy(true)
    setErr('')
    try {
      const fd = new FormData()
      fd.append('file', file)
      const { data } = await api.post('/auth/avatar', fd)
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
        <h2 className="wx-title">设置头像</h2>

        <div className="tabs">
          <button className={tab === 'preset' ? 'tab active' : 'tab'} onClick={() => setTab('preset')}>
            预设头像
          </button>
          <button className={tab === 'upload' ? 'tab active' : 'tab'} onClick={() => setTab('upload')}>
            上传图片
          </button>
        </div>

        {tab === 'preset' ? (
          <div className="preset-grid">
            {PRESET_AVATARS.map((p) => (
              <button
                key={p.id}
                className={user?.avatar === p.data ? 'preset active' : 'preset'}
                onClick={() => choosePreset(p.data)}
                disabled={busy}
                title={p.name}
                style={{ background: p.bg }}
              >
                {p.glyph}
              </button>
            ))}
          </div>
        ) : (
          <div className="upload-zone">
            <div className="upload-preview">
              {preview ? (
                <img src={preview} alt="预览" />
              ) : (
                <Avatar user={user} size="xl" />
              )}
            </div>
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
            <p className="faint">支持 jpg / png / webp / gif，≤ 5MB，将裁剪为圆形显示</p>
            <button className="btn primary block" onClick={upload} disabled={busy || !file}>
              {busy ? '上传中…' : '保存头像'}
            </button>
          </div>
        )}

        {err && <div className="alert">{err}</div>}
      </div>
    </div>
  )
}
