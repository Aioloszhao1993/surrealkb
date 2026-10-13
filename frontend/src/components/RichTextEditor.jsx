import { useEffect, useRef } from 'react'
import { marked } from 'marked'
import TurndownService from 'turndown'

// 富文本（所见即所得）编辑：Markdown 作为内部存储/交换格式，但只暴露富文本一种编辑方式。
// 进入编辑时用 marked 把 Markdown 渲染成 HTML；编辑时用 turndown 写回 Markdown。
// 表格/图片等复杂结构用 keep 原样保留为 HTML，保证「原文件的格式和样式」尽量还原。

const turndown = new TurndownService({
  headingStyle: 'atx',
  codeBlockStyle: 'fenced',
  bulletListMarker: '-',
  emDelimiter: '*',
})
// 表格（含 caption）原样保留，避免 GFM 表格在国内 Word 复杂结构下丢样式
turndown.keep(['table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption'])
// 图片无法可靠定位原始资源，直接丢弃，避免编辑区出现裂图
turndown.addRule('dropImage', { filter: 'img', replacement: () => '' })

marked.setOptions({ gfm: true, breaks: false })

function mdToHtml(md) {
  try {
    const html = marked.parse(md || '')
    return typeof html === 'string' ? html : ''
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
  const boxRef = useRef(null)

  // 仅在挂载时用 Markdown 渲染一次 HTML（不随每次输入重渲染，避免光标跳动）
  useEffect(() => {
    if (boxRef.current) boxRef.current.innerHTML = mdToHtml(value)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onInput = () => {
    if (!boxRef.current) return
    onChange(htmlToMd(boxRef.current.innerHTML))
  }

  const exec = (cmd, arg) => {
    boxRef.current?.focus()
    document.execCommand(cmd, false, arg)
    onInput()
  }

  const addTable = () => {
    const html = `<table><thead><tr><th>列1</th><th>列2</th><th>列3</th></tr></thead><tbody><tr><td>　</td><td>　</td><td>　</td></tr><tr><td>　</td><td>　</td><td>　</td></tr></tbody></table><p><br/></p>`
    boxRef.current?.focus()
    document.execCommand('insertHTML', false, html)
    onInput()
  }

  const Btn = ({ title, onClick, children }) => (
    <button type="button" title={title} onMouseDown={(e) => e.preventDefault()} onClick={onClick}>
      {children}
    </button>
  )

  return (
    <div className="rt-editor">
      <div className="rt-toolbar">
        <Btn title="加粗" onClick={() => exec('bold')}><b>B</b></Btn>
        <Btn title="斜体" onClick={() => exec('italic')}><i>I</i></Btn>
        <Btn title="下划线" onClick={() => exec('underline')}><u>U</u></Btn>
        <span className="rt-sep" />
        <Btn title="一级标题" onClick={() => exec('formatBlock', 'h1')}>H1</Btn>
        <Btn title="二级标题" onClick={() => exec('formatBlock', 'h2')}>H2</Btn>
        <Btn title="三级标题" onClick={() => exec('formatBlock', 'h3')}>H3</Btn>
        <Btn title="正文段落" onClick={() => exec('formatBlock', 'p')}>¶</Btn>
        <span className="rt-sep" />
        <Btn title="无序列表" onClick={() => exec('insertUnorderedList')}>• ≡</Btn>
        <Btn title="有序列表" onClick={() => exec('insertOrderedList')}>1. ≡</Btn>
        <Btn title="引用" onClick={() => exec('formatBlock', 'blockquote')}>❝</Btn>
        <Btn title="插入表格" onClick={addTable}>▦ 表格</Btn>
        <span className="rt-sep" />
        <Btn title="左对齐" onClick={() => exec('justifyLeft')}>⇤</Btn>
        <Btn title="居中" onClick={() => exec('justifyCenter')}>↔</Btn>
        <Btn title="清除格式" onClick={() => exec('removeFormat')}>✕</Btn>
      </div>

      <div
        ref={boxRef}
        className="rt-rich"
        contentEditable
        suppressContentEditableWarning
        onInput={onInput}
        onBlur={onInput}
        data-ph={placeholder}
      />
    </div>
  )
}
