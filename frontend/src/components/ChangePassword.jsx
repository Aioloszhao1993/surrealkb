import { useState } from 'react'
import api, { errMsg } from '../api'
import { passwordProblem } from '../passwordRules'
import portal from './Portal'

/**
 * 修改密码弹窗（已登录用户）。
 *
 * 两种账户：
 * - 有密码的账号：必须填原密码。
 * - 一直是微信扫码登录、从没设过密码的账号：原密码留空即可直接设置新密码
 *   （此时已通过微信身份认证，后端允许直接设置）。
 *
 * 通过 portal 挂到 document.body，遮罩铺满视口，点空白处关闭。
 */
export default function ChangePassword({ onClose }) {
  const [oldPwd, setOldPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    const p = passwordProblem(newPwd)
    if (p) return setError(p)
    if (newPwd !== confirm) return setError('两次输入的新密码不一致')
    if (oldPwd && newPwd === oldPwd) return setError('新密码不能与原密码相同')
    // 原密码是否必填交给后端判断：微信登录用户本来就没有密码，可以留空直接设置

    setBusy(true)
    try {
      await api.post('/auth/password', { old_password: oldPwd, new_password: newPwd })
      setDone(true)
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
        <h2 className="wx-title">修改密码</h2>

        {done ? (
          <>
            <p className="wx-sub">密码已更新，下次登录请使用新密码</p>
            <p className="auth-note">
              已经登录的其它设备不会自动退出（登录凭证有独立有效期）。若你怀疑账号曾被他人使用，
              请在服务器上更换 SECRET_KEY 并重启服务，这会让所有已签发的凭证立即失效。
            </p>
            <button className="btn primary block" style={{ marginTop: 18 }} onClick={onClose}>
              知道了
            </button>
          </>
        ) : (
          <>
            <p className="wx-sub">
              微信扫码登录的用户若从未设置过密码，原密码留空即可直接设置
            </p>

            <form onSubmit={submit} className="form">
              <label className="field">
                <span>原密码</span>
                <input
                  type="password"
                  value={oldPwd}
                  onChange={(e) => setOldPwd(e.target.value)}
                  autoComplete="current-password"
                  placeholder="从来没有设过密码就留空"
                />
              </label>
              <label className="field">
                <span>新密码</span>
                <input
                  type="password"
                  value={newPwd}
                  onChange={(e) => setNewPwd(e.target.value)}
                  autoComplete="new-password"
                />
                <em className="field-hint">至少 6 位，不能全是数字</em>
              </label>
              <label className="field">
                <span>确认新密码</span>
                <input
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  autoComplete="new-password"
                />
              </label>

              {error && <div className="alert">{error}</div>}

              <button className="btn primary block" disabled={busy}>
                {busy ? '提交中…' : '确认修改'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
