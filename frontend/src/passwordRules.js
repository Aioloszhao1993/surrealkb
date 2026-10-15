/**
 * 密码规则的前端即时反馈。
 *
 * 与后端 `app/security.py::password_error` 保持一致 —— 但**后端才是权威**，
 * 这里只是为了不让用户先提交、再收到一个 422 才发现密码不合格。
 * 改规则时两边都要改。
 */
export const MIN_PASSWORD_LEN = 6

// 常见弱口令（按小写比较）
const WEAK_PASSWORDS = new Set([
  '123456', '1234567', '12345678', '123456789', '1234567890',
  '111111', '000000', '666666', '888888', '88888888',
  'password', 'passw0rd', 'qwerty', 'abc123', 'abcd1234',
  'admin', 'admin123', 'root123', 'letmein', 'iloveyou',
  'welcome', 'monkey', 'dragon', 'master', 'test123',
  'surreal', 'surrealkb', 'weixin', 'woaini', '5201314',
])

/** 返回不符合规则的原因；合规返回空字符串。 */
export function passwordProblem(password, username) {
  const p = password || ''
  if (p.length < MIN_PASSWORD_LEN) return `密码至少 ${MIN_PASSWORD_LEN} 位`
  if (/^\d+$/.test(p)) return '密码不能全是数字'
  if (WEAK_PASSWORDS.has(p.toLowerCase())) return '这个密码太常见了，换一个吧'
  if (username && p.trim().toLowerCase() === String(username).trim().toLowerCase()) {
    return '密码不能和用户名相同'
  }
  return ''
}
