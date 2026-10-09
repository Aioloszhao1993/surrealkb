import { Link } from 'react-router-dom'
import { num, timeAgo } from './format'
import Avatar from './Avatar'
import HoverUser from './UserHoverCard'

export default function VideoCard({ video }) {
  return (
    <div className="card">
      <Link to={`/watch/${video.id}`} className="card-link">
        <div className="thumb">
          {video.cover ? (
            <img src={`/media/${video.cover}`} alt={video.title} loading="lazy" />
          ) : (
            <div className="thumb-fallback">
              <span>◈</span>
            </div>
          )}
          <div className="thumb-glow" />
          <span className="duration-tag">{timeAgo(video.created_at)}</span>
        </div>
        <h3 className="card-title">{video.title}</h3>
      </Link>
      <div className="card-body">
        <p className="card-desc">{video.description || '这个梦境没有留下描述…'}</p>
        <div className="card-meta">
          <HoverUser user={video.owner}>
            <Link to={`/user/${video.owner.id}`} className="card-owner">
              <Avatar user={video.owner} size="sm" />
              <span className="owner">{video.owner.username}</span>
            </Link>
          </HoverUser>
          <span className="sep" />
          <span>▶ {num(video.views)}</span>
          <span>♥ {num(video.likes)}</span>
          <span>★ {num(video.favorites)}</span>
        </div>
      </div>
    </div>
  )
}
