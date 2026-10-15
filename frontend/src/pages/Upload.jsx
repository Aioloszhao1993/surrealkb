import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api, { errMsg } from '../api'
import { triggerScan } from '../scanPulse'
import { sizeFmt } from '../components/format'
import portal from '../components/Portal'

const ACCEPT = '.pdf,.docx,.txt,.md,.markdown'
const HINT = '支持 PDF / Word(.docx) / TXT / Markdown，单个不超过 50MB'

// 允许的扩展名（拖拽时校验，避免用户拖入不支持的文件）
const ALLOWED = ['pdf', 'docx', 'txt', 'md', 'markdown']
function pickFile(list) {
  if (!list || !list.length) return null
  const f = list[0]
  const ext = (f.name.split('.').pop() || '').toLowerCase()
  if (!ALLOWED.includes(ext)) return { error: `不支持的文件类型 .${ext}` }
  return { file: f }
}

export default function Upload() {
  const nav = useNavigate()
  const [title, setTitle] = useState('')
  const [file, setFile] = useState(null)
  const [tags, setTags] = useState('')
  const [progress, setProgress] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)
  const [conflict, setConflict] = useState(null) // 同名冲突信息
  const fileRef = useRef(null)
  const dragDepth = useRef(0)

  const applyFile = (f) => {
    if (!f) return
    setFile(f)
    setError('')
    // 未填标题时用文件名兜底（仅提示，不强制）
  }

  const onDrop = (e) => {
    e.preventDefault()
    dragDepth.current = 0
    setDragging(false)
    const res = pickFile(e.dataTransfer?.files)
    if (!res) return
    if (res.error) return setError(res.error)
    applyFile(res.file)
  }

  const onDragEnter = (e) => {
    e.preventDefault()
    dragDepth.current += 1
    setDragging(true)
  }
  const onDragOver = (e) => {
    e.preventDefault()
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
  }
  const onDragLeave = (e) => {
    e.preventDefault()
    dragDepth.current -= 1
    if (dragDepth.current <= 0) {
      dragDepth.current = 0
      setDragging(false)
    }
  }

  const doUpload = async (overwrite) => {
    setError('')
    const fd = new FormData()
    if (title.trim()) fd.append('title', title.trim())
    if (tags.trim()) fd.append('tags', tags.trim())
    if (overwrite) fd.append('overwrite', 'true')
    fd.append('file', file)

    setBusy(true)
    try {
      const { data } = await api.post('/documents', fd, {
        onUploadProgress: (evt) => {
          if (evt.total) setProgress(Math.round((evt.loaded / evt.total) * 100))
        },
      })
      triggerScan() // 上传成功 = 机器开始读取新文档，唤起背景扫描
      nav(`/doc/${data.id}`)
    } catch (err) {
      // 同名冲突：后端返回 409，弹确认框
      const detail = err?.response?.data?.detail
      if (err?.response?.status === 409 && detail?.document_id) {
        setConflict(detail)
      } else {
        setError(errMsg(err))
      }
    } finally {
      setBusy(false)
    }
  }

  const submit = (e) => {
    e.preventDefault()
    if (!file) return setError('请选择要上传的文档')
    doUpload(false)
  }

  return (
    <div className="auth-card wide">
      <h1 className="auth-title">上传文档</h1>
      <p className="auth-sub">{HINT}</p>

      <form onSubmit={submit} className="form">
        <label className="field">
          <span>标题（可选，默认取文件名）</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
            placeholder="给这篇文档起个名字"
          />
        </label>

        <label className="field">
          <span>标签（可选，逗号分隔，最多 10 个）</span>
          <input
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            maxLength={200}
            placeholder="如：合同, 人事制度, 财务"
          />
        </label>

        <div className="field">
          <span>文档文件 *</span>
          <div
            className={`file-drop${dragging ? ' dragging' : ''}${file ? ' has-file' : ''}`}
            onClick={() => fileRef.current?.click()}
            onDrop={onDrop}
            onDragEnter={onDragEnter}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') fileRef.current?.click()
            }}
          >
            {file ? (
              <>
                <strong>{file.name}</strong>
                <em>{sizeFmt(file.size)}</em>
                <button
                  type="button"
                  className="file-clear"
                  onClick={(e) => {
                    e.stopPropagation()
                    setFile(null)
                    if (fileRef.current) fileRef.current.value = ''
                  }}
                >
                  移除
                </button>
              </>
            ) : dragging ? (
              <em className="drop-active">松开鼠标，把文档放进来 📄</em>
            ) : (
              <>
                <em>点击选择，或把文档拖到这里</em>
                <span className="file-drop-hint">PDF / DOCX / TXT / MD</span>
              </>
            )}
          </div>
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPT}
            hidden
            onChange={(e) => {
              const res = pickFile(e.target.files)
              if (res?.error) return setError(res.error)
              applyFile(res?.file)
            }}
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
          {busy ? '处理中…' : '上传并入库'}
        </button>
      </form>

      {conflict && portal(
        <div className="modal-mask" onClick={() => setConflict(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <h3>发现同名文档</h3>
            <p className="modal-text">
              知识库中已存在《{conflict.title}》。
              <br />
              <strong>覆盖</strong>会删除旧文档（含其历史版本），保留你这次上传的新内容；
              <br />
              <strong>取消</strong>的话，可修改标题后再传，两份并存。
            </p>
            <div className="modal-actions">
              <button
                className="btn danger"
                disabled={busy}
                onClick={() => {
                  const c = conflict
                  setConflict(null)
                  if (c) doUpload(true)
                }}
              >
                覆盖旧文档
              </button>
              <button className="btn ghost" onClick={() => setConflict(null)}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
