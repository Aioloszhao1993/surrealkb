import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api, { errMsg } from '../api'
import useClickOutside from '../useClickOutside'
import { useAuth } from '../store'

const SESSION_KEY = 'ai_session_key'
/** 悬浮球位置存这里，刷新后还在原处 */
const POS_KEY = 'ai_fab_pos'
/** 悬浮球与视口边缘的最小间距 */
const EDGE = 12
/** 悬浮球与面板之间的间隙 */
const GAP = 12

/**
 * 还没起名（或未登录）时的默认名。用户注册后第一次打开面板会引导改名。
 * ⚠️ 后端 `backend/app/ai_service.py` 的 DEFAULT_AI_NAME 是同一个值的副本 ——
 *    助手自我介绍时用的名字取自服务端（users.ai_name），两边必须一致，
 *    否则会出现「面板叫小知、助手自称 Friday」。
 */
const DEFAULT_AI_NAME = '小知'
/** 名字最长几个字符（后端 UserUpdate.ai_name 同样是 12，两边要一致） */
const MAX_AI_NAME = 12
/** 起名步骤里的快速选择（第一个是默认名） */
const NAME_SUGGESTIONS = ['小知', 'Friday', 'Nova']
/** 输入框里的示例：列出默认名之外的几个建议 */
const NAME_PLACEHOLDER = '例如 小知、Friday…'
/**
 * 触摸设备上不给输入框自动聚焦：唤起软键盘会把面板顶得看不见输入框，
 * 而手机端面板是贴底通栏的。
 */
const CAN_HOVER =
  typeof window !== 'undefined' &&
  !!window.matchMedia &&
  window.matchMedia('(hover: hover)').matches

function getSessionKey() {
  let k = localStorage.getItem(SESSION_KEY)
  if (!k) {
    k = 'web_' + Math.random().toString(36).slice(2) + Date.now().toString(36)
    localStorage.setItem(SESSION_KEY, k)
  }
  return k
}

function loadFabPos() {
  try {
    const p = JSON.parse(localStorage.getItem(POS_KEY) || 'null')
    if (p && typeof p.x === 'number' && typeof p.y === 'number') return p
  } catch {
    /* 坏数据就当作没存过 */
  }
  return null
}

/** 把悬浮球左上角夹在视口内（保证整个球都看得到，不会被拖丢） */
function clampFab(x, y, w, h) {
  const vw = window.innerWidth
  const vh = window.innerHeight
  return {
    x: Math.round(Math.min(Math.max(x, EDGE), Math.max(EDGE, vw - w - EDGE))),
    y: Math.round(Math.min(Math.max(y, EDGE), Math.max(EDGE, vh - h - EDGE))),
  }
}

/**
 * 算面板该摆在哪 —— 悬浮球是被拖过的，面板不能固定贴右下角了。
 *
 * 顺序：
 * 1) 优先上下堆叠：球上方放得下就放上方，否则翻到下方（最自然的观感）
 * 2) 上下都放不下时（面板高 560px，视口只有 700 出头时中段很容易遇到），
 *    改为摆到球的**左右两侧** —— 直接夹到视口内会盖住球，很难看
 * 3) 四周都没地方了才夹进视口（会压住球，所以 .ai-fab 的 z-index 特意高于面板）
 *
 * 面板高宽是固定的（见 .ai-panel 的 width/height），量出来直接算即可。
 */
function placePanel(fabRect, pw, ph) {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const aboveTop = fabRect.top - GAP - ph
  const belowTop = fabRect.bottom + GAP

  if (aboveTop >= EDGE) return { x: alignX(fabRect, pw, vw), y: Math.round(aboveTop) }
  if (belowTop + ph <= vh - EDGE) return { x: alignX(fabRect, pw, vw), y: Math.round(belowTop) }

  // 上下放不下 → 摆到左右两侧，竖直方向尽量与球齐平再夹住
  const y = Math.round(Math.min(Math.max(fabRect.top, EDGE), Math.max(EDGE, vh - ph - EDGE)))
  const rightX = fabRect.right + GAP
  if (rightX + pw <= vw - EDGE) return { x: Math.round(rightX), y }
  const leftX = fabRect.left - GAP - pw
  if (leftX >= EDGE) return { x: Math.round(leftX), y }

  // 四周都放不下：夹进视口（压住球，但球层级更高仍可拖）
  const yFallback = fabRect.top >= vh - fabRect.bottom ? aboveTop : belowTop
  return {
    x: alignX(fabRect, pw, vw),
    y: Math.round(Math.min(Math.max(yFallback, EDGE), Math.max(EDGE, vh - ph - EDGE))),
  }
}

/** 水平就近对齐：优先与球右对齐，左边越界就改左对齐，再越界就夹住 */
function alignX(fabRect, pw, vw) {
  let x = fabRect.right - pw
  if (x < EDGE) x = fabRect.left
  return Math.round(Math.min(Math.max(x, EDGE), Math.max(EDGE, vw - pw - EDGE)))
}

/**
 * 欢迎语。带 kind 标记，名字改了之后靠它把这条自我介绍一并换掉
 * （已经聊过的内容不动）。
 */
const welcome = (name) => ({
  role: 'assistant',
  kind: 'intro',
  content: `你好，我是 ${name} 🌙 你的知识库 AI 助手。\n基于你上传的文档提问，我会给出带原文出处的回答。试试「报销标准是什么」之类的问题吧。`,
})

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
  const { user, updateUser } = useAuth()
  const [open, setOpen] = useState(false)
  const [enabled, setEnabled] = useState(true)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  // AI 的名字：登录用户存在服务端（users.ai_name），没起过名时是 null
  const aiName = user?.ai_name || DEFAULT_AI_NAME
  const [msgs, setMsgs] = useState(() => [welcome(aiName)])
  // 起名 / 改名步骤：首次打开面板时（登录且从没起过名）自动进入
  const [naming, setNaming] = useState(false)
  const [nameDraft, setNameDraft] = useState('')
  const [nameErr, setNameErr] = useState('')
  const [savingName, setSavingName] = useState(false)
  // 悬浮球位置：null = 用 CSS 默认的右下角（含手机的 safe-area 处理），
  // 拖动过之后才由 JS 接管
  const [pos, setPos] = useState(loadFabPos)
  const [dragging, setDragging] = useState(false)
  const boxRef = useRef(null)
  const fabRef = useRef(null)
  const panelRef = useRef(null)
  const sessionKey = useRef(getSessionKey())
  const abortRef = useRef(null)
  const dragRef = useRef(null)
  const draggedRef = useRef(false)

  // 面板保持常驻悬浮形态（不遮挡页面），但点页面其他地方的空白处即收起。
  // 悬浮按钮本身要排除在「外部」之外，否则会和它自己的 toggle 打架。
  useClickOutside([fabRef, panelRef], () => setOpen(false), open)

  /**
   * 悬浮球的**布局**位置，而不是 getBoundingClientRect()。
   * .ai-fab:hover 有 translateY(-3px) scale(1.05)，用视觉矩形取起点会偏 3px 左右。
   * 面板定位与拖拽起点都基于它，保证和最终的 left/top 是同一套坐标系。
   */
  const fabRect = () => {
    const fab = fabRef.current
    if (!fab) return null
    const w = fab.offsetWidth
    const h = fab.offsetHeight
    const l = fab.offsetLeft
    const t = fab.offsetTop
    return { left: l, top: t, right: l + w, bottom: t + h, width: w, height: h }
  }

  // 面板跟随悬浮球：按两者的实测尺寸算出坐标，写成 CSS 变量（不走 React state，
  // 免得每帧重渲染整个消息列表）
  const free = !!pos || dragging
  useLayoutEffect(() => {
    if (!free || !open) return
    const sync = () => {
      const r = fabRect()
      const panel = panelRef.current
      if (!r || !panel) return
      const { x, y } = placePanel(r, panel.offsetWidth, panel.offsetHeight)
      panel.style.setProperty('--ai-panel-x', x + 'px')
      panel.style.setProperty('--ai-panel-y', y + 'px')
    }
    sync()
    window.addEventListener('resize', sync)
    return () => window.removeEventListener('resize', sync)
  }, [free, open, pos])

  // 视口变小后可能把球留在屏幕外，夹回来
  useEffect(() => {
    const onResize = () => {
      const fab = fabRef.current
      setPos((p) => {
        if (!p) return p
        const w = fab?.offsetWidth || 56
        const h = fab?.offsetHeight || 56
        const c = clampFab(p.x, p.y, w, h)
        return c.x === p.x && c.y === p.y ? p : c
      })
    }
    window.addEventListener('resize', onResize)
    onResize() // 挂载时也夹一次（存的坐标可能来自更大的窗口）
    return () => window.removeEventListener('resize', onResize)
  }, [])

  /**
   * 悬浮球拖拽。用 Pointer Events 统一鼠标/触摸；
   * 位移小于 5px 视为点击（否则想打开面板时会一碰就跑）。
   * 位置在 pointerup 时落 localStorage。
   */
  const onFabDown = (e) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return
    const fab = fabRef.current
    const r = fabRect()
    if (!fab || !r) return
    dragRef.current = { id: e.pointerId, sx: e.clientX, sy: e.clientY, ox: r.left, oy: r.top, w: r.width, h: r.height }
    draggedRef.current = false
    try { fab.setPointerCapture(e.pointerId) } catch { /* 不支持就算了 */ }
  }

  const onFabMove = (e) => {
    const d = dragRef.current
    if (!d || e.pointerId !== d.id) return
    const dx = e.clientX - d.sx
    const dy = e.clientY - d.sy
    if (!draggedRef.current) {
      if (Math.hypot(dx, dy) < 5) return // 还没到阈值，当作点击
      draggedRef.current = true
      setDragging(true)
    }
    const next = clampFab(d.ox + dx, d.oy + dy, d.w, d.h)
    d.last = next
    setPos(next)
  }

  const onFabUp = (e) => {
    const d = dragRef.current
    if (!d) return
    dragRef.current = null
    try { fabRef.current?.releasePointerCapture(d.id) } catch { /* ignore */ }
    if (!draggedRef.current) return // 没拖动 → 交给 onClick 处理开关
    setDragging(false)
    if (d.last) {
      try { localStorage.setItem(POS_KEY, JSON.stringify(d.last)) } catch { /* 隐私模式等 */ }
    }
  }

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
          setMsgs([welcome(aiName), ...data.items.map((m) => ({ role: m.role, content: m.content }))])
        }
      })
      .catch(() => {})
    // 依赖写成 user?.id 而不是整个 user 对象：改名后 store 会换成一个新对象，
    // 若因此重拉历史，会把正在生成的回答整段冲掉。
    // 名字本身由下面那个 [aiName] 的 effect 负责更新欢迎语。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, user?.id])

  // 名字变了（首次起名 / 改名 / 换账号）→ 只换掉那条自我介绍，聊天记录不动
  useEffect(() => {
    setMsgs((m) => m.map((x) => (x.kind === 'intro' ? welcome(aiName) : x)))
  }, [aiName])

  // 首次使用引导：登录用户还没给 AI 起过名 → 打开面板就先请他起名。
  // 没起名之前每次打开都会再问一次（也随时可以按 Esc 先跳过）。
  useEffect(() => {
    if (!open || !user || user.ai_name) return
    setNaming(true)
    setNameDraft('')
    setNameErr('')
  }, [open, user?.id, user?.ai_name])

  // Esc 退出起名/改名步骤。挂在 window 上而不是输入框上：
  // 用户点过「快速选择」胶囊之后焦点在按钮上，输入框的 onKeyDown 收不到按键。
  useEffect(() => {
    if (!naming) return
    const onKey = (e) => {
      if (e.key === 'Escape') setNaming(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [naming])

  useEffect(() => {
    const el = boxRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [msgs, busy, open])

  /** 保存 AI 名字（首次起名与改名共用）。成功后就地把用户信息写回 store。 */
  const saveAiName = async (raw) => {
    const name = (raw || '').trim().replace(/\s+/g, ' ')
    if (!name) {
      setNameErr('名字不能是空的')
      return
    }
    // 按码点数（emoji 算 1 个），与后端 len() 的口径一致
    if ([...name].length > MAX_AI_NAME) {
      setNameErr(`最多 ${MAX_AI_NAME} 个字`)
      return
    }
    setSavingName(true)
    setNameErr('')
    try {
      const { data } = await api.patch('/users/me', { ai_name: name })
      updateUser(data)
      setNaming(false)
    } catch (e) {
      setNameErr(errMsg(e))
    } finally {
      setSavingName(false)
    }
  }

  const ask = async (q) => {
    const text = (q || '').trim()
    if (!text || busy) return
    // 注意：提问**不**触发背景扫描（按用户要求，只有上传文档时才扫）
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
    setMsgs([welcome(aiName)])
  }

  if (!enabled) return null

  return (
    <>
      <button
        className={
          'ai-fab' + (open ? ' active' : '') + (free ? ' free' : '') + (dragging ? ' dragging' : '')
        }
        ref={fabRef}
        style={pos ? { '--ai-fab-x': pos.x + 'px', '--ai-fab-y': pos.y + 'px' } : undefined}
        onPointerDown={onFabDown}
        onPointerMove={onFabMove}
        onPointerUp={onFabUp}
        onPointerCancel={onFabUp}
        onClick={() => {
          // 拖完那一下浏览器还会补一个 click，要吞掉，否则面板会莫名其妙开关一次
          if (draggedRef.current) {
            draggedRef.current = false
            return
          }
          setOpen((v) => !v)
        }}
        title="AI 助手（可拖动）"
        aria-label="AI 助手"
      >
        {open ? '✕' : '✦'}
      </button>

      {open && (
        <div className={'ai-panel' + (free ? ' free' : '')} ref={panelRef}>
          <div className="ai-head">
            <div className="ai-title">
              <span className="ai-dot" />
              <span className="ai-title-text">{aiName} · AI 助手</span>
            </div>
            <div className="ai-head-actions">
              {user && (
                <button
                  onClick={() => {
                    setNaming(true)
                    setNameDraft(user.ai_name || '')
                    setNameErr('')
                  }}
                  title="给 AI 改个名字"
                  aria-label="给 AI 改个名字"
                >
                  ✎
                </button>
              )}
              <button onClick={clear} title="清空对话">
                清空
              </button>
              <button onClick={() => setOpen(false)} title="收起">
                ▾
              </button>
            </div>
          </div>

          {naming ? (
            <div className="ai-setup">
              <div className="ai-setup-mark">✦</div>
              <div className="ai-setup-h">
                {user?.ai_name ? '给我改个名字' : '先给我起个名字吧'}
              </div>
              <p className="ai-setup-p">
                {user?.ai_name
                  ? '改完立刻生效，面板上的称呼会一起换掉。'
                  : `我的名字由你定，默认叫 ${DEFAULT_AI_NAME}，之后随时能改。`}
              </p>
              <input
                className="ai-setup-input"
                value={nameDraft}
                maxLength={MAX_AI_NAME}
                autoFocus={CAN_HOVER}
                placeholder={NAME_PLACEHOLDER}
                aria-label="AI 助手名字"
                onChange={(e) => {
                  setNameDraft(e.target.value)
                  setNameErr('')
                }}
                onKeyDown={(e) => {
                  // Esc 由 window 上的监听统一处理，这里只管 Enter
                  if (e.key === 'Enter') saveAiName(nameDraft)
                }}
              />
              <div className="ai-setup-chips">
                {NAME_SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => {
                      setNameDraft(s)
                      setNameErr('')
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
              {nameErr && <div className="ai-setup-err">{nameErr}</div>}
              <button
                className="ai-setup-go"
                onClick={() => saveAiName(nameDraft)}
                disabled={savingName || !nameDraft.trim()}
              >
                {savingName ? '保存中…' : '就叫这个'}
              </button>
              {!user?.ai_name && (
                <button
                  className="ai-setup-skip"
                  onClick={() => saveAiName(DEFAULT_AI_NAME)}
                  disabled={savingName}
                >
                  先用默认名「{DEFAULT_AI_NAME}」
                </button>
              )}
            </div>
          ) : (
            <>
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
            </>
          )}
        </div>
      )}
    </>
  )
}
