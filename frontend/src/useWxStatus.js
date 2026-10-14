import { useEffect, useState } from 'react'
import api from './api'

// 微信登录是否可用：未配置凭据时后端不提供二维码，前端就别渲染入口。
// 结果在会话内缓存，避免每次组件挂载都打一次接口。
let cached = null

export default function useWxStatus() {
  const [enabled, setEnabled] = useState(cached)

  useEffect(() => {
    if (cached !== null) {
      setEnabled(cached)
      return
    }
    let alive = true
    api
      .get('/auth/wx/status')
      .then(({ data }) => {
        cached = !!data.enabled
        if (alive) setEnabled(cached)
      })
      .catch(() => {
        // 拿不到状态时按「不可用」处理，宁可不显示，也不给用户一个点了会报错的按钮
        if (alive) setEnabled(false)
      })
    return () => {
      alive = false
    }
  }, [])

  return enabled
}
