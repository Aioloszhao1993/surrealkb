import { useMemo } from 'react'
import { PRESET_AVATARS } from '../presets'
import { avatarUrl, gradientFor } from './Avatar'

/**
 * 注册页等「还没有用户对象」的场景使用的头像选择器。
 * 完全受控：value 为具体头像字符串（data URL）或空字符串（=用昵称首字母渐变兜底）。
 */
export default function PresetGrid({ value, onChange, username = '', sizeClass = 'preset' }) {
  const previewUrl = avatarUrl(value)
  const previewStyle = useMemo(
    () => (previewUrl ? {} : { background: gradientFor(username || '?') }),
    [previewUrl, username]
  )

  return (
    <div className="preset-picker">
      <div className="preset-picker-preview">
        <span className="avatar avatar-lg" style={previewStyle}>
          {previewUrl ? (
            <img src={previewUrl} alt="头像预览" />
          ) : (
            <span className="avatar-letter">{(username || '?').slice(0, 1).toUpperCase()}</span>
          )}
        </span>
        <div className="preset-picker-hint">
          <b>选择头像</b>
          <span className="faint">
            {value ? '点击「清除」可改用昵称首字默认头像' : '不选也没关系，会用昵称首字生成默认头像'}
          </span>
        </div>
        {value && (
          <button type="button" className="btn ghost tiny" onClick={() => onChange('')}>
            清除
          </button>
        )}
      </div>

      <div className="preset-grid small">
        {PRESET_AVATARS.map((p) => (
          <button
            key={p.id}
            type="button"
            className={value === p.data ? `${sizeClass} active` : sizeClass}
            onClick={() => onChange(value === p.data ? '' : p.data)}
            title={p.name}
            style={{ background: p.bg }}
          >
            {p.glyph}
          </button>
        ))}
      </div>
    </div>
  )
}
