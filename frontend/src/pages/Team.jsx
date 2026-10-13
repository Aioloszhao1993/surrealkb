import { useCallback, useEffect, useState } from 'react'
import api, { errMsg } from '../api'
import Avatar from '../components/Avatar'
import { Link } from 'react-router-dom'

export default function Team() {
  const [tenant, setTenant] = useState(null)
  const [members, setMembers] = useState([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [joining, setJoining] = useState(false)
  const [name, setName] = useState('')
  const [invite, setInvite] = useState('')
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')

  const flash = (m) => {
    setToast(m)
    setTimeout(() => setToast(''), 1800)
  }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/tenants/current')
      setTenant(data)
      const m = await api.get('/tenants/members/detail')
      setMembers(m.data)
    } catch {
      setTenant(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const doCreate = async (e) => {
    e.preventDefault()
    setError('')
    if (!name.trim()) return setError('请填写知识库名称')
    try {
      await api.post('/tenants', { name: name.trim() })
      setName('')
      setCreating(false)
      await load()
      flash('知识库已创建')
    } catch (err) {
      setError(errMsg(err))
    }
  }

  const doJoin = async (e) => {
    e.preventDefault()
    setError('')
    if (!invite.trim()) return setError('请输入邀请码')
    try {
      await api.post('/tenants/join', { invite_code: invite.trim() })
      setInvite('')
      setJoining(false)
      await load()
      flash('已加入知识库')
    } catch (err) {
      setError(errMsg(err))
    }
  }

  const copyInvite = async () => {
    if (!tenant?.invite_code) return
    try {
      await navigator.clipboard.writeText(tenant.invite_code)
      flash('邀请码已复制')
    } catch {
      flash(tenant.invite_code)
    }
  }

  const doResetInvite = async () => {
    if (!window.confirm('重置后旧邀请码立即失效，已分享出去的邀请码将无法再加入。确定重置？')) return
    try {
      const { data } = await api.post('/tenants/invite/reset')
      setTenant(data)
      flash('邀请码已重置')
    } catch (err) {
      flash(errMsg(err))
    }
  }

  if (loading) return <div className="page-loading">加载中…</div>

  if (!tenant) {
    return (
      <div className="team">
        <h1 className="page-title">知识库</h1>
        <p className="faint">你还没有加入任何知识库。创建一个自己的，或用邀请码加入团队。</p>

        <div className="team-forms">
          <div className="auth-card">
            <h2 className="auth-title">创建知识库</h2>
            {creating ? (
              <form onSubmit={doCreate} className="form">
                <label className="field">
                  <span>名称</span>
                  <input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} placeholder="例如：XX 科技产品知识库" />
                </label>
                {error && <div className="alert">{error}</div>}
                <button className="btn primary block">创建</button>
              </form>
            ) : (
              <button className="btn primary block" onClick={() => setCreating(true)}>
                创建我的知识库
              </button>
            )}
          </div>

          <div className="auth-card">
            <h2 className="auth-title">加入团队</h2>
            {joining ? (
              <form onSubmit={doJoin} className="form">
                <label className="field">
                  <span>邀请码</span>
                  <input value={invite} onChange={(e) => setInvite(e.target.value)} maxLength={16} placeholder="输入 8 位邀请码" />
                </label>
                {error && <div className="alert">{error}</div>}
                <button className="btn primary block">加入</button>
              </form>
            ) : (
              <button className="btn ghost block" onClick={() => setJoining(true)}>
                用邀请码加入
              </button>
            )}
          </div>
        </div>
        {toast && <div className="toast">{toast}</div>}
      </div>
    )
  }

  return (
    <div className="team">
      <div className="team-head">
        <div>
          <h1 className="page-title">{tenant.name}</h1>
          <p className="faint">
            {tenant.member_count} 位成员 · {tenant.document_count} 篇文档
          </p>
        </div>
        {tenant.can_manage ? (
          <div className="team-invite">
            <span className="faint">邀请码</span>
            <code>{tenant.invite_code}</code>
            <button className="btn ghost" onClick={copyInvite}>
              复制
            </button>
            <button className="btn ghost" onClick={doResetInvite}>
              重置
            </button>
          </div>
        ) : (
          <div className="team-invite">
            <span className="faint">邀请码由创建者管理</span>
          </div>
        )}
      </div>

      <h2 className="section-title">成员（{members.length}）</h2>
      <div className="member-list">
        {members.map((m) => (
          <Link key={m.id} to={`/user/${m.id}`} className="member-row">
            <Avatar user={m} size="md" />
            <div className="member-info">
              <span className="member-name">{m.username}</span>
              <span className="faint">{m.role === 'owner' ? '创建者' : '成员'}</span>
            </div>
          </Link>
        ))}
      </div>

      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
