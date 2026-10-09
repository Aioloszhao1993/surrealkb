// 预设头像：内联 SVG（data URL），不依赖任何外部图片
const svg = (c1, c2, glyph) =>
  'data:image/svg+xml,' +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">` +
      `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">` +
      `<stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/>` +
      `</linearGradient></defs>` +
      `<rect width="96" height="96" rx="48" fill="url(#g)"/>` +
      `<text x="48" y="63" font-size="46" text-anchor="middle" fill="#ffffff" ` +
      `font-family="Segoe UI Symbol, Segoe UI Emoji, sans-serif">${glyph}</text></svg>`
  )

const entry = (id, name, c1, c2, glyph) => ({
  id,
  name,
  glyph,
  bg: `linear-gradient(135deg, ${c1}, ${c2})`,
  data: svg(c1, c2, glyph),
})

export const PRESET_AVATARS = [
  entry('aurora', '极光', '#9b59ff', '#00e5ff', '✦'),
  entry('nebula', '星云', '#ff5ca8', '#ffcd60', '✷'),
  entry('mint', '薄荷', '#00e5ff', '#34ffab', '⬡'),
  entry('sunset', '落日', '#ff6f91', '#9b59ff', '◉'),
  entry('moon', '夜月', '#60a5fa', '#c084fc', '☾'),
  entry('wave', '潮汐', '#22d3ee', '#7b5cff', '≈'),
  entry('flame', '炽焰', '#ff7a45', '#ff2d78', '◆'),
  entry('frost', '霜晶', '#a5f3fc', '#818cf8', '❄'),
]
