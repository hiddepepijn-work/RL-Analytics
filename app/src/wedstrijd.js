// Tab-inhoud van het wedstrijdscherm, gevoed door data.stats + de catalogus.
import { GROEPEN, waarde, format, teamWaarde } from './catalogus.js'
import { KLEUR_CSS } from './grafieken.js'
import { VELD } from './veld.js'

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
const initialen = (n) => n.replace(/[^\p{L}\p{N} ]/gu, '').split(' ').filter(Boolean).map((w) => w[0]).join('').slice(0, 2).toUpperCase() || '?'
const klok = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`
const PLAYLIST = { 6: 'Privé', 10: 'Ranked Duel', 11: 'Ranked Doubles', 13: 'Ranked Standard', 27: 'Ranked Hoops', 28: 'Ranked Rumble', 29: 'Ranked Dropshot', 30: 'Ranked Snow Day', 34: 'Toernooi' }
const OPBOUW = { counter_attack: 'Counter', sustained_pressure: 'Aanhoudende druk', kickoff: 'Kickoff', other: 'Open spel' }
export const playlistNaam = (m) => PLAYLIST[m.playlist] ?? m.speltype

// Leetify-idee: gemiddeld blijft neutraal, alleen uitschieters krijgen kleur (los van teamkleuren)
function tint(z, beter) {
  if (!beter || z == null || !Number.isFinite(z)) return ''
  const g = beter === 'hoog' ? z : -z
  if (g >= 1.3) return 'tint-top'
  if (g >= 0.6) return 'tint-goed'
  if (g <= -1.3) return 'tint-slecht'
  if (g <= -0.6) return 'tint-onder'
  return ''
}

function zScores(data, stat) {
  const vs = data.spelers.map((s) => waarde(data.stats.spelers[s.id], stat.pad))
  const ok = vs.filter((v) => v != null)
  const gem = ok.reduce((a, b) => a + b, 0) / (ok.length || 1)
  const sd = Math.sqrt(ok.reduce((a, b) => a + (b - gem) ** 2, 0) / (ok.length || 1))
  return vs.map((v) => (v == null || sd < 1e-9 ? null : (v - gem) / sd))
}

// MVP = hoogste wedstrijdcijfer (val terug op in-game score als er geen rating is)
const eindRating = (data, s) => data.rating?.spelers?.[s.id]?.eind
const mvp = (data) => [...data.spelers].sort((a, b) => (eindRating(data, b) ?? b.stats.Score / 100) - (eindRating(data, a) ?? a.stats.Score / 100))[0]
const rKlasse = (r) => r == null ? 'r-geen' : r >= 8 ? 'r-top' : r >= 7 ? 'r-goed' : r >= 6 ? 'r-gem' : r >= 5 ? 'r-onder' : 'r-slecht'

export function tekenHero(el, data) {
  const m = data.meta, top = mvp(data)
  const team = (t) => data.spelers.filter((s) => s.team === t).sort((a, b) => b.stats.Score - a.stats.Score)
  const rij = (s) => `<div class="hero-speler">
      <span class="avatar-s" style="--kl:${KLEUR_CSS[s.team]}">${esc(initialen(s.naam))}</span>
      <span class="hero-speler-naam">${esc(s.naam)}${s === top ? '<span class="mvp">MVP</span>' : ''}</span>
      ${eindRating(data, s) != null ? `<span class="rating-chip ${rKlasse(eindRating(data, s))}" data-stat="impact.rating">${eindRating(data, s).toLocaleString('nl-NL', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</span>` : `<span class="num dim">${s.stats.Score}</span>`}</div>`
  const winnaar = m.score[0] === m.score[1] ? -1 : m.score[0] > m.score[1] ? 0 : 1
  el.innerHTML = `
    <div class="hero-team">
      <div class="hero-teamnaam"><i style="background:${KLEUR_CSS[0]}"></i>Blauw${winnaar === 0 ? '<span class="winst">Winst</span>' : ''}</div>
      ${team(0).map(rij).join('')}
    </div>
    <div class="hero-midden">
      <div class="hero-meta">${esc(playlistNaam(m))} · ${m.teamgrootte}v${m.teamgrootte} · ${esc((m.map ?? '').replace(/_P$/, '').replace(/_/g, ' '))}</div>
      <div class="hero-score"><span class="s0" data-tel="${m.score[0]}">${m.score[0]}</span><span class="hero-streep">–</span><span class="s1" data-tel="${m.score[1]}">${m.score[1]}</span></div>
      <div class="hero-sub">${klok(m.duur)} gespeeld · seizoen ${m.seizoen}${m.datum ? ` · ${esc(m.datum.slice(0, 10))}` : ''}</div>
    </div>
    <div class="hero-team rechts">
      <div class="hero-teamnaam">${winnaar === 1 ? '<span class="winst">Winst</span>' : ''}Oranje<i style="background:${KLEUR_CSS[1]}"></i></div>
      ${team(1).map(rij).join('')}
    </div>`
}

// FotMob-achtige gespiegelde vergelijkingsbalk
function vergelijk(label, a, b, fmt, beter = 'hoog', klein = false, sleutel = '') {
  const tot = (a ?? 0) + (b ?? 0) || 1
  const wa = beter === 'laag' ? (a ?? 0) < (b ?? 0) : (a ?? 0) > (b ?? 0)
  const wb = beter === 'laag' ? (b ?? 0) < (a ?? 0) : (b ?? 0) > (a ?? 0)
  return `<div class="vgl ${klein ? 'klein' : ''}">
    <span class="vgl-a num ${wa && beter ? 'wint' : ''}">${fmt(a)}</span>
    <span class="vgl-label${sleutel ? ' info' : ''}" ${sleutel ? `data-stat="${sleutel}"` : ''}>${label}</span>
    <span class="vgl-b num ${wb && beter ? 'wint' : ''}">${fmt(b)}</span>
    <div class="vgl-balk"><i class="a" style="flex:${(a ?? 0) / tot}"></i><i class="b" style="flex:${(b ?? 0) / tot}"></i></div>
  </div>`
}

export function tekenKernstrip(el, data) {
  const t = data.stats.teams
  const som = (pad, team) => data.spelers.filter((s) => s.team === team).reduce((x, s) => x + (waarde(data.stats.spelers[s.id], pad) ?? 0), 0)
  const pct = (v) => `${Math.round(v)}%`, n = (v) => Math.round(v).toLocaleString('nl-NL')
  el.innerHTML = [
    vergelijk('Balbezit', t[0].bezit_pct, t[1].bezit_pct, pct, null),
    vergelijk('xG', som('aanval.xg', 0), som('aanval.xg', 1), (v) => v.toFixed(2).replace('.', ',')),
    vergelijk('Schotpogingen', som('aanval.schot_pogingen', 0), som('aanval.schot_pogingen', 1), n),
    vergelijk('50/50 gewonnen', som('duels.5050_gewonnen', 0), som('duels.5050_gewonnen', 1), n),
    vergelijk('Boost gestolen', som('boost.gestolen', 0), som('boost.gestolen', 1), n),
  ].join('')
}

export function tekenGoals(el, data, naam) {
  const goals = data.events.filter((e) => e.soort === 'Goal')
  const ctx = data.events.filter((e) => e.soort === 'goal_context')
  const assists = data.events.filter((e) => e.soort === 'Assist')
  el.innerHTML = goals.map((g, k) => {
    const c = data.stats.goals[k] ?? {}
    const a = assists.find((x) => Math.abs(x.tijd - g.tijd) < 0.5)
    return `<button class="goal" data-t="${g.tijd}" style="--kl:${KLEUR_CSS[g.team]}">
      <span class="goal-tijd num">${klok(g.tijd - data.t[0])}</span>
      <span class="goal-naam">${esc(naam(g.speler))}</span>
      <span class="goal-sub">${a ? `assist ${esc(naam(a.speler))}` : 'solo'}</span>
      <span class="goal-chips"><span class="chip">${c.balsnelheid ?? Math.round((ctx[k]?.balsnelheid ?? 0) * 0.036)} km/u</span><span class="chip">${OPBOUW[c.opbouw] ?? 'Open spel'}</span></span>
    </button>`
  }).join('') || '<div class="dim">Geen doelpunten</div>'
}

export function tekenTeamstats(el, data) {
  el.innerHTML = GROEPEN.map((g) => {
    const rijen = g.stats.filter((s) => s.pad && s.team).map((s) =>
      vergelijk(s.label, teamWaarde(s, data, 0), teamWaarde(s, data, 1), (v) => format(s, v), s.beter, true, `${s.groep}.${s.id}`))
    const later = g.stats.filter((s) => !s.pad)
    if (!rijen.length && !later.length) return ''
    return `<div class="kaart stats-groep">
      <div class="kaart-kop"><h3>${g.naam}</h3><span class="sub">${g.vraag}</span></div>
      ${rijen.join('')}
      ${later.length ? `<div class="later">${later.map((s) => `<span class="chip" title="${esc(s.uitleg ?? '')}">${s.status === 'model' ? '◇' : '◐'} ${s.label}</span>`).join('')}</div>` : ''}
    </div>`
  }).join('')
}

export function tekenSpelertabel(el, data, groepId, sorteer, opKlik) {
  const g = GROEPEN.find((x) => x.id === groepId) ?? GROEPEN[0]
  const stats = g.stats.filter((s) => s.pad)
  const z = Object.fromEntries(stats.map((s) => [s.id, zScores(data, s)]))
  let rijen = data.spelers.map((s, k) => ({ s, k }))
  if (sorteer?.groep === g.id) {
    const st = stats.find((x) => x.id === sorteer.stat)
    if (st) rijen.sort((a, b) => ((waarde(data.stats.spelers[b.s.id], st.pad) ?? -1e9) - (waarde(data.stats.spelers[a.s.id], st.pad) ?? -1e9)) * (sorteer.op ? -1 : 1))
  } else rijen.sort((a, b) => a.s.team - b.s.team || b.s.stats.Score - a.s.stats.Score)
  el.innerHTML = `
    <div class="groepkeuze">${GROEPEN.filter((x) => x.stats.some((s) => s.pad)).map((x) => `<button data-groep="${x.id}" class="${x.id === g.id ? 'actief' : ''}">${x.naam}</button>`).join('')}</div>
    <div class="kaart">
      <div class="kaart-kop"><h3>${g.naam}</h3><span class="sub">${g.vraag} · kleur = uitschieter binnen deze lobby</span></div>
      <div class="tabel-wrap"><table class="tabel">
        <thead><tr><th class="links">Speler</th>${stats.map((s) => `<th data-sort="${s.id}" data-stat="${s.groep}.${s.id}" class="info ${sorteer?.stat === s.id ? 'gesorteerd' : ''}">${s.label}${s.beter === 'laag' ? ' <span class="dim">↓</span>' : ''}</th>`).join('')}</tr></thead>
        <tbody>${rijen.map(({ s, k }) => `<tr>
          <td class="links"><span class="tabel-speler"><i style="background:${KLEUR_CSS[s.team]}"></i>${esc(s.naam)}</span></td>
          ${stats.map((st) => `<td class="num ${tint(z[st.id][k], st.beter)}">${format(st, waarde(data.stats.spelers[s.id], st.pad))}</td>`).join('')}
        </tr>`).join('')}</tbody>
      </table></div>
      <div class="tierlegenda"><span><i style="background:var(--tier-top)"></i>ver boven</span><span><i style="background:var(--tier-goed)"></i>boven</span><span><i style="background:var(--tier-gem)"></i>gemiddeld</span><span><i style="background:var(--tier-onder)"></i>onder</span><span><i style="background:var(--tier-slecht)"></i>ver onder</span><span class="dim">↓ = lager is beter</span></div>
    </div>`
  el.querySelector('.groepkeuze').onclick = (e) => { const b = e.target.closest('button'); if (b) opKlik({ groep: b.dataset.groep }) }
  el.querySelector('thead').onclick = (e) => {
    const th = e.target.closest('th[data-sort]'); if (!th) return
    opKlik({ groep: g.id, stat: th.dataset.sort, op: sorteer?.stat === th.dataset.sort ? !sorteer.op : false })
  }
}

// Liggend veld: eigen doel links. Sequentieel: één tint, transparant → vol; browser strijkt de pixels glad.
const HM_RGB = [46, 196, 196]
export function heatmapSvg(hm) {
  const nx = hm.length, ny = hm[0].length
  const max = Math.max(...hm.flat()) || 1
  const c = document.createElement('canvas'); c.width = ny; c.height = nx
  const ctx = c.getContext('2d'), img = ctx.createImageData(ny, nx)
  for (let x = 0; x < nx; x++) for (let y = 0; y < ny; y++) {
    const v = Math.pow(hm[x][y] / max, 0.8), i = ((nx - 1 - x) * ny + y) * 4
    img.data.set([...HM_RGB, Math.round(v * 235)], i)
  }
  ctx.putImageData(img, 0, 0)
  const W = 300, H = 240
  return `<svg viewBox="-10 0 320 240" class="hm-mini">
    <rect width="${W}" height="${H}" rx="10" fill="var(--paneel-2)"/>
    <image href="${c.toDataURL()}" width="${W}" height="${H}" preserveAspectRatio="none" style="image-rendering:auto"/>
    <g fill="none" stroke="rgba(255,255,255,.18)" stroke-width="1">
      <rect x="0.5" y="0.5" width="${W - 1}" height="${H - 1}" rx="10"/>
      <line x1="${W / 2}" x2="${W / 2}" y1="0" y2="${H}"/>
      <circle cx="${W / 2}" cy="${H / 2}" r="28"/>
      <rect x="0" y="${H / 2 - 52}" width="34" height="104"/><rect x="${W - 34}" y="${H / 2 - 52}" width="34" height="104"/>
    </g>
    <rect x="-7" y="${H / 2 - 26}" width="5" height="52" rx="2" fill="var(--tekst-2)"/><rect x="${W + 2}" y="${H / 2 - 26}" width="5" height="52" rx="2" fill="var(--tekst-3)"/>
  </svg>`
}

function gestapeld(delen, kleuren, labels) {
  const tot = delen.reduce((a, b) => a + (b ?? 0), 0) || 1
  return `<div class="stapel">${delen.map((v, i) => `<i style="flex:${(v ?? 0) / tot};background:${kleuren[i]}" title="${labels[i]}: ${Math.round(v ?? 0)}%"></i>`).join('')}</div>`
}

const RAMP = ['#1d5c63', '#2a9097', '#5fd0d0'] // ordinaal, één tint, donker → licht

export function tekenPositie(el, data) {
  const sp = [...data.spelers].sort((a, b) => a.team - b.team)
  el.innerHTML = `
    <div class="hm-raster">${sp.map((s) => {
      const p = data.stats.spelers[s.id].positie
      return `<div class="kaart hm-kaart">
        <div class="kaart-kop"><span class="tabel-speler"><i style="background:${KLEUR_CSS[s.team]}"></i>${esc(s.naam)}</span><span class="sub num">${p.afstand_bal ?? '–'} uu tot bal</span></div>
        ${heatmapSvg(p.heatmap)}
        <div class="hm-as"><span>eigen doel</span><span>tegenstander</span></div>
      </div>`
    }).join('')}</div>
    <div class="twee">
      <div class="kaart"><div class="kaart-kop"><h3>Veld-derden</h3><span class="sub">verdedigend · midden · aanvallend</span></div>
        ${sp.map((s) => `<div class="stapel-rij"><span class="tabel-speler"><i style="background:${KLEUR_CSS[s.team]}"></i>${esc(s.naam)}</span>${gestapeld(data.stats.spelers[s.id].positie.derden_pct, RAMP, ['Verdedigend', 'Midden', 'Aanvallend'])}<span class="num dim">${data.stats.spelers[s.id].positie.derden_pct.map((v) => Math.round(v)).join(' / ')}</span></div>`).join('')}
        <div class="stapel-legenda"><span><i style="background:${RAMP[0]}"></i>Verdedigend</span><span><i style="background:${RAMP[1]}"></i>Midden</span><span><i style="background:${RAMP[2]}"></i>Aanvallend</span></div>
      </div>
      <div class="kaart"><div class="kaart-kop"><h3>Rotatie</h3><span class="sub">tijd als 1e · 2e · 3e man</span></div>
        ${sp.map((s) => `<div class="stapel-rij"><span class="tabel-speler"><i style="background:${KLEUR_CSS[s.team]}"></i>${esc(s.naam)}</span>${gestapeld(data.stats.spelers[s.id].rotatie.rollen_pct, RAMP.slice().reverse(), ['1e man', '2e man', '3e man'])}<span class="num dim">${data.stats.spelers[s.id].rotatie.rollen_pct.map((v) => Math.round(v)).join(' / ')}</span></div>`).join('')}
        <div class="stapel-legenda"><span><i style="background:${RAMP[2]}"></i>1e man</span><span><i style="background:${RAMP[1]}"></i>2e man</span><span><i style="background:${RAMP[0]}"></i>3e man</span></div>
      </div>
    </div>`
}

const BOOST_RAMP = ['#5a4a1c', '#8f7424', '#c9a231', '#f5cf4f'] // 0–25 … 75–100

export function tekenBoost(el, data) {
  const { lengte: l, breedte: b, hoek: k } = VELD
  const omtrek = [[-l + k, -b], [l - k, -b], [l, -b + k], [l, b - k], [l - k, b], [-l + k, b], [-l, b - k], [-l, -b + k]]
  let kaart = `<polygon points="${omtrek.map(([x, y]) => `${x},${y}`).join(' ')}" fill="var(--paneel-2)" stroke="var(--rand)" stroke-width="24"/>
    <line x1="0" y1="${-b}" x2="0" y2="${b}" stroke="var(--rand)" stroke-width="16"/>
    <rect x="${-l - 880}" y="-893" width="880" height="1786" fill="none" stroke="${KLEUR_CSS[0]}" stroke-width="28"/>
    <rect x="${l}" y="-893" width="880" height="1786" fill="none" stroke="${KLEUR_CSS[1]}" stroke-width="28"/>`
  for (const [x, y, team, groot, steal] of data.stats.pickups) {
    kaart += `<circle cx="${y}" cy="${x}" r="${groot ? 150 : 80}" fill="${KLEUR_CSS[team]}" fill-opacity="${groot ? 0.5 : 0.32}" ${steal ? 'stroke="#fff" stroke-width="22" stroke-opacity=".8"' : ''}/>`
  }
  const sp = [...data.spelers].sort((a, b2) => a.team - b2.team)
  const B = (s) => data.stats.spelers[s.id].boost
  el.innerHTML = `
    <div class="twee boost-boven">
      <div class="kaart"><div class="kaart-kop"><h3>Boost-pickups</h3><span class="sub">${data.stats.pickups.length} pickups · wit = gestolen</span></div>
        <svg viewBox="${-l - 1000} ${-b - 150} ${2 * l + 2000} ${2 * b + 300}" class="padkaart">${kaart}</svg>
        <div class="legenda"><span><i class="stip vol" style="background:${KLEUR_CSS[0]};border-color:${KLEUR_CSS[0]}"></i>Blauw</span><span><i class="stip vol" style="background:${KLEUR_CSS[1]};border-color:${KLEUR_CSS[1]}"></i>Oranje</span><span class="dim">groot = 100-pad · klein = 12-pad</span></div>
      </div>
      <div class="kaart"><div class="kaart-kop"><h3>Boostniveau</h3><span class="sub">tijd per band</span></div>
        ${sp.map((s) => `<div class="stapel-rij"><span class="tabel-speler"><i style="background:${KLEUR_CSS[s.team]}"></i>${esc(s.naam)}</span>${gestapeld(B(s).banden_pct, BOOST_RAMP, ['0–25', '25–50', '50–75', '75–100'])}<span class="num dim">gem. ${B(s).gemiddeld}</span></div>`).join('')}
        <div class="stapel-legenda">${['0–25', '25–50', '50–75', '75–100'].map((t, i) => `<span><i style="background:${BOOST_RAMP[i]}"></i>${t}</span>`).join('')}</div>
      </div>
    </div>`
}

export function tekenCatalogus(el) {
  const alle = GROEPEN.flatMap((g) => g.stats)
  const tel = (st) => alle.filter((s) => (s.pad ? 'ok' : s.status) === st).length
  const STATUS = { ok: ['✓', 'beschikbaar', 'st-ok'], afgeleid: ['◐', 'af te leiden', 'st-af'], model: ['◇', 'eigen model', 'st-model'] }
  el.innerHTML = `
    <div class="catalogus-kop">
      <div><h1>Statistieken</h1><p class="dim">Alle stats per onderdeel, naar het voorbeeld van voetbal-analytics. Status = wat er nu al uit de replay komt.</p></div>
      <div class="catalogus-tellers">
        <div><span class="num">${tel('ok')}</span><span class="st-ok">✓ beschikbaar</span></div>
        <div><span class="num">${tel('afgeleid')}</span><span class="st-af">◐ af te leiden</span></div>
        <div><span class="num">${tel('model')}</span><span class="st-model">◇ eigen model</span></div>
      </div>
    </div>
    <div class="catalogus">${GROEPEN.map((g) => `
      <div class="kaart cat-groep">
        <div class="kaart-kop"><h3>${g.naam}</h3><span class="sub">${g.vraag}</span></div>
        ${g.stats.map((s) => { const [ic, , kl] = STATUS[s.pad ? 'ok' : s.status]; return `
          <div class="cat-rij">
            <span class="cat-status ${kl}">${ic}</span>
            <span class="cat-label info" data-stat="${s.groep}.${s.id}">${s.label}${s.beter === 'laag' ? ' <span class="dim">(lager = beter)</span>' : ''}</span>
            ${s.voetbal ? `<span class="chip">${s.voetbal}</span>` : '<span></span>'}
            ${s.uitleg ? `<span class="cat-uitleg">${s.uitleg}</span>` : ''}
          </div>` }).join('')}
      </div>`).join('')}
    </div>`
}
