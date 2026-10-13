import { useEffect, useRef, useState } from 'react'
import { marked } from 'marked'
import TurndownService from 'turndown'
import { gfm } from 'turndown-plugin-gfm'

// Markdown 是编辑器的唯一交换格式：
// 富文本模式（所见即所得）<-> turndown/marked <-> Markdown <-> 纯文本模式

const turndown = new TurndownService({
  headingStyle: 'atx',
  codeBlockStyle: 'fenced',
  bulletListMarker: '-',
  emDelimiter: '*',
})
turndown.use(gfm)
turndown.keep(['table', 'thead', 'tbody', 'tr', 'th', 'td'])

marked.setOptions({ gfm: true, breaks: false })

function mdToHtml(md) {
  try {
    return marked.parse(md || '')
  } catch {
    return ''
  }
}

function htmlToMd(html) {
  try {
    return turndown.turndown(html || '')
  } catch {
    return ''
  }
}

export default function RichTextEditor({ value, onChange, placeholder }) {
  const [mode, setMode] = useState('rich') // rich | md
  const boxRef = useRef(null)
  const lastMd = useRef(value)

  // 切入富文本模式时，用 Markdown 渲染一次 HTML（不随每次输入重渲染，避免光标跳动）
  useEffect(() => {
    if (mode === 'rich' && boxRef.current) {
      boxRef.current.innerHTML = mdToHtml(value)
      lastMd.current = value
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  const onInput = () => {
    if (!boxRef.current) return
    const md = htmlToMd(boxRef.current.innerHTML)
    lastMd.current = md
    onChange(md)
  }

  const exec = (cmd, arg) => {
    boxRef.current?.focus()
    document.execCommand(cmd, false, arg)
    onInput()
  }

  const switchMode = (next) => {
    if (next === 'rich' && boxRef.current) {
      // 从 md 切回 rich：把当前 markdown 渲染回富文本
      setMode('rich')
      requestAnimationFrame(() => {
        if (boxRef.current) boxRef.current.innerHTML = mdToHtml(value)
      })
      return
    }
    setMode(next)
  }

  return (
    <div className="rt-editor">
      <div className="rt-toolbar">
        {mode === 'rich' ? (
          <>
            <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('bold')} title="加粗">
              <b>B</b>
            </button>
            <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('italic')} title="斜体">
              <i>I</i>
            </button>
            <span className="rt-sep" />
            <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('formatBlock', 'h1')} title="一级标题">H1</button>
            <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('formatBlock', 'h2')} title="二级标题">H2</button>
            <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('formatBlock', 'h3')} title="三级标题">H3</button>
            <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('formatBlock', 'p')} title="正文">¶</button>
            <span className="rt-sep" />
            <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('insertUnorderedList')} title="无序列表">•≡</button>
            <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('insertOrderedList')} title="有序列表">1.</button>
            <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('formatBlock', 'blockquote')} title="引用">❝</button>
            <span className="rt-sep" />
            <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('removeFormat')} title="清除格式">✕</button>
          </>
        ) : (
          <span className="rt-hint">Markdown 源码模式：直接编辑 # 标题、- 列表、| 表格 等语法</span>
        )}
        <div className="rt-modes">
          <button
            type="button"
            className={`rt-mode${mode === 'rich' ? ' active' : ''}`}
            onClick={() => switchMode('rich')}
          >
            富文本
          </button>
          <button
            type="button"
            className={`rt-mode${mode === 'md' ? ' active' : ''}`}
            onClick={() => switchMode('md')}
          >
            Markdown
          </button>
        </div>
      </div>

      {mode === 'rich' ? (
        <div
          ref={boxRef}
          className="rt-rich"
          contentEditable
          suppressContentEditableWarning
          onInput={onInput}
          onBlur={onInput}
          data-ph={placeholder}
        />
      ) : (
        <textarea
          className="rt-md"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
        />
      )}
    </div>
  )
}
