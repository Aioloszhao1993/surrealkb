/**
 * 背景「超梦扫描」的触发入口。
 *
 * 原本背景里的扫描光带是 11s 无限自动循环，只算氛围；改成触发式之后，
 * 它变成一种**反馈信号** —— 用户做了「让机器去读知识库」的动作时扫一次，
 * 比无脑循环更有「正在读取」的暗示。
 *
 * 用 window 自定义事件解耦：任何组件都能触发，后台的 Background 组件监听，
 * 不必把 state 从 App 层层透传下去，也就不影响现有的组件结构。
 */
export const SCAN_EVENT = 'kb:scan'

/** 触发一次全屏扫描。重复触发会重新开始，不会叠加。 */
export function triggerScan() {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(SCAN_EVENT))
}
