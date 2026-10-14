// Modellen-pagina: hoe goed zijn xG en xPass, op hoeveel data, en per rank.

const NAAM_FEATURE = {
  mis_afstand: 'Hoe ver naast het doel', t_doel: 'Tijd tot de doellijn', verdediger_min_v: 'Snelheid die verdediger nodig heeft',
  snelheid_naar_doel: 'Balsnelheid richting doel', ingang_z: 'Hoogte in het doel', afstand: 'Afstand tot doel', ingang_x: 'Plek in het doel (breedte)',
  rank: 'Rank', verdediger_2e_v: 'Tweede verdediger', schutter_z: 'Hoogte schutter', hoek: 'Hoek', bal_z: 'Balhoogte', bal_snelheid: 'Balsnelheid',
  verdedigers_in_doel: 'Verdedigers in doel', verdedigers_tussen: 'Verdedigers tussen bal en doel', op_doel: 'Op doel', verdediger_boost: 'Boost verdedigers',
  schutter_boost: 'Boost schutter', aanvaller_dichtbij: 'Teamgenoot dichtbij',
}
const RANK = { gemengd: 'Gemengd', gold: 'Gold', platinum: 'Platinum', diamond: 'Diamond', champion: 'Champion', 'grand-champion': 'GC+' }
const rankNaam = (band) => { const l = band.split('_')[1] ?? band; return RANK[l.replace(/-\d$/, '')] ?? l }
const nl = (v, d = 0) => Number(v).toLocaleString('nl-NL', { minimumFractionDigits: d, maximumFractionDigits: d })

async function json(url) { try { const r = await fetch(url); return r.ok ? r.json() : null } catch { return null } }
async function regels(url) { try { const r = await fetch(url); return r.ok ? (await r.text()).trim().split('\n').filter(Boolean).map((x) => JSON.parse(x)) : [] } catch { return [] } }

function kalibratieSvg(alle, sleutelN) {
  const rijen = alle.filter((r) => r[sleutelN] >= 50) // te weinig gevallen = ruis, niet tekenen
  const W = 400, H = 300, p = { l: 38, r: 12, t: 10, b: 30 }
  const x = (v) => p.l + v * (W - p.l - p.r), y = (v) => p.t + (1 - v) * (H - p.t - p.b)
  const maxN = Math.max(...rijen.map((r) => r[sleutelN]))
  let s = ''
  for (const v of [0, 0.25, 0.5, 0.75, 1]) {
    s += `<line x1="${x(0)}" x2="${x(1)}" y1="${y(v)}" y2="${y(v)}" stroke="var(--rand)"/><text x="${p.l - 6}" y="${y(v)}" text-anchor="end" dominant-baseline="middle" class="as-tekst">${Math.round(v * 100)}%</text>`
    s += `<text x="${x(v)}" y="${H - 10}" text-anchor="middle" class="as-tekst">${Math.round(v * 100)}%</text>`
  }
  s += `<line x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}" stroke="var(--tekst-3)" stroke-dasharray="4 4"/>`
  s += `<polyline points="${rijen.map((r) => `${x(r.voorspeld)},${y(r.echt)}`).join(' ')}" fill="none" stroke="var(--accent)" stroke-width="2"/>`
  for (const r of rijen) {
    s += `<circle cx="${x(r.voorspeld)}" cy="${y(r.echt)}" r="${4 + 8 * Math.sqrt(r[sleutelN] / maxN)}" fill="var(--accent)" fill-opacity=".85" stroke="var(--paneel)" stroke-width="2">
      <title>voorspeld ${nl(r.voorspeld * 100, 1)}% · echt ${nl(r.echt * 100, 1)}% · ${nl(r[sleutelN])} gevallen</title></circle>`
  }
  return `<svg viewBox="0 0 ${W} ${H}" class="lijngrafiek">${s}</svg>`
}

function lijnSvg(punten, label) {
  // punten: [{x, y}] ; één reeks, geen legenda nodig
  const W = 400, H = 170, p = { l: 44, r: 12, t: 14, b: 26 }
  if (!punten.length) return '<div class="dim">Nog geen rondes</div>'
  const xs = punten.map((q) => q.x), ys = punten.map((q) => q.y)
  const x0 = Math.min(...xs), x1 = Math.max(...xs, x0 + 1)
  const y0 = Math.min(...ys) - 0.01, y1 = Math.max(...ys) + 0.01
  const x = (v) => p.l + ((v - x0) / (x1 - x0)) * (W - p.l - p.r), y = (v) => p.t + (1 - (v - y0) / (y1 - y0)) * (H - p.t - p.b)
  let s = ''
  for (const v of [y0, (y0 + y1) / 2, y1]) s += `<line x1="${p.l}" x2="${W - p.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--rand)"/><text x="${p.l - 6}" y="${y(v)}" text-anchor="end" dominant-baseline="middle" class="as-tekst">${nl(v, 3)}</text>`
  s += `<polyline points="${punten.map((q) => `${x(q.x)},${y(q.y)}`).join(' ')}" fill="none" stroke="var(--accent)" stroke-width="2"/>`
  for (const q of punten) s += `<circle cx="${x(q.x)}" cy="${y(q.y)}" r="4.5" fill="var(--accent)" stroke="var(--paneel)" stroke-width="2"><title>${label} ${nl(q.y, 3)} bij ${q.x} Champion-replays</title></circle>`
  s += `<text x="${p.l}" y="${H - 6}" class="as-tekst">${x0}</text><text x="${W - p.r}" y="${H - 6}" text-anchor="end" class="as-tekst">${x1} Champion-replays</text>`
  return `<svg viewBox="0 0 ${W} ${H}" class="lijngrafiek">${s}</svg>`
}

function balken(items, fmt, max = Math.max(...items.map((i) => i.v))) {
  return items.map((i) => `<div class="mbalk" title="${i.titel ?? ''}">
    <span class="mbalk-label">${i.label}</span>
    <div class="mbalk-spoor"><i style="width:${(100 * i.v) / (max || 1)}%;background:${i.kleur ?? 'var(--accent)'}"></i></div>
    <span class="mbalk-waarde num">${fmt(i.v)}</span></div>`).join('')
}

export async function tekenModellen(el) {
  el.innerHTML = '<div class="dim">Laden…</div>'
  const [xg, xp, hist, sp] = await Promise.all([json('/modellen/xg.json'), json('/modellen/xpass.json'), regels('/modellen/geschiedenis.jsonl'), json('/modellen/steekproef.json')])
  if (!xg) { el.innerHTML = '<div class="dim">Nog geen getraind model.</div>'; return }
  const v = xg.validatie
  const bands = xg.per_band ?? []
  const xpBand = Object.fromEntries((xp?.per_band ?? []).map((r) => [r.band, r]))
  const belang = Object.entries(xg.belang).slice(0, 8)
  const laatste = hist.at(-1)

  el.innerHTML = `
  <div class="catalogus-kop">
    <div><h1>Modellen</h1><p class="dim">Hoe goed voorspellen xG en xPass, getest op wedstrijden die het model niet heeft gezien. Wordt elk uur bijgewerkt met nieuwe Champion-replays.</p></div>
    <div class="catalogus-tellers">
      <div><span class="num">${nl(xg.wedstrijden)}</span><span class="dim">wedstrijden</span></div>
      <div><span class="num">${nl(xg.schoten)}</span><span class="dim">schoten</span></div>
      <div><span class="num">${nl(xp?.n ?? 0)}</span><span class="dim">balcontacten</span></div>
    </div>
  </div>

  <section class="modelraster">
    <div class="kaart">
      <div class="kaart-kop"><h3>xG: hoe goed onderscheidt het?</h3><span class="sub">AUC · 0,5 = gokken · 1 = perfect</span></div>
      ${balken([
        { label: 'Altijd gemiddelde', v: v['basis (altijd gemiddelde)'].auc, kleur: 'var(--tekst-3)' },
        { label: 'Simpel (afstand, hoek, op doel)', v: v['simpel (afstand+hoek+op doel)'].auc, kleur: 'var(--tekst-2)' },
        { label: 'Ons xG-model', v: v['xG-model'].auc },
      ], (x) => nl(x, 3), 1)}
      <div class="mnoot">Brier ${nl(v['xG-model'].brier, 3)} · logloss ${nl(v['xG-model'].logloss, 3)} (lager = beter)</div>
    </div>

    <div class="kaart">
      <div class="kaart-kop"><h3>xPass: physics-formule vs model</h3><span class="sub">verwacht vs echt aangekomen</span></div>
      ${xp ? balken([
        { label: 'Echt aangekomen', v: xp.echt, kleur: 'var(--tekst-2)' },
        { label: 'xPass-model verwachtte', v: xp.verwacht },
      ], (x) => nl(x), Math.max(xp.echt, xp.verwacht) * 1.05) : ''}
      <div class="mnoot">AUC model ${nl(xp?.auc ?? 0, 3)} · eerste physics-formule ${nl(xp?.naief_auc ?? 0, 3)} en verwachtte ~2,8× te veel</div>
    </div>

    <div class="kaart">
      <div class="kaart-kop"><h3>Data per rank</h3><span class="sub">wedstrijden</span></div>
      ${balken(bands.map((b) => ({ label: rankNaam(b.band), v: b.wedstrijden, kleur: rankNaam(b.band) === 'Champion' ? 'var(--accent)' : 'var(--tekst-3)' })), (x) => nl(x))}
      <div class="mnoot">Champion groeit doorlopend (doel 5.000)</div>
    </div>

    <div class="kaart kaart-hoog">
      <div class="kaart-kop"><h3>Kalibratie xG</h3><span class="sub">voorspeld vs echt raak · op de stippellijn = klopt</span></div>
      ${kalibratieSvg(xg.kalibratie, 'schoten')}
    </div>
    <div class="kaart kaart-hoog">
      <div class="kaart-kop"><h3>Kalibratie xPass</h3><span class="sub">voorspeld vs echt aangekomen</span></div>
      ${xp ? kalibratieSvg(xp.kalibratie, 'n') : ''}
    </div>
    <div class="kaart kaart-hoog">
      <div class="kaart-kop"><h3>Wat telt het zwaarst (xG)</h3><span class="sub">hoeveel slechter zonder</span></div>
      ${balken(belang.map(([k, w]) => ({ label: NAAM_FEATURE[k] ?? k, v: w })), (x) => nl(x, 3))}
    </div>

    <div class="kaart kaart-breed">
      <div class="kaart-kop"><h3>Per rank</h3><span class="sub">zelfde model, apart gemeten</span></div>
      <div class="tabel-wrap"><table class="tabel">
        <thead><tr><th class="links">Rank</th><th>Wedstrijden</th><th>Schoten / wedstrijd</th><th>% raak</th><th>Goals − xG</th><th>AUC xG</th><th>Pass komt aan</th><th>AUC xPass</th></tr></thead>
        <tbody>${bands.map((b) => { const p = xpBand[b.band]; return `<tr>
          <td class="links"><b>${rankNaam(b.band)}</b></td><td class="num">${nl(b.wedstrijden)}</td><td class="num">${nl(b.schoten_per_wedstrijd, 1)}</td>
          <td class="num">${nl(b.raak * 100, 1)}%</td><td class="num">${b.goals_min_xg > 0 ? '+' : ''}${nl(b.goals_min_xg, 1)}</td><td class="num">${nl(b.auc, 3)}</td>
          <td class="num">${p ? nl(p.echt * 100, 1) + '%' : '–'}</td><td class="num">${p ? nl(p.auc, 3) : '–'}</td></tr>` }).join('')}</tbody>
      </table></div>
      <div class="mnoot">Champions schieten vaker maar maken een kleiner deel: betere verdediging, meer kansen van lage kwaliteit.</div>
    </div>

    <div class="kaart kaart-breed">
      <div class="kaart-kop"><h3>Model per rank</h3><span class="sub">eigen model vs algemeen model · eerlijk getest per wedstrijd · fout = gemiddelde kalibratiefout</span></div>
      <div class="tabel-wrap"><table class="tabel">
        <thead><tr><th class="links">Model</th><th class="links">Rank</th><th>Data</th><th>Algemeen: fout</th><th>Algemeen: verwacht</th><th>Eigen: fout</th><th>Eigen: verwacht</th><th>Echt</th><th class="links">Gebruikt</th></tr></thead>
        <tbody>${[['xG', xg.per_rank_model], ['xPass', xp?.per_rank_model]].flatMap(([m, lijst]) => (lijst ?? []).map((r) => `<tr>
          <td class="links">${m}</td><td class="links"><b>${r.rank}</b></td><td class="num">${nl(r.n)}</td>
          <td class="num">${nl(r.algemeen.ece * 100, 2)} pt</td><td class="num">${nl(r.algemeen.verwacht)}</td>
          <td class="num ${r.keuze === 'eigen' ? 'tint-goed' : ''}">${r.eigen ? nl(r.eigen.ece * 100, 2) + ' pt' : '–'}</td><td class="num">${r.eigen ? nl(r.eigen.verwacht) : '–'}</td>
          <td class="num">${nl(r.echt)}</td>
          <td class="links">${r.keuze === 'eigen' ? '<span class="chip st-ok">eigen model</span>' : `<span class="chip">${r.keuze}</span>`}</td></tr>`)).join('')}</tbody>
      </table></div>
      <div class="mnoot">Eigen model wint als het minstens even scherp is (logloss ≤1% slechter) én beter gekalibreerd: voor xG-totalen en goals − xG per speler telt kalibratie het zwaarst.</div>
    </div>

    ${sp ? `<div class="kaart kaart-breed">
      <div class="kaart-kop"><h3>Hoeveel data is nodig?</h3><span class="sub">wedstrijden per rank · α 0,05 · power 80%</span></div>
      <div class="tabel-wrap"><table class="tabel">
        <thead><tr><th class="links">Rank</th><th>Nu</th><th>Twee ranks vergelijken<br><span class="dim">4 pt verschil, halve kansen</span></th><th>Goals − xG per rank<br><span class="dim">±2% nauwkeurig</span></th><th>Afwerking per speler<br><span class="dim">±5 pt, eigen wedstrijden</span></th></tr></thead>
        <tbody>${sp.per_rank.map((r) => `<tr><td class="links"><b>${r.rank}</b></td><td class="num">${nl(r.wedstrijden_nu)}</td>
          <td class="num ${r.wedstrijden_nu >= r.nodig_rank_vergelijken ? 'tint-goed' : ''}">${nl(r.nodig_rank_vergelijken)}</td>
          <td class="num ${r.wedstrijden_nu >= r.nodig_goals_min_xg_2pct ? 'tint-goed' : ''}">${nl(r.nodig_goals_min_xg_2pct)}</td>
          <td class="num">${nl(r.nodig_speler_afwerking)}</td></tr>`).join('')}</tbody>
      </table></div>
      <div class="mnoot">Groen = er is al genoeg. Eigen model per rank: leercurve laat zien dat ~300 wedstrijden nodig zijn om het algemene model te evenaren, ~500 om het te verslaan.</div>
    </div>` : ''}

    <div class="kaart">
      <div class="kaart-kop"><h3>xG-AUC per ronde</h3><span class="sub">${hist.length} rondes</span></div>
      ${lijnSvg(hist.filter((r) => r.scores?.xg).map((r) => ({ x: r.champion_replays, y: r.scores.xg.auc })), 'AUC')}
    </div>
    <div class="kaart">
      <div class="kaart-kop"><h3>xPass-AUC per ronde</h3><span class="sub">${hist.length} rondes</span></div>
      ${lijnSvg(hist.filter((r) => r.scores?.xpass).map((r) => ({ x: r.champion_replays, y: r.scores.xpass.auc })), 'AUC')}
    </div>
    <div class="kaart">
      <div class="kaart-kop"><h3>Updater</h3><span class="sub">automatisch</span></div>
      <div class="mstatus">
        <div><span class="dim">Laatste ronde</span><span class="num">${laatste ? laatste.tijd.replace('T', ' ') : '–'}</span></div>
        <div><span class="dim">Champion-replays</span><span class="num">${laatste ? nl(laatste.champion_replays) : '–'} / 5.000</span></div>
        <div><span class="dim">Volgende ronde</span><span>±1 uur na de vorige</span></div>
        <div><span class="dim">Stoppen</span><span>bestand <code>data/STOP</code></span></div>
      </div>
    </div>
  </section>`
}
