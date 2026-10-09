import { useEffect, useRef, useState } from 'react'
import api from '../api'
import { useAuth } from '../store'

const POLL_MS = 1800

export default function WechatLogin({ onClose, onDone }) {
  const { applyToken } = useAuth()
  const [qr, setQr] = useState('')
  const [mode, setMode] = useState('')
  const [state, setState] = useState('')
  const [status, setStatus] = useState('loading') // loading|pending|confirmed|expired|error
  const [err, setErr] = useState('')
  const timer = useRef(null)
  const closed = useRef(false)

  const stop = () => {
    if (timer.current) {
      clearInterval(timer.current)
      timer.current = null
    }
  }

  const load = async () => {
    setStatus('loading')
    setErr('')
    try {
      const { data } = await api.get('/auth/wx/qrcode')
      setQr(data.qr)
      setMode(data.mode)
      setState(data.state)
      setStatus('pending')
    } catch (e) {
      setStatus('error')
      setErr(e?.response?.data?.detail || '二维码获取失败，请稍后再试')
    }
  }

  useEffect(() => {
    load()
    return () => {
      closed.current = true
      stop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!state || status !== 'pending') return
    stop()
    timer.current = setInterval(async () => {
      try {
        const { data } = await api.get('/auth/wx/poll', { params: { state } })
        if (data.status === 'confirmed' && data.token) {
          stop()
          setStatus('confirmed')
          applyToken(data.token, data.user)
          setTimeout(() => {
            if (!closed.current) {
              onDone?.(data.user)
              onClose?.()
            }
          }, 900)
        } else if (data.status === 'expired') {
          stop()
          setStatus('expired')
        }
      } catch {
        /* 轮询失败忽略，等下一次 */
      }
    }, POLL_MS)
    return stop
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, status])

  const scanUrl = mode === 'mock' && state ? `/api/auth/wx/mock?state=${state}` : ''

  return (
    <div className="modal-back" onClick={onClose}>
      <div className="wx-modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-x" onClick={onClose} aria-label="关闭">
          ✕
        </button>
        <h2 className="wx-title">微信扫码登录</h2>
        <p className="wx-sub">用微信扫一扫，快速登录 SurrealVideo</p>

        <div className="wx-qr-wrap">
          {qr ? (
            <img className="wx-qr" src={qr} alt="微信登录二维码" />
          ) : (
            <div className="wx-qr loading">{status === 'error' ? '×' : '二维码生成中…'}</div>
          )}
          {status === 'confirmed' && (
            <div className="wx-mask ok">
              <span>✓</span>
              <p>登录成功</p>
            </div>
          )}
          {status === 'expired' && (
            <div className="wx-mask">
              <p>二维码已失效</p>
              <button className="btn primary" onClick={load}>
                刷新二维码
              </button>
            </div>
          )}
        </div>

        {mode === 'mock' ? (
          <div className="wx-tip mock">
            <b>本地演示模式</b>
            <span>
              当前未配置微信 AppID，二维码指向本机模拟授权页。
              可用微信扫一扫，或直接
              <a href={scanUrl} target="_blank" rel="noreferrer">
                点此打开授权页
              </a>
              （手机扫码更真实）。
            </span>
          </div>
        ) : (
          <p className="wx-tip">请使用微信扫描二维码，并在手机上确认登录</p>
        )}

        {err && <div className="alert">{err}</div>}

        <div className="wx-actions">
          <button
            className="btn ghost"
            onClick={async () => {
              // 一键虚拟扫码：无需扫码，直接生成一个微信风格用户
              try {
                const { data } = await api.get('/auth/wx/virtual')
                applyToken(data.access_token, data.user)
                onDone?.(data.user)
                onClose?.()
              } catch (e) {
                setErr(e?.response?.data?.detail || '虚拟登录失败')
              }
            }}
          >
            ⚡ 模拟一键登录
          </button>
          <button className="btn ghost" onClick={load}>
            刷新二维码
          </button>
        </div>
      </div>
    </div>
  )
}
