import { createPortal } from 'react-dom'

/**
 * 把浮层渲染到 document.body。
 *
 * 为什么需要：`backdrop-filter`（以及 `transform` / `filter` / `will-change`）会让元素
 * 成为其内部 `position: fixed` 后代的「包含块」，同时形成新的层叠上下文。
 * 弹窗遮罩是 `position: fixed; inset: 0`，一旦被渲染进这类祖先里——例如 .navbar 与
 * .auth-card 都带 backdrop-filter——遮罩就只铺满那个祖先的盒子，而不是整个视口。
 * 表现是：弹窗看着弹出来了，但点页面空白处关不掉（遮罩根本没铺到那儿）。
 *
 * 挂到 body 上就没有这个约束，且不会受祖先层叠上下文压制。
 *
 * 用法（放在组件 return 的最外层，写法与原来几乎一致）：
 *   return portal(
 *     <div className="modal-back" onClick={onClose}>…</div>
 *   )
 */
export default function portal(node) {
  return createPortal(node, document.body)
}
