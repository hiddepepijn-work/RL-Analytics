// Spelerprofiel. Nu met VOORBEELDDATA: echte waarden volgen zodra modellen + rank-benchmarks bestaan.
// Ontwerpregels (zie onderzoek): percentiel t.o.v. vaste rank-groep, gemiddeld = neutraal,
// alleen uitschieters kleuren (Leetify-tiers), ruwe waarde altijd naast het percentiel,
// "minder X"-stats expliciet benoemd, onzekerheid altijd zichtbaar.

const VOORBEELD = {
  naam: 'Voorbeeldspeler', rank: 'Champion II', mode: '2v2', games: 48, uren: 3.9, seizoen: 23,
  rating: { waarde: 7.4, laag: 6.9, hoog: 7.8, p: 76 },
  tegels: [
    { label: 'xG per 5 min', waarde: '0,42', p: 71, reeks: [0.31, 0.36, 0.4, 0.33, 0.45, 0.39, 0.5, 0.41, 0.44, 0.42] },
    { label: 'Goals − xG', waarde: '+3,1', p: 84, reeks: [-0.4, 0.2, 0.9, 0.6, 1.4, 1.1, 2.0, 2.6, 2.4, 3.1], onzeker: 'nog 18 schoten tot stabiel' },
    { label: 'Touch-waarde / 5 min', waarde: '+0,09', p: 66, reeks: [0.05, 0.07, 0.04, 0.08, 0.1, 0.07, 0.09, 0.11, 0.08, 0.09] },
    { label: 'Saves boven verwachting', waarde: '+1,8', p: 78, reeks: [0, 0.3, 0.2, 0.7, 0.9, 1.0, 1.4, 1.3, 1.6, 1.8] },
    { label: 'Boost per minuut', waarde: '412', p: 48, reeks: [398, 420, 405, 431, 415, 402, 409, 418, 411, 412] },
    { label: 'Tijd als laatste man', waarde: '31%', p: 22, reeks: [35, 33, 34, 30, 32, 31, 29, 31, 30, 31] },
  ],
  groepen: [
    ['Aanval', [['xG per 5 min', '0,42', 71], ['Schoten per 5 min', '2,1', 64], ['Schot op doel', '47%', 58], ['xA per 5 min', '0,11', 82]]],
    ['Balbezit', [['Touch-waarde per 5 min', '+0,09', 66], ['Passes per 5 min', '1,4', 55], ['50/50 gewonnen', '54%', 61], ['Kickoffs gewonnen', '49%', 44]]],
    ['Verdediging', [['Saves boven verwachting', '+1,8', 78], ['Clears per 5 min', '3,2', 52], ['Tijd achter de bal', '68%', 40], ['Minder double commits', '0,6 / 5 min', 27]]],
    ['Boost & rotatie', [['Boost per minuut', '412', 48], ['Gestolen boost', '19%', 69], ['Minder tijd op 0 boost', '8%', 91], ['Rotatie-discipline', '0,72', 35]]],
  ],
  vingerafdruk: [['Afwerking', 84], ['Kansen maken', 82], ['Balbezit', 66], ['Duels', 61], ['Redden', 78], ['Positie', 33], ['Boostbeheer', 74], ['Mechanics', 57]],
  // Aandeel speeltijd per zone: 5 vakken over de lengte (eigen doel → vijandelijk doel) × 3 banen
  zones: [[4, 6, 5], [7, 11, 8], [6, 9, 7], [5, 8, 6], [3, 6, 3]],
  // Cumulatief goals − xG per wedstrijd met 80%-band (wordt smaller naarmate er meer schoten zijn)
  afwerking: Array.from({ length: 48 }, (_, i) => {
    const v = 3.1 * (i / 47) + Math.sin(i * 0.7) * 0.5 * (1 - i / 60)
    const b = 2.6 / Math.sqrt(1 + i * 0.35)
    return [v, v - b, v + b]
  }),
  stabiel: [['xG per 5 min', 48, 15], ['Touch-waarde', 48, 20], ['Afwerking (G − xG)', 62, 80, 'schoten'], ['Saves boven verwachting', 31, 60, 'schoten tegen'], ['50/50-winst', 112, 150, 'duels']],
}

export const TIER = [
  [90, 'Top', 'var(--tier-top)', 'rgba(47,210,122,.14)'],
  [70, 'Goed', 'var(--tier-goed)', 'rgba(127,220,159,.10)'],
  [30, 'Gemiddeld', 'var(--tier-gem)', 'rgba(230,235,242,.06)'],
  [10, 'Onder', 'var(--tier-onder)', 'rgba(245,163,91,.10)'],
  [0, 'Zwak', 'var(--tier-slecht)', 'rgba(240,101,91,.12)'],
]
export const tier = (p) => TIER.find(([grens]) => p >= grens)
export const pChip = (p, groep = VOORBEELD.rank) => { const [, naam, kl, bg] = tier(p); return `<span class="pchip" style="color:${kl};background:${bg}" title="${naam} · percentiel ${p} binnen ${groep}">p${p}</span>` }

export function sparkline(reeks, p) {
  const w = 120, h = 32, min = Math.min(...reeks), max = Math.max(...reeks), sp = max - min || 1
  const pt = reeks.map((v, i) => [(i / (reeks.length - 1)) * (w - 6) + 3, h - 4 - ((v - min) / sp) * (h - 8)])
  const [, , kl] = tier(p)
  return `<svg class="spark" viewBox="0 0 ${w} ${h}"><polyline points="${pt.map((x) => x.join(',')).join(' ')}" fill="none" stroke="var(--tekst-3)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${pt.at(-1)[0]}" cy="${pt.at(-1)[1]}" r="4" fill="${kl}" stroke="var(--paneel)" stroke-width="2"/></svg>`
}

function ratingBalk({ waarde, laag, hoog }) {
  const min = 5, max = 9, x = (v) => ((v - min) / (max - min)) * 100
  return `<div class="ratingbalk" title="80%-interval ${laag.toFixed(1)}–${hoog.toFixed(1)}">
    <div class="ratingbalk-spoor"></div>
    <div class="ratingbalk-band" style="left:${x(laag)}%;width:${x(hoog) - x(laag)}%"></div>
    <div class="ratingbalk-gem" style="left:${x(6.5)}%"></div>
    <div class="ratingbalk-punt" style="left:${x(waarde)}%"></div>
  </div>
  <div class="ratingbalk-as num"><span>5,0</span><span>rank-gem. 6,5</span><span>9,0</span></div>`
}

function percentielRij([label, waarde, p]) {
  const [, , kl] = tier(p)
  return `<div class="prij" title="${label}: ${waarde} · percentiel ${p}">
    <span class="prij-label">${label}</span>
    <span class="prij-waarde num">${waarde}</span>
    <div class="prij-spoor"><div class="prij-vul" style="width:${p}%;background:${kl}"></div><div class="prij-mid"></div></div>
    <span class="prij-p num" style="color:${kl}">${p}</span>
  </div>`
}

export function vingerafdruk(items) {
  const cx = 170, cy = 170, r0 = 26, r1 = 130, n = items.length
  let s = ''
  for (const ring of [25, 50, 75, 100]) s += `<circle cx="${cx}" cy="${cy}" r="${r0 + (r1 - r0) * ring / 100}" fill="none" stroke="var(--rand)" stroke-dasharray="${ring === 50 ? '4 4' : ''}"/>`
  items.forEach(([label, p], i) => {
    const a0 = (i / n) * 2 * Math.PI - Math.PI / 2 + 0.03, a1 = ((i + 1) / n) * 2 * Math.PI - Math.PI / 2 - 0.03
    const r = r0 + (r1 - r0) * p / 100
    const boog = (rr, a, b) => `${cx + rr * Math.cos(a)},${cy + rr * Math.sin(a)} A${rr},${rr} 0 0 1 ${cx + rr * Math.cos(b)},${cy + rr * Math.sin(b)}`
    const [, naam, kl] = tier(p)
    s += `<path d="M${boog(r0, a0, a1)} L${boog(r, a1, a0).replace('0 0 1', '0 0 0')} Z" fill="${kl}" fill-opacity=".85" stroke="var(--paneel)" stroke-width="2"><title>${label}: percentiel ${p} (${naam})</title></path>`
    const am = (a0 + a1) / 2, rl = r1 + 22
    const x = cx + rl * Math.cos(am), y = cy + rl * Math.sin(am)
    const anker = Math.abs(Math.cos(am)) < 0.3 ? 'middle' : Math.cos(am) > 0 ? 'start' : 'end'
    s += `<text x="${x}" y="${y}" text-anchor="${anker}" dominant-baseline="middle" class="pizza-label">${label}</text>`
    s += `<text x="${x}" y="${y + 14}" text-anchor="${anker}" dominant-baseline="middle" class="pizza-p">${p}</text>`
  })
  return `<svg viewBox="-50 -10 440 360" class="pizza">${s}</svg>`
}

function heatmap(zones) {
  // Bovenaanzicht liggend: links eigen doel, rechts vijandelijk. Sequentieel: één tint, donker → licht.
  const W = 500, H = 300, kolW = W / zones.length, rijH = H / 3
  const max = Math.max(...zones.flat())
  let s = `<rect x="0" y="0" width="${W}" height="${H}" rx="10" fill="var(--paneel-2)"/>`
  zones.forEach((kol, i) => kol.forEach((v, j) => {
    const t = v / max
    s += `<rect x="${i * kolW + 2}" y="${j * rijH + 2}" width="${kolW - 4}" height="${rijH - 4}" rx="6" fill="#2ec4c4" fill-opacity="${0.08 + t * 0.72}"><title>${v}% van de speeltijd</title></rect>`
    s += `<text x="${i * kolW + kolW / 2}" y="${j * rijH + rijH / 2}" text-anchor="middle" dominant-baseline="middle" class="hm-tekst" fill="${t > 0.6 ? '#0a0d13' : 'var(--tekst-2)'}">${v}%</text>`
  }))
  s += `<line x1="${W / 2}" y1="0" x2="${W / 2}" y2="${H}" stroke="var(--tekst-3)" stroke-dasharray="4 4"/>`
  s += `<rect x="-14" y="${H / 2 - 50}" width="12" height="100" rx="3" fill="var(--blauw)" opacity=".7"/><rect x="${W + 2}" y="${H / 2 - 50}" width="12" height="100" rx="3" fill="var(--oranje)" opacity=".7"/>`
  return `<svg viewBox="-20 -6 540 312" class="heatmap">${s}</svg>
    <div class="hm-as"><span>← eigen doel</span><span class="schaal"><i style="opacity:.15"></i><i style="opacity:.4"></i><i style="opacity:.65"></i><i style="opacity:.9"></i> aandeel speeltijd</span><span>vijandelijk doel →</span></div>`
}

export function afwerkingGrafiek(punten) {
  const W = 560, H = 220, pad = { l: 34, r: 12, t: 12, b: 26 }
  const ys = punten.flat(), min = Math.min(0, ...ys) - 0.5, max = Math.max(...ys) + 0.5
  const x = (i) => pad.l + (i / Math.max(1, punten.length - 1)) * (W - pad.l - pad.r)
  const y = (v) => pad.t + (1 - (v - min) / (max - min)) * (H - pad.t - pad.b)
  const band = punten.map(([, l], i) => `${x(i)},${y(l)}`).join(' ') + ' ' + punten.map(([, , h], i) => `${x(i)},${y(h)}`).reverse().join(' ')
  let s = ''
  for (let v = Math.ceil(min); v <= max; v += (max - min > 8 ? 2 : 1)) s += `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--rand)" stroke-width="${v === 0 ? 1.5 : 1}"/><text x="${pad.l - 8}" y="${y(v)}" text-anchor="end" dominant-baseline="middle" class="as-tekst">${v > 0 ? '+' : ''}${v}</text>`
  s += `<polygon points="${band}" fill="var(--tier-goed)" fill-opacity=".12"/>`
  s += `<polyline points="${punten.map(([v], i) => `${x(i)},${y(v)}`).join(' ')}" fill="none" stroke="var(--tier-goed)" stroke-width="2" stroke-linejoin="round"/>`
  const [lv] = punten.at(-1)
  s += `<circle cx="${x(punten.length - 1)}" cy="${y(lv)}" r="4.5" fill="var(--tier-goed)" stroke="var(--paneel)" stroke-width="2"/>`
  s += `<text x="${x(punten.length - 1) - 8}" y="${y(lv) - 12}" text-anchor="end" class="as-tekst" fill="var(--tekst)">${lv > 0 ? "+" : ""}${lv.toFixed(1).replace('.', ',')} goals</text>`
  for (const g of (punten.length <= 6 ? punten.map((_, i) => i + 1) : [1, Math.round(punten.length / 2), punten.length])) s += `<text x="${x(g - 1)}" y="${H - 6}" text-anchor="middle" class="as-tekst">${g}</text>`
  return `<svg viewBox="0 0 ${W} ${H}" class="lijngrafiek">${s}</svg>`
}

export function tekenVoorbeeld(el) {
  const v = VOORBEELD
  const [, rTier, rKl, rBg] = tier(v.rating.p)
  el.innerHTML = `
  <div class="banner">Voorbeelddata. Dit scherm laat het ontwerp zien; de echte waarden komen zodra de modellen en rank-benchmarks er zijn.</div>
  <header class="profielkop kaart">
    <div class="avatar">VS</div>
    <div class="profiel-id">
      <div class="profiel-naam">${v.naam}</div>
      <div><span class="chip">${v.rank}</span><span class="chip">${v.mode}</span><span class="chip">S${v.seizoen}</span><span class="chip">${v.games} wedstrijden · ${v.uren.toString().replace('.', ',')} u</span></div>
    </div>
    <div class="profiel-rating">
      <div class="profiel-rating-kop"><span>Rating</span><span class="dim">t.o.v. ${v.rank} ${v.mode}</span></div>
      <div class="profiel-rating-rij">
        <span class="rating-groot num" style="color:${rKl};background:${rBg}">${v.rating.waarde.toFixed(1).replace('.', ',')}</span>
        <div style="flex:1">${ratingBalk(v.rating)}</div>
      </div>
      <div class="dim" style="font-size:12px">${rTier} · 80%-interval ${v.rating.laag.toFixed(1).replace('.', ',')}–${v.rating.hoog.toFixed(1).replace('.', ',')} · betrouwbaar (≥ 30 games)</div>
    </div>
  </header>

  <section class="tegels">
    ${v.tegels.map((t) => `
      <div class="kaart tegel">
        <div class="tegel-kop"><span>${t.label}</span>${pChip(t.p)}</div>
        <div class="tegel-waarde num">${t.waarde}</div>
        ${sparkline(t.reeks, t.p)}
        <div class="tegel-voet">${t.onzeker ? `<span class="onzeker">◔ ${t.onzeker}</span>` : '<span class="dim">laatste 10 wedstrijden</span>'}</div>
      </div>`).join('')}
  </section>

  <section class="profielraster">
    <div class="kaart">
      <div class="kaart-kop"><span>Percentielen</span><span class="sub">t.o.v. ${v.rank} · ${v.mode} · min. 10 games</span></div>
      <div class="pgroepen">
        ${v.groepen.map(([naam, rijen]) => `<div class="pgroep"><div class="pgroep-kop">${naam}</div>${rijen.map(percentielRij).join('')}</div>`).join('')}
      </div>
      <div class="tierlegenda">${TIER.slice().reverse().map(([g, n, kl]) => `<span><i style="background:${kl}"></i>${n}</span>`).join('')}<span class="dim">· streep = rank-gemiddelde (p50)</span></div>
    </div>
    <div class="kaart">
      <div class="kaart-kop"><span>Speelstijl</span><span class="sub">percentiel per vaardigheid</span></div>
      ${vingerafdruk(v.vingerafdruk)}
    </div>
    <div class="kaart">
      <div class="kaart-kop"><span>Positie op het veld</span>
        <div class="knoppen"><button class="actief">Aandeel tijd</button><button>t.o.v. rank</button></div></div>
      ${heatmap(v.zones)}
    </div>
    <div class="kaart">
      <div class="kaart-kop"><span>Afwerking boven verwachting</span><span class="sub">cumulatief goals − xG · 80%-band</span></div>
      ${afwerkingGrafiek(v.afwerking)}
      <div class="dim" style="font-size:12px;margin-top:4px">Band wordt smaller naarmate er meer schoten zijn. Zolang de band de nul raakt, is "goede afwerker" nog niet bewezen.</div>
    </div>
    <div class="kaart kaart-breed">
      <div class="kaart-kop"><span>Betrouwbaarheid</span><span class="sub">hoeveel data nodig voordat een stat stabiel is (split-half r ≥ 0,7)</span></div>
      <div class="stabiel">
        ${v.stabiel.map(([naam, heb, nodig, eenheid = 'games']) => {
          const f = Math.min(1, heb / nodig), klaar = heb >= nodig
          return `<div class="stabiel-rij"><span>${naam}</span>
            <div class="stabiel-spoor"><i style="width:${f * 100}%;background:${klaar ? 'var(--tier-top)' : 'var(--tekst-3)'}"></i></div>
            <span class="num ${klaar ? '' : 'dim'}">${klaar ? '✓ stabiel' : `${heb}/${nodig} ${eenheid}`}</span></div>`
        }).join('')}
      </div>
    </div>
  </section>`
}
