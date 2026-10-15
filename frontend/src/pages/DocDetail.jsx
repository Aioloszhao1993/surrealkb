import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import api, { errMsg } from '../api'
import { num, timeAgo } from '../components/format'
import Avatar from '../components/Avatar'
import HoverUser from '../components/UserHoverCard'
import RichPreview from '../components/RichPreview'
import RichTextEditor from '../components/RichTextEditor'
import portal from '../components/Portal'
import useClickOutside from '../useClickOutside'
import { useAuth } from '../store'

const STATUS_LABEL = { ready: '已就绪', pending: '处理中', failed: '处理失败' }

// 引用定位：把命中锚点在原文里高亮
// anchor 来自后端，是「去空白后的字符序列」；用「字符间允许任意空白」的正则
// 在原文里匹配，容忍分块 normalize 与原文换行的差异。
function findAnchor(text, anchor) {
  if (!anchor) return null
  const chars = Array.from(anchor).filter((c) => !/\s/.test(c))
  if (!chars.length) return null
  const esc = (c) => c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const pat = new RegExp(chars.map(esc).join('\\s*'))
  const m = pat.exec(text)
  if (!m) return null
  return { start: m.index, end: m.index + m[0].length }
}

function HighlightedContent({ text, kw }) {
  if (!kw) return text
  const hit = findAnchor(text, kw)
  if (!hit) return text
  return (
    <>
      {text.slice(0, hit.start)}
      <mark className="hl">{text.slice(hit.start, hit.end)}</mark>
      {text.slice(hit.end)}
    </>
  )
}

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
  const [params] = useSearchParams()
  const hl = params.get('hl') || '' // 引用定位：原文中的锚点片段（精准定位用）
  const jumpSeq = params.get('seq') // 引用定位：分块序号（回退定位用）
  const [doc, setDoc] = useState(null)
  const [chunks, setChunks] = useState([])
  const [content, setContent] = useState(null) // 提取出的纯文本全文
  const [tab, setTab] = useState('rich') // rich | content | chunks
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [busy, setBusy] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [title, setTitle] = useState('')
  const [tagInput, setTagInput] = useState('')
  const [editTags, setEditTags] = useState(false)

  // 在线编辑
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  // 版本历史
  const [revisions, setRevisions] = useState(null)
  const [viewRev, setViewRev] = useState(null) // { revision, title, content }
  const [showDl, setShowDl] = useState(false) // 「下载当前版本」格式菜单
  const dlWrapRef = useRef(null)

  // 下载格式菜单：点击空白处关闭
  useClickOutside(dlWrapRef, () => setShowDl(false), showDl)

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
      const text = data.content || ''
      setContent(text)
      return text
    } catch (e) {
      setContent('')
      flash(errMsg(e))
      return ''
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  // 引用定位：带锚点/段号从 AI 出处跳进来时，自动切到「原文」视图并高亮
  useEffect(() => {
    if (!doc) return
    if (hl || (jumpSeq !== null && jumpSeq !== '')) setTab('content')
  }, [doc, jumpSeq, hl])

  // 原文加载完成后，把命中位置滚动到视口中间
  useEffect(() => {
    if (tab !== 'content' || content === null || !hl) return
    const t = setTimeout(() => {
      const el = document.querySelector('.doc-content mark.hl')
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 200)
    return () => clearTimeout(t)
  }, [tab, content, hl])

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

  const saveTags = async (next) => {
    try {
      const { data } = await api.patch(`/documents/${id}`, { tags: next })
      setDoc(data)
      setTagInput('')
      setEditTags(false)
      flash('标签已更新')
    } catch (e) {
      flash(errMsg(e))
    }
  }

  const startEdit = async () => {
    // 无论哪种格式，先把当前正文加载进来（此前只在 docx 分支里加载，非 Word 文档会打开空编辑器）
    let md = content
    if (md === null) md = await loadContent()
    if (!md) md = ''

    // 首次编辑 Word：把原始文档还原为 Markdown（标题/列表/表格），让编辑器就是「原文的样子」
    if (doc.doc_type === 'docx' && (doc.revision || 1) === 1) {
      try {
        const res = await api.get(`/documents/${id}/raw`, { responseType: 'blob' })
        const mammoth = (await import('mammoth')).default
        const { value: html } = await mammoth.convertToHtml({
          arrayBuffer: await res.data.arrayBuffer(),
        })
        // 去掉 mammoth 由表格单元格「下边框」生成的水平分割线段落（会把表格拆散）
        const cleaned = html.replace(/<p>\s*<hr\s*\/?>\s*<\/p>/gi, '')
        const TurndownMod = await import('turndown')
        const td = new TurndownMod.default({
          headingStyle: 'atx',
          codeBlockStyle: 'fenced',
          bulletListMarker: '-',
        })
        // 表格原样保留为 HTML（保真优先）
        td.keep(['table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption'])
        td.addRule('dropImage', { filter: 'img', replacement: () => '' })
        const converted = td.turndown(cleaned)
        if (converted.trim()) md = converted
      } catch {
        /* 转换失败则退回纯文本 */
      }
    }
    if (!md.trim()) flash('未提取到正文，可直接在这里输入')
    setDraft(md)
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

  // 打开/下载原始文件：经带 token 的请求取回 blob
  const openRaw = async () => {
    try {
      const res = await api.get(`/documents/${id}/raw`, { responseType: 'blob' })
      const blob = res.data
      // 原始文件名：以下载响应头为准，回退到文档记录里的 original_name
      const cd = res.headers?.['content-disposition'] || ''
      let name = doc.original_name || doc.filename || `${doc.title}.${doc.doc_type}`
      const m = cd.match(/filename\*=UTF-8''([^;]+)/i)
      if (m) {
        try {
          name = decodeURIComponent(m[1])
        } catch {
          /* 保留回退名 */
        }
      }
      const url = URL.createObjectURL(blob)
      if (doc.doc_type === 'pdf') {
        // PDF 用浏览器原生阅读器内嵌预览（blob 无文件名无妨）
        window.open(url, '_blank')
      } else {
        // 其余格式触发下载，并用 <a download> 显式指定原文件名（window.open 会丢掉文件名）
        const a = document.createElement('a')
        a.href = url
        a.download = name
        document.body.appendChild(a)
        a.click()
        a.remove()
      }
      setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (e) {
      flash(errMsg(e))
    }
  }

  // 下载当前版本：按指定格式导出，文件名 = 原文件名(V版本号).ext
  const downloadVersion = async (fmt = 'md') => {
    try {
      const res = await api.get(`/documents/${id}/export`, {
        params: { format: fmt },
        responseType: 'blob',
      })
      const cd = res.headers?.['content-disposition'] || ''
      let name = `${doc.title}(V${doc.revision || 1}).${fmt}`
      const m = cd.match(/filename\*=UTF-8''([^;]+)/i)
      if (m) {
        try {
          name = decodeURIComponent(m[1])
        } catch {
          /* 保留默认名 */
        }
      }
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = name
      document.body.appendChild(a)
      a.click()
      a.remove()
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
            <div className="doc-tags">
              {(doc.tags || []).map((t) => (
                <Link key={t} to={`/?tag=${encodeURIComponent(t)}`} className="doc-tag">
                  #{t}
                </Link>
              ))}
              {mine && (
                editTags ? (
                  <span className="tag-edit">
                    <input
                      value={tagInput}
                      autoFocus
                      placeholder="逗号分隔，如 合同,制度"
                      onChange={(e) => setTagInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveTags(tagInput.split(/[,,]/).map((s) => s.trim()).filter(Boolean))
                        if (e.key === 'Escape') setEditTags(false)
                      }}
                    />
                    <button
                      className="link"
                      onClick={() =>
                        saveTags(tagInput.split(/[,,]/).map((s) => s.trim()).filter(Boolean))
                      }
                    >
                      保存
                    </button>
                    <button className="link" onClick={() => setEditTags(false)}>
                      取消
                    </button>
                  </span>
                ) : (
                  <button className="link tag-add" onClick={() => { setTagInput((doc.tags || []).join(',')); setEditTags(true) }}>
                    + 添加标签
                  </button>
                )
              )}
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
            {doc.doc_type === 'pdf' ? '预览原文件' : '下载原文件'}
          </button>
          {mine && (
            <>
              <button className="btn ghost" onClick={reindex} disabled={busy}>
                {busy ? '重建中…' : '重建索引'}
              </button>
              <div className="dl-wrap" ref={dlWrapRef} onMouseLeave={() => setShowDl(false)}>
                <button className="btn ghost" onClick={() => setShowDl((v) => !v)}>
                  下载当前版本 ▾
                </button>
                {showDl && (
                  <div className="dl-menu">
                    <button onClick={() => { setShowDl(false); downloadVersion('docx') }}>Word 文档 (.docx)</button>
                    <button onClick={() => { setShowDl(false); downloadVersion('pdf') }}>PDF 文档 (.pdf)</button>
                    <button onClick={() => { setShowDl(false); downloadVersion('md') }}>Markdown (.md)</button>
                    <button onClick={() => { setShowDl(false); downloadVersion('txt') }}>纯文本 (.txt)</button>
                  </div>
                )}
              </div>
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

          <RichTextEditor
            value={draft}
            onChange={setDraft}
            placeholder="直接在这里编辑，支持标题 / 列表 / 表格 / 加粗…"
          />
          <div className="editor-foot">
            共 {num(draft.length)} 字 · 富文本所见即所得，尽量还原原文件的标题 / 列表 / 表格样式
          </div>
        </div>
      ) : (
        <>
          <div className="doc-tabs">
            <button
              className={`tab-btn${tab === 'rich' ? ' active' : ''}`}
              onClick={() => setTab('rich')}
            >
              原文样式
              <span className="tab-hint" title="尽量还原上传文件原本的排版（Word/Markdown/PDF）">
                ?
              </span>
            </button>
            <button
              className={`tab-btn${tab === 'content' ? ' active' : ''}`}
              onClick={() => setTab('content')}
            >
              纯文本
            </button>
            <button
              className={`tab-btn${tab === 'chunks' ? ' active' : ''}`}
              onClick={() => setTab('chunks')}
            >
              分块（{chunks.length}）
              <span className="tab-hint" title="分块是喂给 AI 检索的片段，普通阅读请用「原文样式」">
                ?
              </span>
            </button>
          </div>

          {tab === 'rich' ? (
            doc.status !== 'ready' ? (
              <div className="empty">文档尚未就绪，暂无预览。</div>
            ) : (
              <RichPreview doc={doc} />
            )
          ) : tab === 'content' ? (
            doc.status !== 'ready' ? (
              <div className="empty">文档尚未就绪，暂无正文。</div>
            ) : content === null ? (
              <div className="page-loading">正在加载原文…</div>
            ) : content ? (
              <article className="doc-content">
                {hl ? <HighlightedContent text={content} kw={hl} /> : content}
              </article>
            ) : (
              <div className="empty">未能提取到正文内容。</div>
            )
          ) : chunks.length === 0 ? (
            <div className="empty">这篇文档还没有分块内容。</div>
          ) : (
            <div className="chunk-list">
              {chunks.map((c) => (
                <div
                  key={c.id}
                  className={'chunk-item' + (String(c.seq) === String(jumpSeq) ? ' chunk-target' : '')}
                  data-chunk-seq={c.seq}
                >
                  <span className="chunk-seq">#{c.seq + 1}</span>
                  <p className="chunk-text">
                    {String(c.seq) === String(jumpSeq) && hl ? <HighlightedContent text={c.content} kw={hl} /> : c.content}
                  </p>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {revisions !== null && portal(
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

      {viewRev && portal(
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
