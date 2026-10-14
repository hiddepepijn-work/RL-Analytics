// Premium-laag: uitleg-popover bij elke stat, optellende cijfers, rustige opkomst-animaties, laad-skeletons.
// Alles respecteert prefers-reduced-motion.
import { GROEPEN } from './catalogus.js'

const ALLE = Object.fromEntries(GROEPEN.flatMap((g) => g.stats.map((s) => [`${g.id}.${s.id}`, s])))
const PAD = Object.fromEntries(GROEPEN.flatMap((g) => g.stats.filter((s) => s.pad).map((s) => [s.pad, s])))
const rustig = () => matchMedia('(prefers-reduced-motion: reduce)').matches
export const statSleutel = (stat) => `${stat.groep}.${stat.id}`
export const statOpPad = (pad) => PAD[pad]

// ── Uitleg-popover ──────────────────────────────────────────────────────────
// Gebruik: data-stat="groep.id" (uit de catalogus) of data-uitleg="tekst" (+ optioneel data-titel)
let pop = null, timer = null, huidig = null
export function initUitleg() {
  pop = document.createElement('div')
  pop.className = 'uitleg-pop'
  pop.setAttribute('role', 'tooltip')
  document.body.appendChild(pop)
  const doelVan = (e) => e.target.closest?.('[data-stat],[data-uitleg]')
  document.addEventListener('pointerover', (e) => {
    const el = doelVan(e)
    if (!el || el === huidig) return
    clearTimeout(timer)
    timer = setTimeout(() => toon(el), huidig ? 0 : 160)
  })
  document.addEventListener('pointerout', (e) => {
    const el = doelVan(e)
    if (el && !el.contains(e.relatedTarget)) { clearTimeout(timer); verberg() }
  })
  // Telefoon: tikken toont/verbergt
  document.addEventListener('click', (e) => {
    const el = doelVan(e)
    if (el && matchMedia('(hover: none)').matches) { el === huidig ? verberg() : toon(el) }
  })
  addEventListener('scroll', verberg, true)
}
function verberg() { huidig = null; pop?.classList.remove('zichtbaar') }
function toon(el) {
  const st = ALLE[el.dataset.stat]
  const titel = st?.label ?? el.dataset.titel ?? ''
  const tekst = st?.uitleg ?? el.dataset.uitleg ?? ''
  if (!tekst) return
  const richting = !st ? '' : st.beter === 'hoog' ? '<span class="pop-goed">↑ hoger is beter</span>'
    : st.beter === 'laag' ? '<span class="pop-laag">↓ lager is beter</span>' : '<span class="pop-neutraal">stijl, geen goed of slecht</span>'
  pop.innerHTML = `<div class="pop-titel">${titel}</div><div class="pop-tekst">${tekst}</div>
    ${st ? `<div class="pop-voet">${richting}${st.voetbal ? `<span class="pop-chip">voetbal: ${st.voetbal}</span>` : ''}${st.status !== 'ok' && !st.pad ? '<span class="pop-chip">nog niet beschikbaar</span>' : ''}</div>` : ''}`
  huidig = el
  pop.classList.remove('zichtbaar')
  const r = el.getBoundingClientRect()
  pop.style.left = '0px'; pop.style.top = '0px'
  const pw = pop.offsetWidth, ph = pop.offsetHeight
  const x = Math.min(innerWidth - pw - 12, Math.max(12, r.left + r.width / 2 - pw / 2))
  let y = r.top - ph - 10, onder = false
  if (y < 8) { y = r.bottom + 10; onder = true }
  pop.style.left = `${x}px`; pop.style.top = `${y}px`
  pop.dataset.onder = onder
  requestAnimationFrame(() => pop.classList.add('zichtbaar'))
}

// ── Optellende cijfers ──────────────────────────────────────────────────────
// <span data-tel="12.5" data-dec="1" data-suf="%"></span>
const nl = (v, d) => Number(v).toLocaleString('nl-NL', { minimumFractionDigits: d, maximumFractionDigits: d })
export function telOp(root = document) {
  root.querySelectorAll('[data-tel]').forEach((el) => {
    const doel = Number(el.dataset.tel), d = Number(el.dataset.dec ?? 0), suf = el.dataset.suf ?? ''
    if (!Number.isFinite(doel)) return
    if (rustig()) { el.textContent = nl(doel, d) + suf; return }
    const t0 = performance.now(), duur = 380 + Math.min(220, Math.abs(doel) * 2)
    const stap = (nu) => {
      const f = Math.min(1, (nu - t0) / duur), e = 1 - Math.pow(1 - f, 3)
      el.textContent = nl(doel * e, d) + suf
      if (f < 1) requestAnimationFrame(stap)
    }
    requestAnimationFrame(stap)
  })
}

// ── Opkomst: kaarten faden rustig in, kort na elkaar ────────────────────────
export function opkomst(root, selector = '.kaart, .vgl, .tegel, .goal, .stats-groep, .cat-groep, .hm-kaart, .rating-kaart') {
  if (!root || rustig()) return
  // Eerst alles lezen, dan alles schrijven, met één reflow ertussen (per element offsetWidth lezen gaf N layouts)
  const els = [...root.querySelectorAll(selector)].filter((el) => el.offsetParent !== null)
  els.forEach((el) => el.classList.remove('opkomst'))
  void root.offsetWidth
  els.forEach((el, i) => { el.style.setProperty('--i', Math.min(i, 8)); el.classList.add('opkomst') })
}

// ── Laad-skeleton ───────────────────────────────────────────────────────────
export function skelet(el, { regels = 5, kaarten = 0 } = {}) {
  if (!el) return
  const r = Array.from({ length: regels }, (_, i) => `<div class="skelet-regel" style="width:${92 - (i % 3) * 14}%"></div>`).join('')
  const k = Array.from({ length: kaarten }, () => `<div class="skelet-kaart"><div class="skelet-regel" style="width:40%"></div><div class="skelet-blok"></div></div>`).join('')
  el.innerHTML = `<div class="skelet">${k ? `<div class="skelet-raster">${k}</div>` : ''}${r}</div>`
}

// Ripple-vrij "indruk"-effect en klikgeluid zijn bewust weggelaten: ingetogen, geen gloed.
