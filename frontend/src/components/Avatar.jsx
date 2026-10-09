// 头像统一渲染：支持自定义图片（/media/... 或 data URL）与首字母兜底
const GRADS = [
  'linear-gradient(135deg, #9b59ff, #00e5ff)',
  'linear-gradient(135deg, #ff5ca8, #ffcd60)',
  'linear-gradient(135deg, #00e5ff, #34ffab)',
  'linear-gradient(135deg, #ff6f91, #9b59ff)',
  'linear-gradient(135deg, #60a5fa, #c084fc)',
]

export function avatarUrl(avatar) {
  if (!avatar) return null
  if (avatar.startsWith('data:') || avatar.startsWith('http')) return avatar
  return `/media/${avatar}`
}

// 预览任意头像字符串（可能是预设 data URL、/media 路径或后端返回的相对路径）
export function previewSrc(avatar) {
  return avatarUrl(avatar)
}

export function gradientFor(name = '') {
  let h = 0
  for (const ch of String(name)) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return GRADS[h % GRADS.length]
}

const SIZES = { sm: 24, md: 40, lg: 64, xl: 96 }

export default function Avatar({ user, size = 'md', className = '' }) {
  const name = user?.username || '?'
  const url = avatarUrl(user?.avatar)
  const px = typeof size === 'number' ? size : SIZES[size] || 40
  const style = {
    width: px,
    height: px,
    fontSize: Math.round(px * (url ? 0.42 : 0.46)),
    ...(url ? {} : { background: gradientFor(name) }),
  }
  return (
    <span className={`avatar avatar-${size} ${className}`} style={style} title={name}>
      {url ? (
        <img src={url} alt={name} loading="lazy" />
      ) : (
        <span className="avatar-letter">{name.slice(0, 1).toUpperCase()}</span>
      )}
    </span>
  )
}
