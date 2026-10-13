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

export default function Home() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ items: [], total: 0, page_size: 12 })
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/documents', {
        params: { q: q || undefined, status: status || undefined, page },
      })
      setData(data)
    } catch {
      setData({ items: [], total: 0, page_size: 12 })
    } finally {
      setLoading(false)
    }
  }, [q, status, page])

  useEffect(() => {
    setPage(1)
  }, [q, status])

  useEffect(() => {
    if (!user) {
      setLoading(false)
      return
    }
    load()
  }, [load, user])

  const totalPages = Math.max(1, Math.ceil((data.total || 0) / (data.page_size || 12)))

  return (
    <div className="home">
      <section className="hero">
        <h1>
          把你的文档，变成<span className="accent">会答话</span>的知识库
        </h1>
        <p>上传 PDF / Word / TXT / Markdown，向 AI 提问，答案带原文出处。</p>
        {!user && (
          <div className="hero-cta">
            <Link to="/register" className="btn primary">
              免费创建知识库
            </Link>
            <Link to="/login" className="btn ghost">
              已有账号，登录
            </Link>
          </div>
        )}
      </section>

      {!user ? (
        <div className="empty">登录后即可查看和管理你知识库中的文档。</div>
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

          {loading ? (
            <div className="grid">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="skeleton" />
              ))}
            </div>
          ) : data.items.length === 0 ? (
            <div className="empty">
              知识库里还没有文档。
              <Link to="/upload" className="link">
                上传第一篇 ↗
              </Link>
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
