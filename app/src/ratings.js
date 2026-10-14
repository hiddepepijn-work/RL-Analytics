// Ratings: live cijfer per speler, rating-verloop en het Ratings-tabblad.
// Cijfers komen uit kern/rating.py (data.rating): 6,5 = rank-gemiddelde, ≥8 uitstekend, schaal 3–10.
import { KLEUR_CSS } from './grafieken.js'

const ONDERDELEN = ['Schieten', 'Passen', 'Verdedigen', 'Duels', 'Kickoffs', 'Balbezit']
const STAT_ID = { Schieten: 'impact.r_schieten', Passen: 'impact.r_passen', Verdedigen: 'impact.r_verdedigen', Duels: 'impact.r_duels', Kickoffs: 'impact.r_kickoffs', Balbezit: 'impact.r_balbezit' }
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
const nl = (v, d = 1) => Number(v).toLocaleString('nl-NL', { minimumFractionDigits: d, maximumFractionDigits: d })
const klok = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`

export const ratingKlasse = (r) => r == null ? 'r-geen' : r >= 8 ? 'r-top' : r >= 7 ? 'r-goed' : r >= 6 ? 'r-gem' : r >= 5 ? 'r-onder' : 'r-slecht'

/** Cijfer van speler sid op replay-tijd t (null vóór de eerste minuut). */
export function ratingOp(data, sid, t) {
  const tl = data.rating?.spelers?.[sid]?.tijdlijn
  if (!tl?.length || t < tl[0][0]) return null
  let lo = 0, hi = tl.length - 1
  while (lo < hi) { const m = (lo + hi + 1) >> 1; tl[m][0] <= t ? (lo = m) : (hi = m - 1) }
  return tl[lo][1]
}

// Kleur per speler: teamkleur, tweede speler lichter (identiteit = team, geen extra tinten)
const LICHT = ['#9cc4ff', '#f5ad73']
export function spelerKleuren(data) {
  const per = [0, 0], uit = {}
  for (const s of data.spelers) { uit[s.id] = per[s.team]++ === 0 ? KLEUR_CSS[s.team] : LICHT[s.team] }
  return uit
}

/** Rating-verloop: lijn per speler, playhead + hover-crosshair. Geeft {zetT} terug. */
export function tekenRatingVerloop(el, data) {
  if (!data.rating) { el.innerHTML = '<div class="dim">Geen rating beschikbaar</div>'; return { zetT() {} } }
  const W = Math.max(320, el.clientWidth || 700), H = 220, p = { l: 30, r: 110, t: 12, b: 22 }
  const t0 = data.t[0], t1 = data.t.at(-1)
  const x = (t) => p.l + ((t - t0) / (t1 - t0)) * (W - p.l - p.r)
  const y = (v) => p.t + (1 - (v - 3) / 7) * (H - p.t - p.b)
  const kleur = spelerKleuren(data)
  let s = ''
  for (const v of [4, 5, 6, 7, 8, 9]) s += `<line x1="${p.l}" x2="${W - p.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--rand)" ${v === 6.5 ? '' : ''}/><text x="${p.l - 6}" y="${y(v)}" text-anchor="end" dominant-baseline="middle" class="as-tekst">${v}</text>`
  s += `<line x1="${p.l}" x2="${W - p.r}" y1="${y(6.5)}" y2="${y(6.5)}" stroke="var(--tekst-3)" stroke-dasharray="3 4"/><text x="${W - p.r + 4}" y="${y(6.5)}" dominant-baseline="middle" class="as-tekst">rank-gem.</text>`
  const eindLabels = []
  for (const sp of data.spelers) {
    const tl = data.rating.spelers[sp.id]?.tijdlijn ?? []
    if (!tl.length) continue
    s += `<polyline points="${tl.map(([t, v]) => `${x(t).toFixed(1)},${y(v).toFixed(1)}`).join(' ')}" fill="none" stroke="${kleur[sp.id]}" stroke-width="2" stroke-linejoin="round" class="rv-lijn"/>`
    eindLabels.push([y(tl.at(-1)[1]), sp, tl.at(-1)[1]])
  }
  // Labels aan het eind, uit elkaar geschoven als ze overlappen
  eindLabels.sort((a, b) => a[0] - b[0])
  for (let i = 1; i < eindLabels.length; i++) if (eindLabels[i][0] - eindLabels[i - 1][0] < 13) eindLabels[i][0] = eindLabels[i - 1][0] + 13
  for (const [ly, sp, v] of eindLabels) s += `<text x="${W - p.r + 8}" y="${ly}" dominant-baseline="middle" class="rv-label"><tspan fill="${kleur[sp.id]}">●</tspan> ${esc(sp.naam.slice(0, 12))} <tspan class="num" fill="var(--tekst)">${nl(v)}</tspan></text>`
  for (let m = 0; m <= Math.floor((t1 - t0) / 60); m++) s += `<text x="${x(t0 + m * 60)}" y="${H - 4}" text-anchor="middle" class="as-tekst">${m}'</text>`
  s += `<line class="rv-kop" x1="0" x2="0" y1="${p.t}" y2="${H - p.b}"/><g class="rv-hover" opacity="0"><line x1="0" x2="0" y1="${p.t}" y2="${H - p.b}" stroke="var(--tekst-3)"/></g>`
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="lijngrafiek rv">${s}</svg><div class="rv-tip"></div>`
  const svg = el.querySelector('svg'), kop = svg.querySelector('.rv-kop'), hover = svg.querySelector('.rv-hover'), tip = el.querySelector('.rv-tip')
  svg.addEventListener('pointermove', (e) => {
    const r = svg.getBoundingClientRect(), sx = ((e.clientX - r.left) / r.width) * W
    const t = t0 + ((sx - p.l) / (W - p.l - p.r)) * (t1 - t0)
    if (t < t0 || t > t1) return
    hover.setAttribute('opacity', 1); hover.firstElementChild.setAttribute('x1', sx); hover.firstElementChild.setAttribute('x2', sx)
    const rijen = data.spelers.map((sp) => [sp, ratingOp(data, sp.id, t)]).filter(([, v]) => v != null).sort((a, b) => b[1] - a[1])
    tip.innerHTML = `<div class="dim">${klok(t - t0)}</div>${rijen.map(([sp, v]) => `<div><i style="background:${kleur[sp.id]}"></i>${esc(sp.naam)} <b class="num ${ratingKlasse(v)}-tekst">${nl(v)}</b></div>`).join('') || '<div class="dim">nog geen cijfer (na 1 min)</div>'}`
    tip.style.left = `${Math.min(r.width - 170, Math.max(0, e.clientX - r.left + 12))}px`
    tip.classList.add('zichtbaar')
  })
  svg.addEventListener('pointerleave', () => { hover.setAttribute('opacity', 0); tip.classList.remove('zichtbaar') })
  return { zetT(t) { const px = x(Math.max(t0, Math.min(t1, t))); kop.setAttribute('x1', px); kop.setAttribute('x2', px) }, svg }
}

/** Ratings-tabblad: per speler eindcijfer, cijfer per onderdeel en de acties die het bepaalden. */
export function tekenRatingsTab(el, data, opSpring) {
  if (!data.rating) { el.innerHTML = '<div class="kaart dim">Deze wedstrijd heeft nog geen rating (opnieuw verwerken).</div>'; return }
  const kleur = spelerKleuren(data)
  const spelers = [...data.spelers].sort((a, b) => (data.rating.spelers[b.id]?.eind ?? 0) - (data.rating.spelers[a.id]?.eind ?? 0))
  const t0 = data.t[0]
  el.innerHTML = `
    <div class="kaart rating-uitleg"><div class="kaart-kop"><h3>Hoe werkt de rating?</h3><span class="sub" data-stat="impact.rating">ⓘ volledige uitleg</span></div>
      <p class="dim">Elke actie levert plus- of minpunten op (in goal-equivalenten). Het cijfer vergelijkt jouw punten met een gemiddelde speler van deze rank op hetzelfde moment: <b>6,5 = gemiddeld</b>, 7+ goed, 8+ uitstekend, onder 6 zwak. Vanaf 1 minuut speeltijd zichtbaar; daarna beweegt het mee met elke actie.</p>
      ${data.rating.norm_band ? '' : '<p class="pop-laag" style="margin:6px 0 0">Voorlopige normen: cijfers worden nauwkeuriger zodra de rank-normen berekend zijn.</p>'}
    </div>
    <div class="ratings-raster">${spelers.map((sp) => {
      const r = data.rating.spelers[sp.id]
      if (!r) return ''
      const top = [...r.acties].sort((a, b) => Math.abs(b[2]) - Math.abs(a[2])).slice(0, 6).sort((a, b) => a[0] - b[0])
      return `<div class="kaart rating-kaart" style="--kl:${kleur[sp.id]}">
        <div class="rk-kop">
          <div><div class="rk-naam">${esc(sp.naam)}</div><div class="dim" style="font-size:12px">${r.acties.length} acties · impact <span class="num">${r.impact > 0 ? '+' : ''}${nl(r.impact, 2)}</span> goals</div></div>
          <span class="rating-groot-badge ${ratingKlasse(r.eind)}" data-stat="impact.rating"><span data-tel="${r.eind ?? 0}" data-dec="1">${r.eind != null ? nl(r.eind) : '–'}</span></span>
        </div>
        <div class="rk-onderdelen">${ONDERDELEN.map((o) => {
          const c = r.onderdelen[o]?.cijfer, imp = r.onderdelen[o]?.impact ?? 0
          return `<div class="rk-rij" data-stat="${STAT_ID[o]}"><span>${o}</span>
            <div class="rk-spoor"><i class="${ratingKlasse(c)}" style="width:${c == null ? 0 : ((c - 3) / 7) * 100}%"></i><b style="left:${((6.5 - 3) / 7) * 100}%"></b></div>
            <span class="num ${ratingKlasse(c)}-tekst">${c != null ? nl(c) : '–'}</span><span class="num dim rk-imp">${imp > 0 ? '+' : ''}${nl(imp, 2)}</span></div>`
        }).join('')}</div>
        <div class="rk-acties-kop">Belangrijkste momenten</div>
        <ul class="rk-acties">${top.map(([t, o, w, oms]) => `<li data-t="${t}"><span class="num dim">${klok(t - t0)}</span><span class="rk-delta ${w >= 0 ? 'plus' : 'min'}">${w >= 0 ? '+' : ''}${nl(w, 2)}</span><span>${esc(oms)}</span><span class="dim">${o}</span></li>`).join('') || '<li class="dim">Geen acties</li>'}</ul>
      </div>`
    }).join('')}</div>`
  el.querySelectorAll('.rk-acties li[data-t]').forEach((li) => li.addEventListener('click', () => opSpring(Number(li.dataset.t))))
}
