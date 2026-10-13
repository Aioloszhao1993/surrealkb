import { Link } from 'react-router-dom'
import { num } from './format'

const STATUS_LABEL = { ready: '已就绪', pending: '处理中', failed: '处理失败' }
const TYPE_ICON = { pdf: '📕', docx: '📘', txt: '📄', md: '📝' }

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

export default function DocCard({ doc }) {
  return (
    <div className={'card doc-card status-' + doc.status}>
      <Link to={`/doc/${doc.id}`} className="card-link">
        <div className="doc-icon-wrap">
          <span className="doc-icon">{TYPE_ICON[doc.doc_type] || '📄'}</span>
          <span className={`doc-status ${doc.status}`}>{STATUS_LABEL[doc.status] || doc.status}</span>
          <div className="thumb-glow" />
        </div>
        <h3 className="card-title">{doc.title}</h3>
      </Link>
      <div className="card-body">
        <div className="card-meta doc-meta">
          <span>{doc.doc_type.toUpperCase()}</span>
          <span className="sep" />
          <span>{sizeFmt(doc.size)}</span>
          <span className="sep" />
          <span>{num(doc.chunk_count)} 段</span>
        </div>
      </div>
    </div>
  )
}
