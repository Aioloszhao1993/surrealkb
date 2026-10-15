import { useEffect, useRef, useState } from 'react'
import { SCAN_EVENT } from '../scanPulse'

/** 扫描光带的存活时长，与 CSS 里 bdScan 的 1.1s 对齐、留一点余量，作为卸载兜底。 */
const SCAN_MS = 1500

/**
 * 超梦（Braindance）风格时间码，形如 14:22:07:13，纯装饰。
 * 每秒走一格，帧位在 00–23 之间循环——不追求真实帧率，只为还原 BD 回放的观感。
 */
function useBdTimecode() {
  const [tc, setTc] = useState('00:00:00:00')

  useEffect(() => {
    let frame = 0
    const p = (v) => String(v).padStart(2, '0')
    const tick = () => {
      const d = new Date()
      setTc(`${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}:${p(frame++ % 24)}`)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  return tc
}

/**
 * 全站背景层。
 *
 * 两层叠加：
 * 1) 品牌底色 —— 深空渐变 + 极光光球 + 星图网格（原有）
 * 2) 超梦（Braindance）叠层 —— 回放扫描线、扫描光带、偶发故障闪带、
 *    暗角，以及一圈 HUD（四角括号 / 时间码 / 进度轨 / 层级列表）。
 *
 * 扫描光带是**触发式**的（见 `src/scanPulse.js`）：平时静止待命，
 * 由用户「让机器去读知识库」的动作（搜索 / 提问 / 上传）唤起一次快速扫描。
 * 触发时递增 scanId，靠 key 让元素重建，动画自然从头播放，播完即卸载。
 *
 * 卸载有两条路：animationend 主动上报 + 一个 1.5s 的定时器兜底。
 * 只靠前者是不够的 —— 动画被禁用时（系统开了「减弱动态效果」、或元素被
 * 隐藏）不会派发 animationend，元素就会永久留在 DOM 里。
 *
 * 全部位于 `.bg`（`position: fixed; z-index: -1; pointer-events: none`）内
 * 并标注 aria-hidden，因此不参与交互、也不遮挡内容。
 * 动效只在纯 transform / opacity 上，并在 `prefers-reduced-motion: reduce` 下关闭。
 */
export default function Background() {
  const timecode = useBdTimecode()
  const [scanId, setScanId] = useState(0)
  const scanTimer = useRef(null)

  const endScan = () => {
    clearTimeout(scanTimer.current)
    setScanId(0)
  }

  useEffect(() => {
    const onScan = () => {
      // 尊重系统「减弱动态效果」：直接不播。CSS 里还有一层保险，这里省掉一次无谓渲染
      if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
      setScanId((v) => v + 1)
      clearTimeout(scanTimer.current)
      scanTimer.current = setTimeout(() => setScanId(0), SCAN_MS)
    }
    window.addEventListener(SCAN_EVENT, onScan)
    return () => {
      window.removeEventListener(SCAN_EVENT, onScan)
      clearTimeout(scanTimer.current)
    }
  }, [])

  return (
    <div className="bg" aria-hidden="true">
      <div className="orb orb-1" />
      <div className="orb orb-2" />
      <div className="orb orb-3" />
      <div className="grid-overlay" />

      {/* ---- 超梦（Braindance）叠层 ---- */}
      <div className="bd-scanlines" />
      {scanId > 0 && (
        <div className="bd-sweep run" key={scanId} onAnimationEnd={endScan} />
      )}
      <div className="bd-glitch" />
      <div className="bd-vignette" />

      <div className="bd-hud">
        <i className="bd-corner tl" />
        <i className="bd-corner tr" />
        <i className="bd-corner bl" />
        <i className="bd-corner br" />

        <div className="bd-meta">
          <span className="bd-meta-row">
            <i className="bd-dot" />
            <span className="bd-label">BD · Playback</span>
          </span>
          <span className="bd-timecode">{timecode}</span>
          <span className="bd-track">
            <i style={{ width: '38%' }} />
          </span>
        </div>

        <div className="bd-layers">
          <span className="bd-layer on">
            <i /> Visual
          </span>
          <span className="bd-layer">
            <i /> Audio
          </span>
          <span className="bd-layer">
            <i /> Thermal
          </span>
        </div>
      </div>

      <div className="noise" />
    </div>
  )
}
