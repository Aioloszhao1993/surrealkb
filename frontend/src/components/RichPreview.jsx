import { useEffect, useState } from 'react'
import api, { errMsg } from '../api'

/**
 * 富文本预览：尽量还原文档「原来的样子」。
 * - Word(.docx)：mammoth 转 HTML（保留标题/列表/表格/加粗等），浏览器内渲染
 * - Markdown：轻量渲染标题/列表/加粗/代码
 * - PDF：<iframe> 内嵌浏览器自带阅读器
 * - TXT：等宽纯文本
 * 原始文件经带 token 的请求取回（blob），不暴露静态路径。
 */
export default function RichPreview({ doc }) {
  const [state, setState] = useState({ loading: true, kind: null, html: null, text: null, note: null })
  const type = (doc?.doc_type || '').toLowerCase()

  useEffect(() => {
    let alive = true
    let objUrl = null
    setState({ loading: true, kind: null, html: null, text: null, note: null })

    ;(async () => {
      try {
        const res = await api.get(`/documents/${doc.id}/raw`, { responseType: 'blob' })
        const blob = res.data
        if (!alive) return

        if (type === 'docx') {
          const arrayBuffer = await blob.arrayBuffer()
          // 按需加载 mammoth（~400KB），只有预览 Word 时才拉取
          const mammoth = (await import('mammoth')).default
          const result = await mammoth.convertToHtml({ arrayBuffer })
          if (!alive) return
          const note = result.messages?.length
            ? result.messages.map((m) => m.message).slice(0, 3).join('；')
            : null
          setState({ loading: false, kind: 'html', html: result.value || '', note })
        } else if (type === 'md' || type === 'markdown') {
          const text = await blob.text()
          if (!alive) return
          setState({ loading: false, kind: 'html', html: mdToHtml(text), note: null })
        } else if (type === 'pdf') {
          objUrl = URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }))
          if (!alive) return
          setState({ loading: false, kind: 'pdf', url: objUrl, note: null })
        } else {
          const text = await blob.text()
          if (!alive) return
          setState({ loading: false, kind: 'text', text, note: null })
        }
      } catch (e) {
        if (alive) setState({ loading: false, kind: 'error', note: errMsg(e) })
      }
    })()

    return () => {
      alive = false
      if (objUrl) URL.revokeObjectURL(objUrl)
    }
  }, [doc?.id, type])

  if (state.loading) return <div className="rich-preview loading">正在还原原文样式…</div>
  if (state.kind === 'error') return <div className="rich-preview empty">{state.note || '预览失败'}</div>

  return (
    <div className="rich-preview">
      {state.note && <div className="rich-note">提示：{state.note}</div>}
      {state.kind === 'html' && (
        <div className="rich-doc" dangerouslySetInnerHTML={{ __html: state.html }} />
      )}
      {state.kind === 'pdf' && (
        <iframe className="rich-pdf" title="PDF 预览" src={state.url} />
      )}
      {state.kind === 'text' && <pre className="rich-text">{state.text}</pre>}
    </div>
  )
}

// 极简 Markdown → HTML（标题/列表/加粗/行内代码/换行），不引入额外依赖
function mdToHtml(src) {
  const esc = (s) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const inline = (s) =>
    esc(s)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>')

  const out = []
  let inList = false
  for (const raw of src.split(/\r?\n/)) {
    const line = raw.replace(/\s+$/, '')
    const h = line.match(/^(#{1,6})\s+(.*)$/)
    const li = line.match(/^\s*[-*+]\s+(.*)$/)
    if (li) {
      if (!inList) {
        out.push('<ul>')
        inList = true
      }
      out.push(`<li>${inline(li[1])}</li>`)
      continue
    }
    if (inList) {
      out.push('</ul>')
      inList = false
    }
    if (h) out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`)
    else if (line.trim() === '') out.push('')
    else out.push(`<p>${inline(line)}</p>`)
  }
  if (inList) out.push('</ul>')
  return out.join('\n')
}
