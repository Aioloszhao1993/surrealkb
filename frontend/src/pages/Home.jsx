import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import api from '../api'
import DocCard from '../components/DocCard'
import { useAuth } from '../store'

const STATUS_TABS = [
  { key: '', label: '全部' },
  { key: 'ready', label: '已就绪' },
  { key: 'pending', label: '处理中' },
  { key: 'failed', label: '失败' },
]

// hero 下方展示的支持格式（格式清单只在这里出现一处，避免和能力卡片重复）
const FORMATS = ['PDF', 'Word (.docx)', 'TXT', 'Markdown']

// 未登录时的能力介绍（首页留白填充，同时替代营销文案）
const FEATURES = [
  {
    icon: '⇪',
    title: '上传即用',
    desc: '拖进来就行，自动识别标题与正文结构，不用先手工整理。',
  },
  {
    icon: '◈',
    title: '自动建索引',
    desc: '系统自动解析正文、切分片段并建立向量索引，几秒后就能检索。',
  },
  {
    icon: '✦',
    title: '问答带出处',
    desc: '向 AI 提问，答案附带原文出处，点一下即可跳回原文对应位置。',
  },
]

const STEPS = [
  { title: '上传文档', desc: '拖拽或点选，单份不超过 50MB' },
  { title: '自动处理', desc: '解析正文 → 切分片段 → 建立索引' },
  { title: '提问取答案', desc: '点右下角 ✦ 提问，答案带回原文出处' },
]

export default function Home() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const tag = params.get('tag') || ''
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [tags, setTags] = useState([])
  const [data, setData] = useState({ items: [], total: 0, page_size: 12 })
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/documents', {
        params: { q: q || undefined, status: status || undefined, tag: tag || undefined, page },
      })
      setData(data)
    } catch {
      setData({ items: [], total: 0, page_size: 12 })
    } finally {
      setLoading(false)
    }
  }, [q, status, tag, page])

  const loadTags = useCallback(async () => {
    if (!user) return
    try {
      const { data } = await api.get('/documents/tags')
      setTags(data.items || [])
    } catch {
      setTags([])
    }
  }, [user])

  useEffect(() => {
    setPage(1)
  }, [q, status, tag])

  useEffect(() => {
    if (!user) {
      setLoading(false)
      return
    }
    load()
  }, [load, user])

  useEffect(() => {
    loadTags()
  }, [loadTags])

  const totalPages = Math.max(1, Math.ceil((data.total || 0) / (data.page_size || 12)))

  return (
    <div className="home">
      <section className="hero">
        <span className="hero-badge">个人知识库 · 上传即用 · 无需配置</span>
        <h1>
          把你的文档，变成<span className="accent">会答话</span>的知识库
        </h1>
        <p>上传你的文档，向它提问 —— 每个答案都标注原文出处。</p>
        <ul className="hero-formats">
          {FORMATS.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      </section>

      {!user ? (
        <>
          <section className="features">
            {FEATURES.map((f) => (
              <article className="feature-card" key={f.title}>
                <div className="feature-icon" aria-hidden="true">
                  {f.icon}
                </div>
                <h3 className="feature-title">{f.title}</h3>
                <p className="feature-desc">{f.desc}</p>
              </article>
            ))}
          </section>

          <section className="howto">
            <h2 className="howto-title">三步用起来</h2>
            <ol className="howto-list">
              {STEPS.map((s, i) => (
                <li className="howto-item" key={s.title}>
                  <span className="howto-num" aria-hidden="true">
                    {i + 1}
                  </span>
                  <span className="howto-text">
                    <strong>{s.title}</strong>
                    <em>{s.desc}</em>
                  </span>
                </li>
              ))}
            </ol>
          </section>
        </>
      ) : (
        <>
          <div className="toolbar">
            <div className="tabs">
              {STATUS_TABS.map((t) => (
                <button
                  key={t.key}
                  className={status === t.key ? 'tab active' : 'tab'}
                  onClick={() => setStatus(t.key)}
                >
                  {t.label}
                </button>
              ))}
            </div>
            {q && (
              <div className="search-hint">
                “{q}” 的搜索结果
                <button className="link" onClick={() => setParams({})}>
                  清除
                </button>
              </div>
            )}
            <span className="count">共 {data.total} 篇文档</span>
          </div>

          {tags.length > 0 && (
            <div className="tag-bar">
              <span className="tag-bar-label">标签</span>
              <button
                className={`tag-chip${!tag ? ' active' : ''}`}
                onClick={() => setParams((p) => { p.delete('tag'); return p })}
              >
                全部
              </button>
              {tags.map((t) => (
                <button
                  key={t.tag}
                  className={`tag-chip${tag === t.tag ? ' active' : ''}`}
                  onClick={() =>
                    setParams((p) => {
                      p.set('tag', t.tag)
                      return p
                    })
                  }
                >
                  #{t.tag}
                  <em>{t.count}</em>
                </button>
              ))}
            </div>
          )}

          {loading ? (
            <div className="grid">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="skeleton" />
              ))}
            </div>
          ) : data.items.length === 0 ? (
            <div className="empty">
              {q || tag ? (
                <>
                  没有找到匹配的文档。
                  <button className="link" onClick={() => setParams({})}>
                    清除筛选
                  </button>
                </>
              ) : (
                <div className="onboard-card">
                  <div className="onboard-icon" aria-hidden="true">
                    ⇪
                  </div>
                  <div className="onboard-title">知识库还是空的</div>
                  <p className="onboard-desc">
                    上传第一份文档，系统会自动解析正文、切分片段并建立索引，随后你就能向它提问了。
                  </p>
                  <Link to="/upload" className="btn primary">
                    上传第一份文档
                  </Link>
                  <p className="onboard-hint">
                    支持 PDF / Word(.docx) / TXT / Markdown，单份不超过 50MB
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div className="grid">
              {data.items.map((d) => (
                <DocCard key={d.id} doc={d} />
              ))}
            </div>
          )}

          {totalPages > 1 && (
            <div className="pager">
              <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                上一页
              </button>
              <span>
                {page} / {totalPages}
              </span>
              <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                下一页
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
