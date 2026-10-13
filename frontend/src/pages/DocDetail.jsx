import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import api, { errMsg } from '../api'
import { num, timeAgo } from '../components/format'
import Avatar from '../components/Avatar'
import HoverUser from '../components/UserHoverCard'
import { useAuth } from '../store'

const STATUS_LABEL = { ready: '已就绪', pending: '处理中', failed: '处理失败' }

function sizeFmt(bytes) {
  if (!bytes) return '—'
  const u = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let v = bytes
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${u[i]}`
}

export default function DocDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const nav = useNavigate()
  const [doc, setDoc] = useState(null)
  const [chunks, setChunks] = useState([])
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [busy, setBusy] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [title, setTitle] = useState('')

  const flash = (m) => {
    setToast(m)
    setTimeout(() => setToast(''), 1800)
  }

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/documents/${id}`)
      setDoc(data)
      setTitle(data.title)
      const c = await api.get(`/documents/${id}/chunks`)
      setChunks(c.data)
    } catch (e) {
      setError(errMsg(e))
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  const saveTitle = async () => {
    if (!title.trim() || title.trim() === doc.title) {
      setRenaming(false)
      return
    }
    try {
      const { data } = await api.patch(`/documents/${id}`, { title: title.trim() })
      setDoc(data)
      setRenaming(false)
      flash('标题已更新')
    } catch (e) {
      flash(errMsg(e))
    }
  }

  const reindex = async () => {
    setBusy(true)
    try {
      await api.post(`/documents/${id}/reindex`)
      flash('已重建索引')
      await load()
    } catch (e) {
      flash(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!confirm('确定删除这篇文档吗？其分块与向量也会一并删除，不可撤销。')) return
    try {
      await api.delete(`/documents/${id}`)
      nav('/')
    } catch (e) {
      flash(errMsg(e))
    }
  }

  const ask = () => {
    window.dispatchEvent(
      new CustomEvent('ai-ask', { detail: `请根据文档《${doc.title}》总结它的主要内容。` })
    )
  }

  if (error) return <div className="empty">{error}</div>
  if (!doc) return <div className="page-loading">正在加载文档…</div>

  const mine = user && (doc.owner_id === user.id || ['owner', 'admin'].includes(user.role))

  return (
    <div className="doc-detail">
      <div className="doc-head">
        <div className="doc-head-main">
          <span className="doc-head-icon">📄</span>
          <div className="doc-head-info">
            {renaming ? (
              <div className="inline-edit">
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  maxLength={200}
                  autoFocus
                  onKeyDown={(e) => e.key === 'Enter' && saveTitle()}
                />
                <button className="btn primary" onClick={saveTitle}>
                  保存
                </button>
                <button className="btn ghost" onClick={() => setRenaming(false)}>
                  取消
                </button>
              </div>
            ) : (
              <h1 className="doc-title">
                {doc.title}
                {mine && (
                  <button className="link edit-title" onClick={() => setRenaming(true)}>
                    改名
                  </button>
                )}
              </h1>
            )}
            <div className="doc-sub">
              <span className={`doc-status ${doc.status}`}>{STATUS_LABEL[doc.status] || doc.status}</span>
              <span>· {doc.doc_type.toUpperCase()}</span>
              <span>· {sizeFmt(doc.size)}</span>
              <span>· {num(doc.char_count)} 字</span>
              <span>· {chunks.length} 段</span>
              <span>· {timeAgo(doc.created_at)}</span>
            </div>
            {doc.error && <div className="alert">{doc.error}</div>}
          </div>
        </div>

        <div className="doc-head-actions">
          <button className="btn action ai-ask-btn" onClick={ask} disabled={doc.status !== 'ready'}>
            ✦ 问问 AI
          </button>
          {mine && (
            <>
              <button className="btn ghost" onClick={reindex} disabled={busy}>
                {busy ? '重建中…' : '重建索引'}
              </button>
              <button className="btn danger" onClick={remove}>
                删除
              </button>
            </>
          )}
        </div>
      </div>

      {doc.owner_id && (
        <div className="doc-owner">
          <HoverUser user={{ id: doc.owner_id, username: doc.owner?.username || '上传者' }}>
            <Link to={`/user/${doc.owner_id}`} className="author-name">
              <Avatar user={doc.owner || { username: '?' }} size="sm" />
              <span>{doc.owner?.username || '上传者'}</span>
            </Link>
          </HoverUser>
        </div>
      )}

      <h2 className="section-title">文档分块（{chunks.length}）</h2>
      {chunks.length === 0 ? (
        <div className="empty">这篇文档还没有分块内容。</div>
      ) : (
        <div className="chunk-list">
          {chunks.map((c) => (
            <div key={c.id} className="chunk-item">
              <span className="chunk-seq">#{c.seq + 1}</span>
              <p className="chunk-text">{c.content}</p>
            </div>
          ))}
        </div>
      )}

      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
