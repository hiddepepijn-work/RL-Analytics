// Spelerprofiel met echte data (data/verwerkt/profiel.json, gemaakt door kern/profiel.py).
// Valt terug op de voorbeeldweergave als er nog geen profiel is.
import { GROEPEN, format } from './catalogus.js'
import { TIER, tier, pChip, sparkline, vingerafdruk, afwerkingGrafiek, tekenVoorbeeld } from './profiel.js'
import { heatmapSvg } from './wedstrijd.js'
import { ratingKlasse } from './ratings.js'

// Deze stats zijn al een verhouding/gemiddelde; alle andere tellingen staan per 5 minuten speeltijd
const NIET_PER5 = new Set(['impact.rating', 'impact.Schieten', 'impact.Passen', 'impact.Verdedigen', 'impact.Duels', 'impact.Kickoffs', 'impact.Balbezit', 'aanval.schotrendement', 'aanval.xg_per_schot', 'beweging.gem_snelheid', 'positie.afstand_bal',
  'positie.afstand_teamgenoot', 'boost.per_minuut', 'boost.gemiddeld', 'mechanics.speedflip_kwaliteit'])
const isPer5 = (stat) => stat.eenheid !== '%' && !stat.pad.endsWith('_pct') && !/\.\d$/.test(stat.pad) && !NIET_PER5.has(stat.pad)
// "Balk lang = goed" (FBref-regel): bij lager-is-beter het percentiel omdraaien
// Per-5-min-waarden zijn kleine getallen: minstens 1 decimaal
const fmt = (stat, v) => format(isPer5(stat) ? { ...stat, decimalen: Math.max(stat.decimalen ?? 0, Math.abs(v) < 1 ? 2 : 1) } : stat, v)
const goedP = (stat, p) => (stat.beter === 'laag' ? 100 - p : p)
const nl = (v, d = 0) => Number(v).toLocaleString('nl-NL', { minimumFractionDigits: d, maximumFractionDigits: d })
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])

function scoreBalk({ p, laag, hoog }) {
  return `<div class="ratingbalk" title="80%-interval p${laag}–p${hoog}">
    <div class="ratingbalk-spoor"></div>
    <div class="ratingbalk-band" style="left:${laag}%;width:${Math.max(1, hoog - laag)}%"></div>
    <div class="ratingbalk-gem" style="left:50%"></div>
    <div class="ratingbalk-punt" style="left:${p}%"></div>
  </div>
  <div class="ratingbalk-as num"><span>p0</span><span>Champion-mediaan</span><span>p100</span></div>`
}

function statRij(stat, rij) {
  const per5 = isPer5(stat)
  const waarde = fmt(stat, rij.waarde) + (per5 ? '<span class="dim"> /5m</span>' : '')
  const label = `<span class="info" data-stat="${stat.groep}.${stat.id}">${stat.label}</span>${stat.beter === 'laag' ? ' <span class="dim">↓</span>' : ''}`
  if (rij.p == null) return `<div class="prij"><span class="prij-label">${label}</span><span class="prij-waarde num">${waarde}</span><div></div><span class="dim">–</span></div>`
  const neutraal = !stat.beter
  const p = neutraal ? rij.p : goedP(stat, rij.p)
  const [, , kl] = neutraal ? [0, 0, 'var(--tekst-2)'] : tier(p)
  const titel = `${stat.label}: ${fmt(stat, rij.waarde)}${per5 ? ' per 5 min' : ''} · Champion-mediaan ${fmt(stat, rij.mediaan_rank)} · ${neutraal ? `percentiel ${rij.p} (stijl, geen goed/slecht)` : `beter dan ${p}% van de Champions${stat.beter === 'laag' ? ' (lager = beter)' : ''}`}`
  return `<div class="prij" title="${esc(titel)}">
    <span class="prij-label">${label}</span>
    <span class="prij-waarde num">${waarde}</span>
    <div class="prij-spoor"><div class="prij-vul" style="width:${p}%;background:${kl}"></div><div class="prij-mid"></div></div>
    <span class="prij-p num" style="color:${kl}">${p}</span>
  </div>`
}

const TEGELS = ['aanval.xg', 'aanval.goals_min_xg', 'passen.pass_waarde', 'verdedigen.saves', 'passen.aanspeelbaar_pct', 'boost.tijd_0_pct']
const STABIEL = [['Afwerking (goals − xG)', 14], ['xG per 5 min', 10], ['Pass-waarde', 12], ['Saves', 12], ['Boostbeheer', 8]]

function tekenEcht(el, pr) {
  const alle = GROEPEN.flatMap((g) => g.stats.filter((s) => s.pad && pr.stats[s.pad]))
  const vind = (pad) => alle.find((s) => s.pad === pad)
  const sc = pr.profielscore
  const [, sTier, sKl, sBg] = tier(sc?.p ?? 50)
  const groepen = GROEPEN.map((g) => [g.naam, g.stats.filter((s) => s.pad && pr.stats[s.pad])]).filter(([, l]) => l.length)
  const vinger = groepen.map(([naam, l]) => {
    const ps = l.filter((s) => s.beter && pr.stats[s.pad].p != null).map((s) => goedP(s, pr.stats[s.pad].p))
    return ps.length ? [naam.replace(' & creëren', ''), Math.round(ps.reduce((a, b) => a + b, 0) / ps.length)] : null
  }).filter(Boolean).slice(0, 10)
  const tegels = TEGELS.map(vind).filter(Boolean).map((st) => {
    const r = pr.stats[st.pad], gp = r.p != null ? goedP(st, r.p) : null
    return `<div class="kaart tegel">
      <div class="tegel-kop"><span class="info" data-stat="${st.groep}.${st.id}">${st.label}${isPer5(st) ? ' /5m' : ''}</span>${gp != null ? pChip(gp, 'Champion') : ''}</div>
      <div class="tegel-waarde num">${fmt(st, r.waarde)}</div>
      ${r.reeks.length > 1 ? sparkline(r.reeks, gp ?? 50) : '<div style="height:32px"></div>'}
      <div class="tegel-voet"><span class="dim">Champion-mediaan ${fmt(st, r.mediaan_rank)}</span></div>
    </div>`
  }).join('')
  const initialen = pr.naam.replace(/[^\p{L}\p{N}]/gu, '').slice(0, 2).toUpperCase()

  el.innerHTML = `
  ${pr.wedstrijden < pr.betrouwbaar_vanaf ? `<div class="banner">Gebaseerd op ${pr.wedstrijden} wedstrijden. Betrouwbaar vanaf ~${pr.betrouwbaar_vanaf}; tot die tijd zijn de banden breed. Nieuwe wedstrijden komen er automatisch bij.</div>` : ''}
  ${pr.weggelaten ? `<div class="banner dim">Huidige vorm: je ${pr.wedstrijden} nieuwste wedstrijden (laatste ${pr.venster_dagen} dagen). ${pr.weggelaten} oudere ${pr.weggelaten === 1 ? 'telt' : 'tellen'} niet mee.</div>` : ''}
  <header class="profielkop kaart">
    <div class="avatar">${esc(initialen)}</div>
    <div class="profiel-id">
      <div class="profiel-naam">${esc(pr.naam)}</div>
      <div><span class="chip" title="${pr.rank_schatting ? `Geschat uit je laatste ${pr.rank_schatting.wedstrijden} wedstrijden: het niveau van alle spelers in je lobby's (rank-schatter)` : ''}">${pr.rank}${pr.rank_schatting ? ' <span class="dim">(geschat)</span>' : ''}</span><span class="chip">2v2</span><span class="chip">${pr.wedstrijden} wedstrijden · ${String(pr.uren).replace('.', ',')} u</span><span class="chip">${pr.winst}W – ${pr.verlies}V</span></div>
      <div class="dim" style="font-size:12px;margin-top:6px">Vergeleken met ${nl(pr.benchmark_wedstrijden)} Champion-wedstrijden · tellingen per 5 min speeltijd</div>
    </div>
    ${sc ? `<div class="profiel-rating">
      <div class="profiel-rating-kop"><span>Profielscore</span><span class="dim">gem. percentiel kernstats</span></div>
      <div class="profiel-rating-rij"><span class="rating-groot num" style="color:${sKl};background:${sBg}">${sc.p}</span><div style="flex:1">${scoreBalk(sc)}</div></div>
      <div class="dim" style="font-size:12px">${sTier} · 80%-interval p${sc.laag}–p${sc.hoog}</div>
    </div>` : ''}
  </header>
  ${ratingSectie(pr)}
  <section class="tegels">${tegels}</section>
  <section class="profielraster">
    <div class="kaart">
      <div class="kaart-kop"><span>Percentielen</span><span class="sub">t.o.v. Champion 2v2 · balk lang = goed · ↓ = lager is beter</span></div>
      <div class="pgroepen">${groepen.map(([naam, l]) => `<div class="pgroep"><div class="pgroep-kop">${naam}</div>${l.slice(0, 6).map((s) => statRij(s, pr.stats[s.pad])).join('')}</div>`).join('')}</div>
      <div class="tierlegenda">${TIER.slice().reverse().map(([, n, kl]) => `<span><i style="background:${kl}"></i>${n}</span>`).join('')}<span class="dim">· grijs = stijl (geen goed/slecht) · streep = Champion-mediaan</span></div>
    </div>
    <div>
      <div class="kaart" style="margin-bottom:16px">
        <div class="kaart-kop"><span>Speelstijl</span><span class="sub">gem. percentiel per onderdeel</span></div>
        ${vingerafdruk(vinger)}
      </div>
      <div class="kaart" style="margin-bottom:16px">
        <div class="kaart-kop"><span>Positie op het veld</span><span class="sub">gemiddeld over je wedstrijden</span></div>
        ${heatmapSvg(pr.heatmap)}
        <div class="hm-as"><span>eigen doel</span><span>tegenstander</span></div>
      </div>
      <div class="kaart">
        <div class="kaart-kop"><span>Afwerking boven verwachting</span><span class="sub">cumulatief goals − xG · 80%-band</span></div>
        ${pr.afwerking.length > 1 ? afwerkingGrafiek(pr.afwerking) : '<div class="dim">Zichtbaar vanaf 2 wedstrijden</div>'}
        <div class="dim" style="font-size:12px;margin-top:4px">Raakt de band de nul, dan is "goede of slechte afwerker" nog niet bewezen.</div>
      </div>
    </div>
    <div class="kaart kaart-breed">
      <div class="kaart-kop"><span>Betrouwbaarheid</span><span class="sub">wedstrijden nodig voor een stabiel beeld (zie Modellen → Hoeveel data is nodig?)</span></div>
      <div class="stabiel">${STABIEL.map(([naam, nodig]) => {
        const f = Math.min(1, pr.wedstrijden / nodig), klaar = pr.wedstrijden >= nodig
        return `<div class="stabiel-rij"><span>${naam}</span><div class="stabiel-spoor"><i style="width:${f * 100}%;background:${klaar ? 'var(--tier-top)' : 'var(--tekst-3)'}"></i></div><span class="num ${klaar ? '' : 'dim'}">${klaar ? '✓ stabiel' : `${pr.wedstrijden}/${nodig} wedstr.`}</span></div>`
      }).join('')}</div>
    </div>
  </section>`
}

// Ratings in het profiel: gemiddeld wedstrijdcijfer, cijfer per onderdeel, en vorm (cijfer per wedstrijd)
function ratingSectie(pr) {
  const r = pr.ratings
  if (!r || r.gem == null) return ''
  const ond = Object.entries(r.onderdelen ?? {})
  const id = { Schieten: 'r_schieten', Passen: 'r_passen', Verdedigen: 'r_verdedigen', Duels: 'r_duels', Kickoffs: 'r_kickoffs', Balbezit: 'r_balbezit' }
  const vorm = r.per_wedstrijd.filter((w) => w.rating != null)
  return `<section class="profiel-ratings">
    <div class="kaart pr-cijfer">
      <div class="kaart-kop"><h3 class="info" data-stat="impact.rating">Gem. wedstrijdcijfer</h3><span class="sub">${vorm.length} wedstrijden</span></div>
      <div class="pr-groot ${ratingKlasse(r.gem)}"><span data-tel="${r.gem}" data-dec="1">${nl(r.gem, 1)}</span></div>
      <div class="dim" style="font-size:12px;margin-top:8px">6,5 = gemiddelde Champion · 7+ goed · 8+ uitstekend</div>
    </div>
    <div class="kaart">
      <div class="kaart-kop"><h3>Cijfer per onderdeel</h3><span class="sub">gemiddeld</span></div>
      <div class="rk-onderdelen">${ond.map(([o, c]) => `<div class="rk-rij" data-stat="impact.${id[o]}"><span>${o}</span>
        <div class="rk-spoor"><i class="${ratingKlasse(c)}" style="width:${((c - 3) / 7) * 100}%"></i><b style="left:${(3.5 / 7) * 100}%"></b></div>
        <span class="num ${ratingKlasse(c)}-tekst">${nl(c, 1)}</span><span></span></div>`).join('')}</div>
    </div>
    <div class="kaart">
      <div class="kaart-kop"><h3>Vorm</h3><span class="sub">cijfer per wedstrijd · klik om te openen</span></div>
      <div class="vorm">${vorm.slice(-15).map((w) => `<a class="vorm-balk" href="/?replay=${w.bestand}" data-uitleg="${w.datum?.slice(0, 10) ?? ''} · ${w.uitslag === 'W' ? 'gewonnen' : 'verloren'} · cijfer ${nl(w.rating, 1)}" data-titel="Wedstrijd">
        <span class="vorm-cijfer num">${nl(w.rating, 1)}</span><i class="${ratingKlasse(w.rating)}" style="height:${Math.max(6, ((w.rating - 3) / 7) * 100)}%"></i><span class="vorm-uitslag ${w.uitslag === 'W' ? 'w' : 'v'}">${w.uitslag}</span></a>`).join('')}</div>
    </div>
  </section>`
}

export async function tekenProfiel(el) {
  try {
    const r = await fetch('/verwerkt/profiel.json', { cache: 'no-store' })
    if (r.ok) return tekenEcht(el, await r.json())
  } catch {}
  tekenVoorbeeld(el)
}
