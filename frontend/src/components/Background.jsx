import { useEffect, useState } from 'react'

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
 * 2) 超梦（Braindance）叠层 —— 回放扫描线、自上而下的扫描光带、偶发故障闪带、
 *    暗角，以及一圈 HUD（四角括号 / 时间码 / 进度轨 / 层级列表）。
 *
 * 全部位于 `.bg`（`position: fixed; z-index: -1`）内并标注 aria-hidden，
 * 因此不参与交互、也不遮挡内容。动效只在纯 transform / opacity 上，
 * 并在 `prefers-reduced-motion: reduce` 下关闭。
 */
export default function Background() {
  const timecode = useBdTimecode()

  return (
    <div className="bg" aria-hidden="true">
      <div className="orb orb-1" />
      <div className="orb orb-2" />
      <div className="orb orb-3" />
      <div className="grid-overlay" />

      {/* ---- 超梦（Braindance）叠层 ---- */}
      <div className="bd-scanlines" />
      <div className="bd-sweep" />
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
