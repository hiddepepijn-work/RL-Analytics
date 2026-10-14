import { VELD } from './veld.js'

export const KLEUR_CSS = ['#3d8bff', '#e06a12']
const BAL_STRIDE = 7

export function balOp(data, t) {
  const ts = data.t
  let lo = 0, hi = ts.length - 1
  while (hi - lo > 1) { const m = (lo + hi) >> 1; ts[m] <= t ? (lo = m) : (hi = m) }
  const i = lo * BAL_STRIDE
  return [data.bal[i], data.bal[i + 1], data.bal[i + 2]]
}

// Schoten: Shot-events, met als plek de bal bij de laatste touch van de schutter.
// Goal binnen 6 s door dezelfde speler = raak. Goals zonder Shot-event komen er los bij.
export function schoten(data) {
  const touches = data.events.filter((e) => e.soort === 'touch')
  const goals = data.events.filter((e) => e.soort === 'Goal')
  const plek = (e) => {
    const t = touches.filter((x) => x.speler === e.speler && x.tijd <= e.tijd + 0.15 && x.tijd > e.tijd - 4).at(-1)
    return balOp(data, t ? t.tijd : e.tijd)
  }
  const gebruikt = new Set()
  const lijst = data.events.filter((e) => e.soort === 'Shot').map((e) => {
    const g = goals.find((x) => !gebruikt.has(x) && x.speler === e.speler && x.tijd >= e.tijd && x.tijd - e.tijd < 6)
    if (g) gebruikt.add(g)
    return { ...e, goal: !!g, plek: plek(e) }
  })
  for (const g of goals) if (!gebruikt.has(g)) lijst.push({ ...g, goal: true, plek: plek(g) })
  return lijst.sort((a, b) => a.tijd - b.tijd)
}

export function scoreOp(data, t) {
  const s = [0, 0]
  for (const e of data.events) if (e.soort === 'Goal' && e.tijd <= t) s[e.team]++
  return s
}

// Diverging momentum (FotMob/Opta-stijl): staaf per 10 s, blauw boven, oranje onder.
export function tekenMomentum(canvas, data) {
  const dpr = devicePixelRatio || 1
  const w = canvas.clientWidth, h = canvas.clientHeight
  canvas.width = w * dpr; canvas.height = h * dpr
  const c = canvas.getContext('2d')
  c.scale(dpr, dpr)
  const t0 = data.t[0], t1 = data.t.at(-1), duur = t1 - t0
  const x = (t) => ((t - t0) / duur) * w
  const mid = h / 2, max = h / 2 - 14

  c.strokeStyle = '#222a37'; c.lineWidth = 1
  c.beginPath(); c.moveTo(0, mid + 0.5); c.lineTo(w, mid + 0.5); c.stroke()

  const BIN = 10
  const n = Math.ceil(duur / BIN)
  const som = new Float64Array(n), aantal = new Uint32Array(n)
  for (let i = 0; i < data.t.length; i++) {
    if (data.bal[i * BAL_STRIDE + 2] === 0) continue // bal afwezig (reset na goal)
    const b = Math.min(n - 1, Math.floor((data.t[i] - t0) / BIN))
    som[b] += data.bal[i * BAL_STRIDE + 1]; aantal[b]++
  }
  const breed = w / n
  for (let b = 0; b < n; b++) {
    const v = Math.max(-1, Math.min(1, som[b] / (aantal[b] || 1) / (VELD.lengte * 0.6)))
    const hoogte = Math.abs(v) * max
    c.fillStyle = v >= 0 ? KLEUR_CSS[0] : KLEUR_CSS[1]
    c.globalAlpha = 0.35 + Math.abs(v) * 0.6
    const y = v >= 0 ? mid - hoogte : mid + 1
    rondeRect(c, b * breed + 1, y, breed - 2, Math.max(hoogte, 1), 2)
  }
  c.globalAlpha = 1

  // Markers: schoten als streepjes, goals als stip met lijn, demo's als kruisje
  for (const s of schoten(data)) {
    const px = x(s.tijd), boven = s.team === 0
    if (s.goal) {
      c.strokeStyle = 'rgba(230,235,242,.25)'
      c.beginPath(); c.moveTo(px, 10); c.lineTo(px, h - 10); c.stroke()
      c.fillStyle = KLEUR_CSS[s.team]; c.strokeStyle = '#0a0d13'; c.lineWidth = 2
      c.beginPath(); c.arc(px, boven ? 7 : h - 7, 5.5, 0, Math.PI * 2); c.fill(); c.stroke(); c.lineWidth = 1
    } else {
      c.fillStyle = KLEUR_CSS[s.team]
      c.fillRect(px - 1, boven ? 2 : h - 8, 2, 6)
    }
  }
  for (const d of data.events.filter((e) => e.soort === 'demolition')) {
    const px = x(d.tijd), py = d.team === 0 ? mid - 4 : mid + 4
    c.strokeStyle = '#e6ebf2'; c.globalAlpha = 0.6
    c.beginPath(); c.moveTo(px - 3, py - 3); c.lineTo(px + 3, py + 3); c.moveTo(px + 3, py - 3); c.lineTo(px - 3, py + 3); c.stroke()
    c.globalAlpha = 1
  }
}

function rondeRect(c, x, y, w, h, r) {
  c.beginPath(); c.roundRect ? c.roundRect(x, y, w, h, r) : c.rect(x, y, w, h); c.fill()
}

// Schotkaart: bovenaanzicht, oranje doel boven (blauw valt naar boven aan). Cirkeloppervlak ∝ xG.
export function tekenSchotkaart(svg, data, spelerNaam) {
  const { breedte: b, lengte: l, hoek: k, doelBreedte: dw, doelDiepte: dd } = VELD
  const pt = (x, y) => `${x},${-y}`
  const omtrek = [[-b + k, -l], [b - k, -l], [b, -l + k], [b, l - k], [b - k, l], [-b + k, l], [-b, l - k], [-b, -l + k]]
  const metXg = data.schoten?.length && data.schoten[0].xg != null
  const lijst = metXg ? data.schoten : schoten(data)
  const plek = (sch) => sch.plek
  const straal = (sch) => (metXg ? 110 + 560 * Math.sqrt(sch.xg) : 190)
  let s = `
    <defs>
      <linearGradient id="hb" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#3d8bff" stop-opacity=".10"/><stop offset=".5" stop-color="#3d8bff" stop-opacity="0"/><stop offset=".5" stop-color="#e06a12" stop-opacity="0"/><stop offset="1" stop-color="#e06a12" stop-opacity=".10"/></linearGradient>
    </defs>
    <polygon points="${omtrek.map(([x, y]) => pt(x, y)).join(' ')}" fill="url(#hb)" stroke="#2c3747" stroke-width="28"/>
    <line x1="${-b}" y1="0" x2="${b}" y2="0" stroke="#2c3747" stroke-width="20"/>
    <circle cx="0" cy="0" r="1000" fill="none" stroke="#2c3747" stroke-width="20"/>
    <rect x="${-dw}" y="${-l - dd}" width="${2 * dw}" height="${dd}" fill="rgba(224,106,18,.15)" stroke="#e06a12" stroke-width="24"/>
    <rect x="${-dw}" y="${l}" width="${2 * dw}" height="${dd}" fill="rgba(61,139,255,.15)" stroke="#3d8bff" stroke-width="24"/>`
  // kleine schoten eerst, zodat grote kansen bovenop liggen
  const gesorteerd = [...lijst].sort((a, c) => (a.xg ?? 0) - (c.xg ?? 0))
  for (const sch of gesorteerd) {
    const [x, y] = plek(sch)
    const kl = KLEUR_CSS[sch.team]
    const titel = `${spelerNaam(sch.speler)} · ${sch.goal ? 'goal' : 'schot'}${metXg ? ` · xG ${sch.xg.toFixed(2)}${sch.xgot != null ? ` · xGOT ${sch.xgot.toFixed(2)}` : ' · naast'}` : ''} · ${Math.round(sch.tijd - data.t[0])} s`
    const k = metXg ? data.schoten.indexOf(sch) : -1
    s += `<circle class="schot-punt" ${k >= 0 ? `data-schot="${k}"` : ''} cx="${x}" cy="${-y}" r="${straal(sch)}" fill="${sch.goal ? kl : 'rgba(10,13,19,.55)'}" fill-opacity="${sch.goal ? 0.9 : 1}" stroke="${kl}" stroke-width="34"><title>${titel}</title></circle>`
  }
  // Gemiste kansen door een whiff: stippelcirkel (geen schot, wel een kans)
  for (const [ki, k] of (metXg ? data.kansen?.gemist ?? [] : []).entries()) {
    const [x, y] = k.plek
    const titel = `${spelerNaam(k.speler)} · whiff · kans-xG ${k.kans_xg.toFixed(2)} · ${Math.round(k.tijd - data.t[0])} s`
    s += `<circle class="schot-punt" data-whiff="${ki}" cx="${x}" cy="${-y}" r="${straal({ xg: k.kans_xg })}" fill="rgba(0,0,0,0.001)" stroke="${KLEUR_CSS[k.team]}" stroke-width="30" stroke-dasharray="70 55" opacity=".85"><title>${titel}</title></circle>`
  }
  svg.innerHTML = s
  const per = [0, 1].map((t) => lijst.filter((x) => x.team === t))
  const som = (a) => a.reduce((z, x) => z + (x.xg ?? 0), 0).toFixed(1).replace('.', ',')
  return metXg
    ? `xG ${som(per[0])} – ${som(per[1])} · ${per[0].length} vs ${per[1].length} schoten`
    : `${per[0].length} vs ${per[1].length} schoten · ${per[0].filter((x) => x.goal).length} – ${per[1].filter((x) => x.goal).length} goals`
}

// xG-verloop (Understat): cumulatieve trap-lijn per team, goals als stip.
export function tekenXgVerloop(svg, data) {
  if (!data.schoten?.length || data.schoten[0].xg == null) { svg.innerHTML = ''; return '' }
  const W = Math.max(320, svg.clientWidth || 600), H = 200, p = { l: 30, r: 14, t: 12, b: 22 }
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`)
  const t0 = data.t[0], t1 = data.t.at(-1)
  const x = (t) => p.l + ((t - t0) / (t1 - t0)) * (W - p.l - p.r)
  const totalen = [0, 1].map((tm) => data.schoten.filter((s) => s.team === tm).reduce((a, s) => a + s.xg, 0))
  const max = Math.max(1, ...totalen) * 1.08
  const y = (v) => p.t + (1 - v / max) * (H - p.t - p.b)
  let s = ''
  for (let v = 0; v <= max; v += max > 4 ? 1 : 0.5) s += `<line x1="${p.l}" x2="${W - p.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--rand)"/><text x="${p.l - 6}" y="${y(v)}" text-anchor="end" dominant-baseline="middle" class="as-tekst">${String(v).replace('.', ',')}</text>`
  for (const tm of [0, 1]) {
    let cum = 0, pad = `M${x(t0)},${y(0)}`
    const stippen = []
    for (const sch of data.schoten.filter((q) => q.team === tm)) {
      pad += ` H${x(sch.tijd)}`; cum += sch.xg; pad += ` V${y(cum)}`
      if (sch.goal) stippen.push([x(sch.tijd), y(cum)])
    }
    pad += ` H${x(t1)}`
    s += `<path d="${pad}" fill="none" stroke="${KLEUR_CSS[tm]}" stroke-width="2" stroke-linejoin="round"/>`
    for (const [gx, gy] of stippen) s += `<circle cx="${gx}" cy="${gy}" r="5" fill="${KLEUR_CSS[tm]}" stroke="var(--paneel)" stroke-width="2"/>`
    s += `<text x="${W - p.r}" y="${y(cum) - 8}" text-anchor="end" class="as-tekst" fill="var(--tekst)">${cum.toFixed(2).replace('.', ',')}</text>`
  }
  for (let m = 0; m <= Math.floor((t1 - t0) / 60); m++) s += `<text x="${x(t0 + m * 60)}" y="${H - 4}" text-anchor="middle" class="as-tekst">${m}'</text>`
  svg.innerHTML = s
  return `${totalen[0].toFixed(2).replace('.', ',')} – ${totalen[1].toFixed(2).replace('.', ',')}`
}
