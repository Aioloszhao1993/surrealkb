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
  const [content, setContent] = useState(null) // 提取出的纯文本全文
  const [tab, setTab] = useState('content') // content | chunks
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [busy, setBusy] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [title, setTitle] = useState('')

  // 在线编辑
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  // 版本历史
  const [revisions, setRevisions] = useState(null)
  const [viewRev, setViewRev] = useState(null) // { revision, title, content }

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

  const loadContent = useCallback(async () => {
    try {
      const { data } = await api.get(`/documents/${id}/content`)
      setContent(data.content || '')
    } catch (e) {
      setContent('')
      flash(errMsg(e))
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  // 切到「原文」时按需拉取全文（大文本不在首屏加载）
  useEffect(() => {
    if (tab === 'content' && content === null && doc?.status === 'ready') {
      loadContent()
    }
  }, [tab, content, doc, loadContent])

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

  const startEdit = () => {
    setDraft(content || '')
    setEditing(true)
  }

  const saveEdit = async () => {
    if (!draft.trim()) return flash('正文不能为空')
    setSaving(true)
    try {
      const { data } = await api.put(`/documents/${id}`, { content: draft })
      setDoc(data)
      setContent(draft)
      setTab('content')
      setEditing(false)
      flash(`已保存，v${data.revision} · 正在重建索引`)
      const c = await api.get(`/documents/${id}/chunks`)
      setChunks(c.data)
    } catch (e) {
      flash(errMsg(e))
    } finally {
      setSaving(false)
    }
  }

  const openRevisions = async () => {
    try {
      const { data } = await api.get(`/documents/${id}/revisions`)
      setRevisions(data)
    } catch (e) {
      flash(errMsg(e))
    }
  }

  const viewRevision = async (revId) => {
    try {
      const { data } = await api.get(`/documents/${id}/revisions/${revId}`)
      setViewRev({ ...data, rev_id: revId })
    } catch (e) {
      flash(errMsg(e))
    }
  }

  const restoreRevision = async (revId) => {
    if (!confirm('回滚到该版本？当前内容会先存为一个新版本，可再切回。')) return
    setSaving(true)
    try {
      const { data } = await api.post(`/documents/${id}/revisions/${revId}/restore`)
      setDoc(data)
      setViewRev(null)
      setRevisions(null)
      setContent(null)
      await load()
      await loadContent()
      flash(`已回滚到 v${data.revision}`)
    } catch (e) {
      flash(errMsg(e))
    } finally {
      setSaving(false)
    }
  }

  const reindex = async () => {
    setBusy(true)
    try {
      await api.post(`/documents/${id}/reindex`)
      flash('已重建索引')
      setContent(null)
      await load()
      await loadContent()
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

  // 打开原始文件：经带 token 的请求取回 blob（PDF 可内嵌预览，Word/TXT 下载）
  const openRaw = async () => {
    try {
      const res = await api.get(`/documents/${id}/raw`, { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      window.open(url, '_blank')
      setTimeout(() => URL.revokeObjectURL(url), 60000)
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
                <span className="doc-ver">v{doc.revision || 1}</span>
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
              <span>· {timeAgo(doc.edited_at || doc.created_at)}</span>
            </div>
            {doc.error && <div className="alert">{doc.error}</div>}
          </div>
        </div>

        <div className="doc-head-actions">
          <button className="btn action ai-ask-btn" onClick={ask} disabled={doc.status !== 'ready'}>
            ✦ 问问 AI
          </button>
          {mine && !editing && (
            <button className="btn primary" onClick={startEdit} disabled={doc.status !== 'ready'}>
              编辑正文
            </button>
          )}
          <button className="btn ghost" onClick={openRevisions}>
            版本历史
          </button>
          <button className="btn ghost" onClick={openRaw}>
            查看原文件
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

      {editing ? (
        <div className="doc-editor">
          <div className="editor-bar">
            <strong>编辑正文</strong>
            <span className="editor-hint">
              保存后会重新分块并重建向量，AI 立即用新内容作答。原始文件（{doc.original_name || doc.doc_type}）不受影响。
            </span>
            <div className="editor-actions">
              <button className="btn primary" onClick={saveEdit} disabled={saving}>
                {saving ? '保存中…' : '保存'}
              </button>
              <button className="btn ghost" onClick={() => setEditing(false)} disabled={saving}>
                取消
              </button>
            </div>
          </div>
          <textarea
            className="editor-area"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            spellCheck={false}
          />
          <div className="editor-foot">
            共 {num(draft.length)} 字 · 可用空行分段，AI 会按段落切分
          </div>
        </div>
      ) : (
        <>
          <div className="doc-tabs">
            <button
              className={`tab-btn${tab === 'content' ? ' active' : ''}`}
              onClick={() => setTab('content')}
            >
              原文
            </button>
            <button
              className={`tab-btn${tab === 'chunks' ? ' active' : ''}`}
              onClick={() => setTab('chunks')}
            >
              分块（{chunks.length}）
              <span className="tab-hint" title="分块是喂给 AI 检索的片段，普通阅读请用「原文」">
                ?
              </span>
            </button>
          </div>

          {tab === 'content' ? (
            doc.status !== 'ready' ? (
              <div className="empty">文档尚未就绪，暂无正文。</div>
            ) : content === null ? (
              <div className="page-loading">正在加载原文…</div>
            ) : content ? (
              <article className="doc-content">{content}</article>
            ) : (
              <div className="empty">未能提取到正文内容。</div>
            )
          ) : chunks.length === 0 ? (
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
        </>
      )}

      {revisions !== null && (
        <div className="modal-mask" onClick={() => setRevisions(null)}>
          <div className="modal-card wide" onClick={(e) => e.stopPropagation()}>
            <h3>版本历史</h3>
            <p className="modal-text">当前为 <strong>v{doc.revision || 1}</strong>。每条记录是编辑前的快照，可查看原文或回滚。</p>
            {revisions.length === 0 ? (
              <div className="empty">还没有历史版本（首次编辑后才会产生）。</div>
            ) : (
              <ul className="rev-list">
                {revisions.map((r) => (
                  <li key={r.id} className="rev-item">
                    <div>
                      <strong>v{r.revision_no}</strong>
                      <span className="rev-meta">
                        · {r.title} · {num(r.char_count)} 字 · {timeAgo(r.created_at)}
                      </span>
                    </div>
                    <div className="rev-actions">
                      <button className="btn ghost" onClick={() => viewRevision(r.id)}>
                        查看
                      </button>
                      {mine && (
                        <button className="btn primary" onClick={() => restoreRevision(r.id)}>
                          回滚
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <div className="modal-actions">
              <button className="btn ghost" onClick={() => setRevisions(null)}>
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {viewRev && (
        <div className="modal-mask" onClick={() => setViewRev(null)}>
          <div className="modal-card wide" onClick={(e) => e.stopPropagation()}>
            <h3>v{viewRev.revision} · {viewRev.title}</h3>
            <pre className="rev-content">{viewRev.content}</pre>
            <div className="modal-actions">
              {mine && viewRev.rev_id && (
                <button className="btn primary" onClick={() => restoreRevision(viewRev.rev_id)}>
                  回滚到此版本
                </button>
              )}
              <button className="btn ghost" onClick={() => setViewRev(null)}>
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
