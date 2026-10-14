import { Component } from 'react'

// 前端错误边界：任一页面渲染抛错时，兜底展示友好提示，而不是白屏
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // 保留在控制台，便于排查
    console.error('[SurrealKB] 页面渲染异常:', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="empty err-boundary">
          <div className="err-boundary-title">页面出了点问题 🙈</div>
          <p className="err-boundary-msg">{String(this.state.error?.message || this.state.error)}</p>
          <div className="err-boundary-actions">
            <button className="btn primary" onClick={() => this.setState({ error: null })}>
              重试
            </button>
            <button className="btn ghost" onClick={() => (window.location.href = '/')}>
              回到首页
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
