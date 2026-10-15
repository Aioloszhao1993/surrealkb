import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api, { errMsg } from '../api'
import useClickOutside from '../useClickOutside'
import { useAuth } from '../store'

const SESSION_KEY = 'ai_session_key'

function getSessionKey() {
  let k = localStorage.getItem(SESSION_KEY)
  if (!k) {
    k = 'web_' + Math.random().toString(36).slice(2) + Date.now().toString(36)
    localStorage.setItem(SESSION_KEY, k)
  }
  return k
}

const WELCOME = {
  role: 'assistant',
  content:
    '你好，我是 Friday 🌙 你的知识库 AI 助手。\n基于你上传的文档提问，我会给出带原文出处的回答。试试「报销标准是什么」之类的问题吧。',
}

// 用 fetch + ReadableStream 解析后端 SSE（axios 不便做浏览器流式）
async function streamChat({ question, sessionKey, onSources, onDelta, signal }) {
  const token = localStorage.getItem('token')
  const res = await fetch('/api/ai/chat?stream=true', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      'X-Session-Key': sessionKey,
    },
    body: JSON.stringify({ question }),
    signal,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const j = await res.json()
      detail = j.detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  let event = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const parts = buf.split('\n\n')
    buf = parts.pop()
    for (const block of parts) {
      const lines = block.split('\n')
      let data = ''
      for (const ln of lines) {
        if (ln.startsWith('event:')) event = ln.slice(6).trim()
        else if (ln.startsWith('data:')) data += ln.slice(5).trim()
      }
      if (!data) continue
      let obj
      try {
        obj = JSON.parse(data)
      } catch {
        continue
      }
      if (event === 'sources') onSources(obj.sources || [])
      else if (event === 'delta') onDelta(obj)
      else if (event === 'error') throw new Error(obj.detail || 'AI 出错')
    }
  }
}

export default function AiChat() {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [enabled, setEnabled] = useState(true)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [msgs, setMsgs] = useState([WELCOME])
  const boxRef = useRef(null)
  const fabRef = useRef(null)
  const panelRef = useRef(null)
  const sessionKey = useRef(getSessionKey())
  const abortRef = useRef(null)

  // 面板保持常驻悬浮形态（不遮挡页面），但点页面其他地方的空白处即收起。
  // 悬浮按钮本身要排除在「外部」之外，否则会和它自己的 toggle 打架。
  useClickOutside([fabRef, panelRef], () => setOpen(false), open)

  const skHeaders = () => ({ headers: { 'X-Session-Key': sessionKey.current } })

  useEffect(() => {
    api
      .get('/ai/status')
      .then(({ data }) => setEnabled(!!data.enabled))
      .catch(() => setEnabled(false))
  }, [])

  useEffect(() => {
    const onAsk = (e) => {
      const q = e?.detail
      if (!q) return
      setOpen(true)
      ask(q)
    }
    window.addEventListener('ai-ask', onAsk)
    return () => window.removeEventListener('ai-ask', onAsk)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy])

  useEffect(() => {
    if (!open || !user) return
    api
      .get('/ai/history', skHeaders())
      .then(({ data }) => {
        if (data.items?.length) {
          setMsgs([WELCOME, ...data.items.map((m) => ({ role: m.role, content: m.content }))])
        }
      })
      .catch(() => {})
  }, [open, user])

  useEffect(() => {
    const el = boxRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [msgs, busy, open])

  const ask = async (q) => {
    const text = (q || '').trim()
    if (!text || busy) return
    if (!user) {
      setOpen(true)
      setMsgs((m) => [
        ...m,
        { role: 'user', content: text },
        { role: 'assistant', content: '请先登录后再使用 AI 助手（可在右上角登录）。', error: true },
      ])
      return
    }
    setMsgs((m) => [...m, { role: 'user', content: text }, { role: 'assistant', content: '', streaming: true }])
    setBusy(true)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    try {
      await streamChat({
        question: text,
        sessionKey: sessionKey.current,
        signal: ctrl.signal,
        onSources: (sources) =>
          setMsgs((m) => {
            const copy = m.slice()
            copy[copy.length - 1] = { ...copy[copy.length - 1], sources }
            return copy
          }),
        onDelta: (chunk) =>
          setMsgs((m) => {
            const copy = m.slice()
            const last = copy[copy.length - 1]
            copy[copy.length - 1] = { ...last, content: (last.content || '') + chunk }
            return copy
          }),
      })
      setMsgs((m) => {
        const copy = m.slice()
        const last = copy[copy.length - 1]
        copy[copy.length - 1] = { ...last, streaming: false }
        return copy
      })
    } catch (e) {
      if (e?.name === 'AbortError') {
        setMsgs((m) => m) // 已停止，保留已生成内容
      } else {
        setMsgs((m) => [...m, { role: 'assistant', content: '⚠️ ' + (e?.message || errMsg(e)), error: true }])
      }
    } finally {
      setBusy(false)
      abortRef.current = null
    }
  }

  const stop = () => {
    abortRef.current?.abort()
    setBusy(false)
  }

  const send = async () => {
    const q = input.trim()
    if (!q || busy) return
    setInput('')
    await ask(q)
  }

  const clear = async () => {
    try {
      await api.delete('/ai/history', skHeaders())
    } catch {
      /* ignore */
    }
    setMsgs([WELCOME])
  }

  if (!enabled) return null

  return (
    <>
      <button
        className={'ai-fab' + (open ? ' active' : '')}
        ref={fabRef}
        onClick={() => setOpen((v) => !v)}
        title="AI 助手"
        aria-label="AI 助手"
      >
        {open ? '✕' : '✦'}
      </button>

      {open && (
        <div className="ai-panel" ref={panelRef}>
          <div className="ai-head">
            <div className="ai-title">
              <span className="ai-dot" />
              Friday · AI 助手
            </div>
            <div className="ai-head-actions">
              <button onClick={clear} title="清空对话">
                清空
              </button>
              <button onClick={() => setOpen(false)} title="收起">
                ▾
              </button>
            </div>
          </div>

          <div className="ai-body" ref={boxRef}>
            {msgs.map((m, i) => (
              <div key={i} className={'ai-msg ' + m.role + (m.error ? ' err' : '')}>
                <div className="ai-bubble">
                  {m.content}
                  {m.streaming && <span className="ai-caret" />}
                </div>
                {m.sources?.length > 0 && (
                  <div className="ai-sources">
                    {m.sources.map((s, si) => (
                      <Link
                        key={si}
                        to={`/doc/${s.document_id}?hl=${encodeURIComponent(
                          s.anchor || s.snippet || ''
                        )}&seq=${s.seq ?? ''}`}
                        className="ai-source"
                        onClick={() => setOpen(false)}
                        title={s.snippet}
                      >
                        📄 {s.title}
                        {s.seq != null && <span className="ai-seq">第{s.seq + 1}段</span>}
                        <span className="ai-score">{(s.score * 100).toFixed(0)}%</span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {busy && !msgs[msgs.length - 1]?.content && (
              <div className="ai-msg assistant">
                <div className="ai-bubble ai-typing">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}
          </div>

          <div className="ai-input">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && send()}
              placeholder="基于知识库提问…（Enter 发送）"
              disabled={busy}
            />
            {busy ? (
              <button onClick={stop}>停止</button>
            ) : (
              <button onClick={send} disabled={!input.trim()}>
                发送
              </button>
            )}
          </div>
        </div>
      )}
    </>
  )
}
