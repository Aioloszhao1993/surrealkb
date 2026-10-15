import { useEffect, useRef } from 'react'

/**
 * 点击「目标之外」的空白处时触发回调，让弹窗 / 下拉菜单 / 浮层随点击空白自动消失。
 *
 * 用法：
 *   const boxRef = useRef(null)
 *   useClickOutside(boxRef, () => setOpen(false), open)
 *   ...
 *   <div ref={boxRef}>触发按钮 + 弹出的内容</div>
 *
 * 要点：
 * - ref 要挂在「触发按钮 + 弹出层」共同的包裹元素上。只挂弹出层会让点击触发按钮
 *   被判定成「外部点击」，跟按钮自身的 toggle 互相打架（关了又立刻开）。
 * - 多个互不相邻的元素（例如悬浮按钮和它弹出的面板）可以传数组：
 *   useClickOutside([fabRef, panelRef], () => setOpen(false), open)
 * - enabled 传 false 时不挂监听，关闭状态零开销。
 * - 监听 mousedown 而非 click：浮层里的条目常在 click 后立刻卸载自身
 *   （点了就关菜单并跳转），click 阶段的事件可能来不及冒泡到 document。
 */
export default function useClickOutside(refs, onOutside, enabled = true) {
  const cb = useRef(onOutside)
  useEffect(() => {
    cb.current = onOutside
  })

  useEffect(() => {
    if (!enabled) return undefined

    const list = Array.isArray(refs) ? refs : [refs]
    const handler = (e) => {
      const inside = list.some((r) => r && r.current && r.current.contains(e.target))
      if (inside) return
      cb.current(e)
    }

    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [refs, enabled])
}
