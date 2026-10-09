import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api, { errMsg } from '../api'

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
  content: '你好，我是 Friday 🌙 SurrealVideo 的 AI 助手。\n可以问我「站里有什么视频」「帮我找讲 XX 的视频」，或者随便聊两句。',
}

export default function AiChat() {
  const [open, setOpen] = useState(false)
  const [enabled, setEnabled] = useState(true)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [msgs, setMsgs] = useState([WELCOME])
  const boxRef = useRef(null)
  const sessionKey = useRef(getSessionKey())

  // 探测后端 AI 是否可用；不可用则不显示入口
  useEffect(() => {
    api
      .get('/ai/status')
      .then(({ data }) => setEnabled(!!data.enabled))
      .catch(() => setEnabled(false))
  }, [])

  // 其他页面可通过 window.dispatchEvent(new CustomEvent('ai-ask', {detail: '...'})) 唤起并提问
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

  // 打开时拉取历史
  useEffect(() => {
    if (!open) return
    api
      .get(`/ai/history/${sessionKey.current}`)
      .then(({ data }) => {
        if (data.items?.length) {
          setMsgs([WELCOME, ...data.items.map((m) => ({ role: m.role, content: m.content }))])
        }
      })
      .catch(() => {})
  }, [open])

  useEffect(() => {
    const el = boxRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [msgs, busy, open])

  const ask = async (q) => {
    const text = (q || '').trim()
    if (!text || busy) return
    setMsgs((m) => [...m, { role: 'user', content: text }])
    setBusy(true)
    try {
      const { data } = await api.post('/ai/chat', { question: text, session_key: sessionKey.current })
      setMsgs((m) => [...m, { role: 'assistant', content: data.answer, sources: data.sources }])
    } catch (e) {
      setMsgs((m) => [...m, { role: 'assistant', content: '⚠️ ' + errMsg(e), error: true }])
    } finally {
      setBusy(false)
    }
  }

  const send = async () => {
    const q = input.trim()
    if (!q || busy) return
    setInput('')
    await ask(q)
  }

  const clear = async () => {
    try {
      await api.delete(`/ai/history/${sessionKey.current}`)
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
        onClick={() => setOpen((v) => !v)}
        title="AI 助手"
        aria-label="AI 助手"
      >
        {open ? '✕' : '✦'}
      </button>

      {open && (
        <div className="ai-panel">
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
                <div className="ai-bubble">{m.content}</div>
                {m.sources?.length > 0 && (
                  <div className="ai-sources">
                    {m.sources.map((s) => (
                      <Link key={s.id} to={`/watch/${s.id}`} className="ai-source" onClick={() => setOpen(false)}>
                        ▶ {s.title}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {busy && (
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
              placeholder="问点什么…（Enter 发送）"
              disabled={busy}
            />
            <button onClick={send} disabled={busy || !input.trim()}>
              发送
            </button>
          </div>
        </div>
      )}
    </>
  )
}
