import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
import '@fontsource-variable/space-grotesk'
import '@fontsource/instrument-serif'
import './stijl.css'
import './premium.css'
import { Viewer } from './viewer.js'
import { KLEUR_CSS, scoreOp, tekenMomentum, tekenSchotkaart, tekenXgVerloop } from './grafieken.js'
import { tekenProfiel } from './profiel_echt.js'
import { tekenModellen } from './modellen.js'
import { initUitleg, telOp, opkomst, skelet } from './premium.js'
import { ratingOp, ratingKlasse, tekenRatingVerloop, tekenRatingsTab } from './ratings.js'
import { tekenHero, tekenKernstrip, tekenGoals, tekenTeamstats, tekenSpelertabel, tekenPositie, tekenBoost, tekenCatalogus, playlistNaam, wedstrijdKlok } from './wedstrijd.js'

const $ = (id) => document.getElementById(id)
const MARKANT = { Goal: ['G', 1], Shot: ['S', 0.75], Save: ['R', 0.75], demolition: ['D', 0.6], flip_reset: ['F', 0.6], air_dribble: ['A', 0.6], ceiling_shot: ['C', 0.6], double_tap: ['2', 0.6] }
const EVENT_NAAM = { Goal: 'Goal', Shot: 'Schot', Save: 'Redding', demolition: 'Demo', flip_reset: 'Flip reset', air_dribble: 'Air dribble', ceiling_shot: 'Ceiling shot', double_tap: 'Double tap' }

const params = new URLSearchParams(location.search)
const viewer = new Viewer($('viewer'))
const staat = { data: null, t: 0, speelt: params.get('speel') !== '0', snelheid: 1, laatste: performance.now(), tab: params.get('tab') ?? 'overzicht', tabel: { groep: params.get('groep') ?? 'schieten' } }

const klok = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
const naam = (id) => staat.spelerOpId?.[id]?.naam ?? '?'

// ── Thema ──
function zetThema(t) {
  document.documentElement.dataset.thema = t
  $('themas').querySelectorAll('button').forEach((b) => b.classList.toggle('actief', b.dataset.thema === t))
  try { localStorage.setItem('thema', t) } catch {}
  if (staat.data) tekenMomentum($('momentum'), staat.data)
}
$('themas').onclick = (e) => { const b = e.target.closest('button'); if (b) zetThema(b.dataset.thema) }
let bewaard = null
try { bewaard = localStorage.getItem('thema') } catch {}
zetThema(params.get('thema') ?? bewaard ?? 'arena')

// ── Data ──
// Wedstrijdlijst: eigen wedstrijden eerst, nieuwste bovenaan. Ververst zichzelf (nieuwe replays van de desktop-app
// verschijnen zonder herladen); de wedstrijd die je bekijkt blijft staan.
async function haalIndex() {
  const index = await (await fetch('/verwerkt/index.json', { cache: 'no-cache' })).json()
  index.sort((a, b) => (b.eigen ? 1 : 0) - (a.eigen ? 1 : 0) || String(b.datum ?? '').localeCompare(String(a.datum ?? '')))
  return index
}

function tekenLijst(index) {
  const sleutel = index.map((r) => r.naam).join()
  if (sleutel === staat.lijstSleutel) return
  staat.lijstSleutel = sleutel
  $('replaylijst').innerHTML = index.map((r) => `
    <li class="replay${r.bestand === staat.bestand ? ' actief' : ''}" data-bestand="${r.bestand}">
      <div class="replay-score"><span class="b">${r.score[0]}</span><span class="dim">–</span><span class="o">${r.score[1]}</span>
        ${r.eigen ? `<span class="replay-mijn ${r.uitslag === 'W' ? 'w' : 'v'}">${r.uitslag === 'W' ? 'W' : 'V'}</span>` : ''}<span class="replay-pl">${esc(playlistNaam(r))}</span></div>
      <div class="replay-sub">${esc(r.spelers.filter((s) => s.team === 0).map((s) => s.naam).join(', '))}</div>
    </li>`).join('')
}

async function start() {
  const index = await haalIndex()
  tekenLijst(index)
  $('replaylijst').onclick = (e) => { const li = e.target.closest('.replay'); if (li) { laad(li.dataset.bestand); toonView('wedstrijd') } }
  setInterval(() => haalIndex().then(tekenLijst).catch(() => {}), 30000)
  const gekozen = index.find((r) => r.naam === params.get('replay')) ?? index[0]
  if (gekozen) await laad(gekozen.bestand)
}

async function laad(bestand) {
  document.querySelectorAll('.replay').forEach((li) => li.classList.toggle('actief', li.dataset.bestand === bestand))
  staat.bestand = bestand
  $('viewerladen').classList.add('aan')
  if (!staat.data) { skelet($('hero'), { regels: 3 }); skelet($('kernstrip'), { regels: 1 }) }
  const data = await (await fetch(`/verwerkt/${bestand}`)).json()
  $('viewerladen').classList.remove('aan')
  staat.data = data
  staat.t = params.has('t') ? data.t[0] + Number(params.get('t')) : data.t[0]
  staat.spelerOpId = Object.fromEntries(data.spelers.map((s) => [s.id, s]))
  viewer.laad(data)
  if (!$('view-wedstrijd').hidden) $('kruimel').innerHTML = `Wedstrijden <span class="dim">/</span> ${esc(playlistNaam(data.meta))} <span class="num">${data.meta.score[0]}–${data.meta.score[1]}</span>`
  tekenHero($('hero'), data)
  tekenKernstrip($('kernstrip'), data)
  tekenSpelersLive()
  tekenEvents()
  tekenGoals($('goals'), data, naam)
  document.querySelector('.schot-pop')?.remove()
  $('schotensub').textContent = tekenSchotkaart($('schotkaart'), data, naam)
  $('xgsub').textContent = tekenXgVerloop($('xgverloop'), data)
  tekenTeamstats($('teamstats'), data)
  tekenTabel()
  tekenPositie($('positie'), data)
  tekenBoost($('boosttab'), data)
  staat.rv = tekenRatingVerloop($('ratingverloop'), data)
  staat.ratingsGetekend = false
  staat.vorigeRating = {}
  toonTab(staat.tab)
  telOp($('hero'))
  opkomst($('view-wedstrijd'))
}

function tekenTabel() {
  tekenSpelertabel($('spelertabel'), staat.data, staat.tabel.groep, staat.tabel, (keuze) => { staat.tabel = keuze; tekenTabel() })
}

function tekenSpelersLive() {
  const d = staat.data
  vorigeHud.clear()  // nieuwe boost-/cijferelementen
  const groep = (t) => d.spelers.map((s, k) => [s, k]).filter(([s]) => s.team === t).sort(([a], [b]) => b.stats.Score - a.stats.Score).map(([s, k]) => `
      <div class="speler">
        <span class="speler-streep" style="background:${KLEUR_CSS[t]}"></span>
        <div style="min-width:0">
          <div class="speler-naam">${esc(s.naam)}</div>
          <div class="speler-boost"><i id="boost${k}"></i></div>
        </div>
        <div class="speler-stats num"><span><b>G</b>${s.stats.Goals}</span><span><b>A</b>${s.stats.Assists}</span><span><b>R</b>${s.stats.Saves}</span><span><b>S</b>${s.stats.Shots}</span></div>
        <span class="rating-live r-geen num" id="rating${k}" title="Live cijfer">–</span>
      </div>`).join('')
  $('spelers').innerHTML = `<div class="team-groep">${groep(0)}</div><div class="team-groep">${groep(1)}</div>`
}

function tekenEvents() {
  const d = staat.data
  $('eventlijst').innerHTML = d.events.filter((e) => MARKANT[e.soort]).map((e) => {
    const [letter, alpha] = MARKANT[e.soort]
    return `<li class="event" data-t="${e.tijd}">
      <span class="num">${klok(Math.round(e.tijd - d.t[0]))}</span>
      <span class="event-icoon" style="background:${KLEUR_CSS[e.team]};opacity:${alpha}">${letter}</span>
      <span>${EVENT_NAAM[e.soort]} <span class="dim">· ${esc(naam(e.speler))}</span></span></li>`
  }).join('')
}
const springNaar = (t) => { staat.t = t - 3; toonTab('overzicht') }
$('eventlijst').onclick = (e) => { const li = e.target.closest('.event'); if (li) springNaar(Number(li.dataset.t)) }
$('goals').onclick = (e) => { const b = e.target.closest('.goal'); if (b) springNaar(Number(b.dataset.t)) }

// ── Navigatie ──
function toonTab(tab) {
  staat.tab = tab
  document.querySelectorAll('section.tab').forEach((s) => (s.hidden = s.dataset.tab !== tab))
  const knop = $('tabs').querySelector(`[data-tab="${tab}"]`)
  $('tabs').querySelectorAll('button').forEach((b) => b.classList.toggle('actief', b === knop))
  if (knop) Object.assign($('tabsstreep').style, { left: knop.offsetLeft + 'px', width: knop.offsetWidth + 'px' })
  if (tab === 'overzicht' && staat.data) requestAnimationFrame(() => { viewer.pasGrootteAan(); tekenMomentum($('momentum'), staat.data); tekenXgVerloop($('xgverloop'), staat.data); staat.rv = tekenRatingVerloop($('ratingverloop'), staat.data) })
  if (tab === 'ratings' && staat.data && !staat.ratingsGetekend) { tekenRatingsTab($('ratingstab'), staat.data, springNaar); staat.ratingsGetekend = true; telOp($('ratingstab')) }
  const sectie = document.querySelector(`section.tab[data-tab="${tab}"]`)
  if (sectie && staat.data) opkomst(sectie)
}
$('tabs').onclick = (e) => { const b = e.target.closest('button'); if (b) toonTab(b.dataset.tab) }

function toonView(view) {
  document.querySelectorAll('.nav-item[data-view]').forEach((a) => a.classList.toggle('actief', a.dataset.view === view))
  for (const v of ['wedstrijd', 'spelers', 'catalogus', 'modellen']) $('view-' + v).hidden = v !== view
  if (view === 'modellen') tekenModellen($('view-modellen')).then(() => opkomst($('view-modellen')))
  if (view === 'spelers' && !$('view-spelers').childElementCount) { skelet($('view-spelers'), { kaarten: 6, regels: 6 }); tekenProfiel($('view-spelers')).then(() => { telOp($('view-spelers')); opkomst($('view-spelers')) }) }
  else if (view === 'spelers') opkomst($('view-spelers'))
  if (view === 'catalogus' && !$('view-catalogus').childElementCount) tekenCatalogus($('view-catalogus'))
  if (view === 'catalogus') opkomst($('view-catalogus'))
  if (view !== 'wedstrijd') $('kruimel').textContent = { spelers: 'Spelers', catalogus: 'Statistieken', modellen: 'Modellen' }[view]
  if (view === 'wedstrijd') { toonTab(staat.tab); if (staat.data) $('kruimel').innerHTML = `Wedstrijden <span class="dim">/</span> ${esc(playlistNaam(staat.data.meta))} <span class="num">${staat.data.meta.score[0]}–${staat.data.meta.score[1]}</span>` }
}
document.querySelector('.nav').onclick = (e) => { const a = e.target.closest('[data-view]'); if (a) toonView(a.dataset.view) }

// ── Schotkaart: klik op een schot → detailkaart, met 'Bekijk' naar dat moment in de replay ──
$('schotkaart').addEventListener('click', (e) => {
  const punt = e.target.closest('[data-schot],[data-whiff]'), d = staat.data
  document.querySelector('.schot-pop')?.remove()
  $('schotkaart').querySelectorAll('.gekozen').forEach((x) => x.classList.remove('gekozen'))
  if (!punt || !d) return
  punt.classList.add('gekozen')
  const whiff = punt.dataset.whiff != null
  const s = whiff ? d.kansen.gemist[+punt.dataset.whiff] : d.schoten[+punt.dataset.schot]
  const [x, y] = s.plek
  const afstand = Math.round(Math.hypot(x, (s.team === 0 ? 5120 : -5120) - y) / 100)
  const [i] = viewer.zoek(s.tijd + 0.15)
  const kmu = Math.round((d.balSnelheid?.[i] ?? 0) * 0.036)
  const creatie = (d.kansen?.creaties ?? []).filter((c) => c.ontvanger === s.speler && c.tijd <= s.tijd && s.tijd - c.tijd < 4).at(-1)
  const [uitkomst, kl] = whiff ? ['Whiff', ''] : s.goal ? ['Goal', 'goal'] : s.xgot != null ? ['Op doel · gered', ''] : ['Naast', '']
  const f2 = (v) => (v == null ? '–' : v.toFixed(2).replace('.', ','))
  const cel = (l, v, stat) => `<div${stat ? ` class="info" data-stat="${stat}"` : ''}><span>${l}</span><b>${v}</b></div>`
  const cellen = whiff
    ? [cel('Kans-xG', f2(s.kans_xg), 'schieten.whiffxg'), cel('Afstand', `${afstand} m`), cel('Gevolg', 'kans verloren')]
    : [cel('xG', f2(s.xg), 'schieten.xg'), cel('xGOT', s.xgot != null ? f2(s.xgot) : 'naast', 'schieten.xgot'), cel('Kans vóór touch', f2(s.kans), 'passen.xa'),
       cel('Schot-kwaliteit', s.kans != null && s.xg != null ? `${s.xg >= s.kans ? '+' : ''}${f2(s.xg - s.kans)}` : '–', 'schieten.kwaliteit'),
       cel('Afstand', `${afstand} m`), cel('Balsnelheid', `${kmu} km/u`)]
  const pop = document.createElement('div')
  pop.className = 'schot-pop'
  pop.innerHTML = `<button class="sp-sluit" aria-label="Sluiten">×</button>
    <div class="sp-kop"><i style="background:${KLEUR_CSS[s.team]}"></i><b>${esc(naam(s.speler))}</b><span class="num dim">${wedstrijdKlok(d, s.tijd)}</span><span class="sp-uit ${kl}">${uitkomst}</span></div>
    <div class="sp-grid">${cellen.join('')}</div>
    <div class="sp-voet"><span>${creatie ? `Kans gecreëerd door ${esc(naam(creatie.speler))}` : whiff ? '' : 'Eigen actie'}</span><button class="sp-bekijk">▶ Bekijk</button></div>`
  $('schotkaart').closest('.kaart').appendChild(pop)
  pop.querySelector('.sp-sluit').onclick = () => { pop.remove(); punt.classList.remove('gekozen') }
  pop.querySelector('.sp-bekijk').onclick = () => {
    staat.t = Math.max(d.t[0], s.tijd - 3); staat.speelt = true; $('speel').textContent = '❚❚'
    document.querySelector('.kaart-3d')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
})

// ── Afspelen ──
// Alleen naar de DOM schrijven als de waarde echt verandert: elke schrijfactie kan stijl/layout van de pagina
// opnieuw laten berekenen, en dat kostte elk frame ~5 ms (Layout) bij het afspelen.
const vorigeHud = new Map()
function zet(id, sleutel, waarde, schrijf) {
  const k = id + sleutel
  if (vorigeHud.get(k) === waarde) return
  vorigeHud.set(k, waarde)
  const el = $(id); if (el) schrijf(el, waarde)
}
const tekst = (el, v) => { el.textContent = v }
// Breedte van de tijdlijn één keer meten (en bij resize), niet elk frame: lezen na schrijven forceert layout
const tijdlijnBreedte = { w: 0 }
new ResizeObserver(([e]) => { tijdlijnBreedte.w = e.contentRect.width; vorigeHud.delete('tijdlijnkopx') }).observe($('tijdlijnkop').parentElement)

function werkHudBij() {
  const d = staat.data
  const [i] = viewer.zoek(staat.t)
  zet('tijd', 't', klok(d.klok[i]), tekst)
  zet('balsnelheid', 't', `${Math.round(d.balSnelheid[i] * 0.036)} km/u`, tekst)
  const s = scoreOp(d, staat.t)
  zet('score0', 't', String(s[0]), tekst); zet('score1', 't', String(s[1]), tekst)
  d.spelers.forEach((sp, k) => zet('boost' + k, 'b', Math.round(sp.frames[i * 9 + 7]), (el, v) => { el.style.transform = `scaleX(${v / 100})` }))
  // Tijdlijncursor via transform (compositor) i.p.v. left (layout)
  const breedte = tijdlijnBreedte.w
  zet('tijdlijnkop', 'x', Math.round(((staat.t - d.t[0]) / (d.t.at(-1) - d.t[0])) * breedte), (el, v) => { el.style.transform = `translateX(${v - 1}px)` })
  // Live cijfers: kleur per niveau, pijltje bij een verandering
  d.spelers.forEach((sp, k) => {
    const el = $('rating' + k); if (!el) return
    const r = ratingOp(d, sp.id, staat.t), vorige = staat.vorigeRating[k]
    const txt = r == null ? '–' : r.toLocaleString('nl-NL', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
    if (el.textContent !== txt) el.textContent = txt
    const kl = `rating-live num ${ratingKlasse(r)}`
    if (el._kl !== kl) { el.className = kl + (el.classList.contains('flits') ? ' flits' : ''); el._kl = kl }
    if (r != null && vorige != null && Math.abs(r - vorige) >= 0.05) {
      el.dataset.richting = r > vorige ? 'op' : 'neer'
      el.classList.add('flits'); clearTimeout(el._t); el._t = setTimeout(() => el.classList.remove('flits'), 900)
    }
    staat.vorigeRating[k] = r
  })
  staat.rv?.zetT(staat.t)
}

// ?meet=1 → tijd per onderdeel in window.__meet (toon, hud, webgl, labels)
const meet = params.has('meet') ? (window.__meet = []) : null

function lus(nu) {
  const dt = Math.min(0.1, (nu - staat.laatste) / 1000)
  staat.laatste = nu
  if (staat.data && staat.tab === 'overzicht' && !$('view-wedstrijd').hidden) {
    if (staat.speelt) staat.t = Math.min(staat.t + dt * staat.snelheid, staat.data.t.at(-1))
    if (meet) {
      const a = performance.now(); viewer.toon(staat.t); const b = performance.now(); werkHudBij(); const c = performance.now()
      viewer.renderer.render(viewer.scene, viewer.camera); const d = performance.now(); viewer.labels.render(viewer.scene, viewer.camera); const e = performance.now()
      meet.push([b - a, c - b, d - c, e - d])
    } else {
      if (staat.t !== staat.hudT) { werkHudBij(); staat.hudT = staat.t }
      viewer.toon(staat.t)
      viewer.render()
    }
  }
  requestAnimationFrame(lus)
}

$('speel').onclick = () => { staat.speelt = !staat.speelt; $('speel').textContent = staat.speelt ? '❚❚' : '▶' }
$('speel').textContent = staat.speelt ? '❚❚' : '▶'
$('snelheden').onclick = (e) => {
  const b = e.target.closest('button'); if (!b) return
  staat.snelheid = Number(b.dataset.v)
  $('snelheden').querySelectorAll('button').forEach((x) => x.classList.toggle('actief', x === b))
}
$('camknoppen').onclick = (e) => {
  const b = e.target.closest('button'); if (!b) return
  viewer.zetCamera(b.dataset.cam)
  $('camknoppen').querySelectorAll('button').forEach((x) => x.classList.toggle('actief', x === b))
}
if (params.get('cam')) {
  viewer.zetCamera(params.get('cam'))
  $('camknoppen').querySelectorAll('button').forEach((x) => x.classList.toggle('actief', x.dataset.cam === params.get('cam')))
}

let slepen = false
const zoekNaar = (e) => {
  const r = $('tijdlijn').getBoundingClientRect(), d = staat.data
  staat.t = d.t[0] + Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * (d.t.at(-1) - d.t[0])
}
$('tijdlijn').onpointerdown = (e) => { slepen = true; zoekNaar(e) }
addEventListener('pointermove', (e) => slepen && zoekNaar(e))
addEventListener('pointerup', () => (slepen = false))
addEventListener('resize', () => { if (staat.data) { tekenMomentum($('momentum'), staat.data); tekenXgVerloop($('xgverloop'), staat.data); staat.rv = tekenRatingVerloop($('ratingverloop'), staat.data); toonTab(staat.tab) } })
addEventListener('keydown', (e) => { if (e.code === 'Space' && e.target === document.body) { e.preventDefault(); $('speel').click() } })

initUitleg()
toonView(params.get('view') ?? 'wedstrijd')
requestAnimationFrame(lus)
start()
