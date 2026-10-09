import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api, { errMsg } from '../api'
import { sizeFmt } from '../components/format'

export default function Upload() {
  const nav = useNavigate()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [file, setFile] = useState(null)
  const [cover, setCover] = useState(null)
  const [progress, setProgress] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef(null)
  const coverRef = useRef(null)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    if (!title.trim()) return setError('请填写标题')
    if (!file) return setError('请选择视频文件')

    const fd = new FormData()
    fd.append('title', title.trim())
    fd.append('description', description.trim())
    fd.append('file', file)
    if (cover) fd.append('cover', cover)

    setBusy(true)
    try {
      const { data } = await api.post('/videos', fd, {
        onUploadProgress: (evt) => {
          if (evt.total) setProgress(Math.round((evt.loaded / evt.total) * 100))
        },
      })
      nav(`/watch/${data.id}`)
    } catch (err) {
      setError(errMsg(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-card wide">
      <h1 className="auth-title">上传梦境</h1>
      <p className="auth-sub">支持 mp4 / webm / mov / mkv / ogg</p>

      <form onSubmit={submit} className="form">
        <label className="field">
          <span>标题 *</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} placeholder="给这段影像起个名字" />
        </label>

        <label className="field">
          <span>描述</span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder="描述一下这个梦…"
          />
        </label>

        <div className="field">
          <span>视频文件 *</span>
          <div className="file-drop" onClick={() => fileRef.current?.click()}>
            {file ? (
              <>
                <strong>{file.name}</strong>
                <em>{sizeFmt(file.size)}</em>
              </>
            ) : (
              <em>点击选择视频文件</em>
            )}
          </div>
          <input
            ref={fileRef}
            type="file"
            accept="video/*"
            hidden
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </div>

        <div className="field">
          <span>封面（可选）</span>
          <div className="file-drop" onClick={() => coverRef.current?.click()}>
            {cover ? <strong>{cover.name}</strong> : <em>点击选择封面图（jpg/png/webp）</em>}
          </div>
          <input
            ref={coverRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            hidden
            onChange={(e) => setCover(e.target.files?.[0] || null)}
          />
        </div>

        {busy && (
          <div className="progress">
            <div className="progress-bar" style={{ width: `${progress}%` }} />
            <span>{progress}%</span>
          </div>
        )}

        {error && <div className="alert">{error}</div>}

        <button className="btn primary block" type="submit" disabled={busy}>
          {busy ? '上传中…' : '发布'}
        </button>
      </form>
    </div>
  )
}
