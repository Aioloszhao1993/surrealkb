import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../api'
import VideoCard from '../components/VideoCard'

export default function Home() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const [sort, setSort] = useState('new')
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ items: [], total: 0, page_size: 12 })
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/videos', { params: { q: q || undefined, sort, page } })
      setData(data)
    } finally {
      setLoading(false)
    }
  }, [q, sort, page])

  useEffect(() => {
    setPage(1)
  }, [q, sort])

  useEffect(() => {
    load()
  }, [load])

  const totalPages = Math.max(1, Math.ceil((data.total || 0) / (data.page_size || 12)))

  return (
    <div className="home">
      <section className="hero">
        <h1>
          潜入<span className="accent">超现实</span>的影像之海
        </h1>
        <p>上传、点赞、收藏、转发 —— 一个更轻盈的梦境视频站。</p>
      </section>

      <div className="toolbar">
        <div className="tabs">
          <button className={sort === 'new' ? 'tab active' : 'tab'} onClick={() => setSort('new')}>
            最新
          </button>
          <button className={sort === 'hot' ? 'tab active' : 'tab'} onClick={() => setSort('hot')}>
            最热
          </button>
        </div>
        {q && (
          <div className="search-hint">
            “{q}” 的搜索结果
            <button className="link" onClick={() => setParams({})}>
              清除
            </button>
          </div>
        )}
        <span className="count">共 {data.total} 个梦境</span>
      </div>

      {loading ? (
        <div className="grid">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skeleton" />
          ))}
        </div>
      ) : data.items.length === 0 ? (
        <div className="empty">
          这里还没有视频。{q ? '换个关键词试试。' : '成为第一个上传梦境的人吧 ↖'}
        </div>
      ) : (
        <div className="grid">
          {data.items.map((v) => (
            <VideoCard key={v.id} video={v} />
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
    </div>
  )
}
