import { useEffect, useState } from 'react'
import api from '../api'
import VideoCard from '../components/VideoCard'

export default function Favorites() {
  const [data, setData] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .get('/videos/favorites/me', { params: { page_size: 60 } })
      .then(({ data }) => setData(data))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <h1 className="page-title">我的收藏</h1>
      {loading ? (
        <div className="page-loading">加载中…</div>
      ) : data.items.length === 0 ? (
        <div className="empty">还没有收藏任何梦境。去首页逛逛吧 ↖</div>
      ) : (
        <div className="grid">
          {data.items.map((v) => (
            <VideoCard key={v.id} video={v} />
          ))}
        </div>
      )}
    </div>
  )
}
