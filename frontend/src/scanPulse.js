/**
 * 背景「超梦扫描」的触发入口。
 *
 * 原本扫描光带是 11s 无限自动循环，只算氛围；改成触发式之后，它变成一种
 * **反馈信号** —— 机器真的开始读文档时才扫一次。
 *
 * ⚠️ 目前**只有「上传文档成功」**调用它。搜索与提问**不**触发，这是用户
 * 2026-10-15 明确要求的，别往那两处加回来（除非用户改主意）。
 *
 * 用 window 自定义事件解耦：调用方只管喊一声，后台的 Background 组件监听，
 * 不必把 state 从 App 层层透传到每个使用点。
 */
export const SCAN_EVENT = 'kb:scan'

/** 触发一次全屏扫描。重复触发会重新开始，不会叠加。 */
export function triggerScan() {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(SCAN_EVENT))
}
