import { useState } from 'react'
import { errMsg } from '../api'
import { useAuth } from '../store'
import useWxStatus from '../useWxStatus'
import PresetGrid from './PresetGrid'
import WechatLogin from './WechatLogin'
import portal from './Portal'

/**
 * 全站唯一的认证入口弹窗（未登录时）。
 *
 * 设计说明：
 * - 单页展示：上半部分是账号登录，底部一行「还没有账号？免费注册」切换到注册；
 *   注册里包含原来的「免费创建知识库」（创建新知识库 / 用邀请码加入二选一）。
 * - 微信扫码登录作为登录页里的一个入口，点开复用既有的 WechatLogin 弹窗。
 * - 通过 portal 挂到 document.body，遮罩铺满整个视口，点空白处即关闭。
 *   （不能用 `return (<div className="modal-back">…)`：本弹窗会被渲染进带
 *   backdrop-filter 的容器里，那样遮罩只会铺满容器、点空白关不掉。）
 */
export default function AuthModal({ onClose, onDone, initialMode = 'login' }) {
  const { login, register } = useAuth()
  const wxEnabled = useWxStatus()
  const [mode, setMode] = useState(initialMode) // login | register

  // 登录表单
  const [loginName, setLoginName] = useState('')
  const [loginPass, setLoginPass] = useState('')
  // 注册表单
  const [regName, setRegName] = useState('')
  const [regEmail, setRegEmail] = useState('')
  const [regPass, setRegPass] = useState('')
  const [avatar, setAvatar] = useState('')
  const [tenantName, setTenantName] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [joinMode, setJoinMode] = useState(false) // 注册：创建新知识库 / 用邀请码加入

  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [showWx, setShowWx] = useState(false)

  const switchMode = (next) => {
    setMode(next)
    setError('')
  }

  const finish = (u) => {
    onDone?.(u)
    onClose?.()
  }

  const submitLogin = async (e) => {
    e.preventDefault()
    setError('')
    if (!loginName.trim() || !loginPass) return setError('请填写用户名和密码')
    setBusy(true)
    try {
      const u = await login(loginName.trim(), loginPass)
      finish(u)
    } catch (err) {
      setError(errMsg(err))
    } finally {
      setBusy(false)
    }
  }

  const submitRegister = async (e) => {
    e.preventDefault()
    setError('')
    if (regName.trim().length < 3) return setError('用户名至少 3 个字符')
    if (regPass.length < 6) return setError('密码至少 6 位')
    if (joinMode && !inviteCode.trim()) return setError('请填写邀请码')
    if (!joinMode && !tenantName.trim()) return setError('请填写知识库名称')
    setBusy(true)
    try {
      const u = await register(
        regName.trim(),
        regPass,
        regEmail.trim(),
        avatar,
        joinMode ? null : tenantName.trim(),
        joinMode ? inviteCode.trim() : null
      )
      finish(u)
    } catch (err) {
      setError(errMsg(err))
    } finally {
      setBusy(false)
    }
  }

  return portal(
    <div className="modal-back" onClick={onClose}>
      <div className="auth-modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-x" onClick={onClose} aria-label="关闭">
          ✕
        </button>

        {mode === 'login' ? (
          <>
            <h2 className="wx-title">登录</h2>
            <p className="wx-sub">登录以管理知识库、上传文档与提问</p>

            <form onSubmit={submitLogin} className="form">
              <label className="field">
                <span>用户名</span>
                <input
                  value={loginName}
                  onChange={(e) => setLoginName(e.target.value)}
                  autoComplete="username"
                />
              </label>
              <label className="field">
                <span>密码</span>
                <input
                  type="password"
                  value={loginPass}
                  onChange={(e) => setLoginPass(e.target.value)}
                  autoComplete="current-password"
                />
              </label>

              {error && <div className="alert">{error}</div>}

              <button className="btn primary block" disabled={busy}>
                {busy ? '登录中…' : '登录'}
              </button>
            </form>

            {wxEnabled && (
              <>
                <div className="divider">
                  <span>或</span>
                </div>
                <button className="btn wechat block" onClick={() => setShowWx(true)}>
                  <span className="wx-logo">✆</span> 微信扫码登录
                </button>
              </>
            )}

            <p className="auth-foot">
              还没有账号？
              <button className="link" onClick={() => switchMode('register')}>
                免费注册
              </button>
            </p>
          </>
        ) : (
          <>
            <h2 className="wx-title">创建账号</h2>
            <p className="wx-sub">拥有属于你自己的知识库</p>

            <form onSubmit={submitRegister} className="form">
              <PresetGrid value={avatar} onChange={setAvatar} username={regName} />

              <label className="field">
                <span>用户名 *</span>
                <input
                  value={regName}
                  onChange={(e) => setRegName(e.target.value)}
                  autoComplete="username"
                />
              </label>
              <label className="field">
                <span>邮箱（可选）</span>
                <input
                  type="email"
                  value={regEmail}
                  onChange={(e) => setRegEmail(e.target.value)}
                  autoComplete="email"
                />
              </label>
              <label className="field">
                <span>密码 *</span>
                <input
                  type="password"
                  value={regPass}
                  onChange={(e) => setRegPass(e.target.value)}
                  autoComplete="new-password"
                />
              </label>

              <div className="toggle-row">
                <button
                  type="button"
                  className={joinMode ? 'toggle' : 'toggle active'}
                  onClick={() => setJoinMode(false)}
                >
                  创建新知识库
                </button>
                <button
                  type="button"
                  className={joinMode ? 'toggle active' : 'toggle'}
                  onClick={() => setJoinMode(true)}
                >
                  用邀请码加入
                </button>
              </div>

              {joinMode ? (
                <label className="field">
                  <span>邀请码 *</span>
                  <input
                    value={inviteCode}
                    onChange={(e) => setInviteCode(e.target.value)}
                    maxLength={16}
                    placeholder="8 位邀请码"
                  />
                </label>
              ) : (
                <label className="field">
                  <span>知识库名称 *</span>
                  <input
                    value={tenantName}
                    onChange={(e) => setTenantName(e.target.value)}
                    maxLength={100}
                    placeholder="例如：XX 科技产品知识库"
                  />
                </label>
              )}

              {error && <div className="alert">{error}</div>}

              <button className="btn primary block" disabled={busy}>
                {busy ? '创建中…' : '创建账号'}
              </button>
            </form>

            <p className="auth-foot">
              已有账号？
              <button className="link" onClick={() => switchMode('login')}>
                去登录
              </button>
            </p>
          </>
        )}

        {showWx && (
          <WechatLogin
            onClose={() => setShowWx(false)}
            onDone={(u) => finish(u)}
          />
        )}
      </div>
    </div>
  )
}
