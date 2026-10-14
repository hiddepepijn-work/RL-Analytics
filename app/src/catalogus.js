// Stats-catalogus: één bron voor teamstats, spelertabel en de catalogus-pagina.
// pad      = plek in data.stats.spelers[id] (null = nog niet beschikbaar)
// beter    = 'hoog' | 'laag' | null (neutraal, bv. stijlkeuze)
// status   = 'ok' (parser levert het) | 'afgeleid' (uit frames/events te berekenen) | 'model' (eigen ML-model nodig)
// team     = hoe teamwaarde ontstaat: 'som' | 'gem' | null (geen teamwaarde)
// voetbal  = waar de stat in voetbal-analytics op lijkt

import { UITLEG } from './uitleg.js'

const s = (id, label, pad, opties = {}) => ({ id, label, pad, beter: 'hoog', status: pad ? 'ok' : 'model', team: 'som', eenheid: '', ...opties })

export const GROEPEN = [
  {
    id: 'schieten', naam: 'Schieten', kort: 'SCH', vraag: 'Hoe gevaarlijk en hoe efficiënt?',
    stats: [
      s('goals', 'Goals', 'aanval.goals'),
      s('schoten', 'Schoten (game)', 'aanval.schoten', { uitleg: 'Wat Rocket League zelf als schot telt: alleen ballen die richting doel gaan en gered moeten worden' }),
      s('pogingen', 'Schotpogingen', 'aanval.schot_pogingen', { uitleg: 'Onze definitie: elke touch richting doel die op of net naast gaat; basis voor xG' }),
      s('schoten5', 'Schoten per 5 min', 'aanval.schoten_per_5', { team: 'som', decimalen: 2 }),
      s('rendement', 'Schotrendement', 'aanval.schotrendement', { eenheid: '%', team: 'gem' }),
      s('hard', 'Harde schoten', 'aanval.harde_schoten', { uitleg: 'Touches met grote snelheidswinst van de bal' }),
      s('onetimer', 'One-timers', 'aanval.one_timers'),
      s('halfvolley', 'Half-volleys', 'aanval.half_volleys'),
      s('xg', 'xG', 'aanval.xg', { voetbal: 'xG', decimalen: 2, uitleg: 'Som van de kans per schot dat hij erin gaat (afstand, hoek, balbaan, verdedigers)' }),
      s('xgschot', 'xG per schot', 'aanval.xg_per_schot', { voetbal: 'npxG/Sh', decimalen: 2, team: 'gem', uitleg: 'Gemiddelde kwaliteit van de kansen' }),
      s('xgot', 'xGOT', 'aanval.xgot', { voetbal: 'xGOT / PSxG', decimalen: 2, uitleg: 'xG ná de touch, alleen schoten die op doel gaan' }),
      s('opdoel', 'Schoten op doel', 'aanval.op_doel', { voetbal: 'Shots on target', uitleg: 'Schotpogingen waarvan de balbaan in het doel eindigt' }),
      s('gminxgot', 'Goals − xGOT', 'aanval.xgot_min_goals', { decimalen: 2, uitleg: 'Meer goals dan je schoten op doel waard waren = de keeper had pech, of je rebound viel goed' }),
      s('gminxg', 'Goals − xG', 'aanval.goals_min_xg', { voetbal: 'G − xG', decimalen: 2, uitleg: 'Afwerking boven verwachting (ruis bij weinig schoten!)' }),
      s('kwaliteit', 'Schot-kwaliteit', 'aanval.schot_kwaliteit', { decimalen: 2, voetbal: 'PSxG − xG / shooting goals added', uitleg: 'xG ná je touch − verwachte xG vóór je touch' }),
      s('grotekans', 'Grote kansen', 'aanval.grote_kansen', { voetbal: 'Big chances', uitleg: 'Kansen met xG ≥ 0,35, ook als je de bal miste' }),
      s('grotegemist', 'Grote kansen gemist', 'aanval.grote_kansen_gemist', { beter: 'laag', voetbal: 'Big chances missed' }),
      s('whiffkans', 'Kansen gewhifft', 'aanval.kansen_gewhifft', { beter: 'laag', uitleg: 'Kans op de aanvalshelft waarbij je de bal miste' }),
      s('whiffxg', 'Kans-xG gewhifft', 'aanval.kans_xg_gewhifft', { beter: 'laag', decimalen: 2, uitleg: 'Hoeveel xG je liet liggen door de bal te missen' }),
    ],
  },
  {
    id: 'passen', naam: 'Passen & creëren', kort: 'PAS', vraag: 'Maakt hij kansen voor anderen?',
    stats: [
      s('assists', 'Assists', 'passen.assists'),
      s('passes', 'Passes', 'passen.passes'),
      s('ontvangen', 'Passes ontvangen', 'passen.passes_ontvangen'),
      s('centers', 'Centers', 'passen.centers', { uitleg: 'Bal van de zijkant naar het midden voor het doel' }),
      s('passwinst', 'Pass-winst', 'passen.pass_winst_m', { eenheid: 'm', uitleg: 'Meters dat passes de bal richting doel brachten', voetbal: 'Progressive passes' }),
      s('xpass', 'xPass', 'passen.xpass', { decimalen: 1, voetbal: 'xPass', uitleg: 'Verwacht aantal passes dat aankomt, gegeven waar iedereen stond' }),
      s('pbv', 'Passes boven verwachting', 'passen.pass_boven_verwachting', { decimalen: 1, uitleg: 'Aangekomen passes − xPass' }),
      s('pwaarde', 'Pass-waarde', 'passen.pass_waarde', { decimalen: 2, voetbal: 'xT via passes', uitleg: 'xPass × hoe gevaarlijk de plek is waar de bal heen gaat' }),
      s('niemand', 'Ballen naar niemand', 'passen.naar_niemand', { beter: 'laag', uitleg: 'Bewust weggespeeld waar geen teamgenoot op tijd kon zijn' }),
      s('kansen', 'Kansen gecreëerd', 'passen.kansen_gecreeerd', { voetbal: 'Chances created / key passes', uitleg: 'Jouw touch zette een teamgenoot klaar voor een schot of kans' }),
      s('grotecreatie', 'Grote kansen gecreëerd', 'passen.grote_kansen_gecreeerd', { voetbal: 'Big chances created' }),
      s('xa', 'xA', 'passen.xa', { voetbal: 'xA', decimalen: 2, uitleg: 'Verwachte xG van de kans die je klaarlegt, vóór de touch van de schutter' }),
      s('sca', 'Schot-creërende acties', null, { status: 'afgeleid', voetbal: 'SCA / GCA', uitleg: 'De twee touches vóór een schot' }),
    ],
  },
  {
    id: 'balbezit', naam: 'Balbezit', kort: 'BEZ', vraag: 'Hoeveel en hoe goed aan de bal?',
    stats: [
      s('touches', 'Touches', 'balbezit.touches'),
      s('bezit', 'Balbezit', 'balbezit.bezit_pct', { eenheid: '%', team: 'som' }),
      s('eerste', 'Eerste touches', 'balbezit.eerste_touches', { beter: null, uitleg: 'Touches na een touch van iemand anders' }),
      s('controle', 'Controle-touches', 'balbezit.controle_touches', { uitleg: 'Zachte touches om de bal onder controle te houden' }),
      s('controletijd', 'Tijd in controle', 'balbezit.controle_tijd', { eenheid: 's', decimalen: 1 }),
      s('vooruit', 'Bal vooruit', 'balbezit.bal_vooruit_m', { eenheid: 'm', voetbal: 'Progressive carries' }),
      s('xt', 'Touch-waarde (xT)', null, { voetbal: 'xT / EPV / OBV', uitleg: 'Verandering in goal-kans door jouw touch' }),
    ],
  },
  {
    id: 'verdedigen', naam: 'Verdedigen', kort: 'VER', vraag: 'Houdt hij de nul?',
    stats: [
      s('saves', 'Saves', 'verdedigen.saves'),
      s('clears', 'Clears', 'verdedigen.clears'),
      s('achterbal', 'Tijd achter de bal', 'verdedigen.achter_bal_pct', { eenheid: '%', team: 'gem' }),
      s('schaduw', 'Schaduwverdediging', 'verdedigen.schaduw_pct', { eenheid: '%', team: 'gem', decimalen: 1, uitleg: 'Meerijden tussen aanvaller en doel zonder aan te vallen' }),
      s('laatsteman', 'Tegengoal als laatste man', 'verdedigen.tegengoal_als_laatste_man', { beter: 'laag' }),
      s('tevervoor', 'Te ver voor bij tegengoal', 'verdedigen.tegengoal_te_ver_voor', { beter: 'laag' }),
      s('fout', 'Fouten voor tegengoal', 'verdedigen.fouten_voor_tegengoal', { beter: 'laag', voetbal: 'Errors leading to goal', uitleg: 'Whiff of balverlies waaruit de tegengoal viel' }),
      s('sbv', 'Goals voorkomen', 'verdedigen.goals_voorkomen', { voetbal: 'Goals prevented (PSxG)', decimalen: 2, uitleg: 'xGOT van de schoten die je tegenhield' }),
    ],
  },
  {
    id: 'duels', naam: 'Duels', kort: 'DUE', vraag: 'Wint hij de ballen?',
    stats: [
      s('5050w', '50/50 gewonnen', 'duels.5050_gewonnen'),
      s('5050v', '50/50 verloren', 'duels.5050_verloren', { beter: 'laag' }),
      s('whiffs', 'Whiffs', 'duels.whiffs', { beter: 'laag', uitleg: 'Bal gemist terwijl hij er vlak bij was' }),
      s('telaat', 'Te laat bij de bal', 'duels.te_laat_bij_bal', { beter: 'laag' }),
      s('demos', "Demo's gemaakt", 'duels.demos_gemaakt'),
      s('demosin', "Demo's gekregen", 'duels.demos_gekregen', { beter: 'laag' }),
      s('bumps', 'Bumps', 'duels.bumps'),
    ],
  },
  {
    id: 'kickoffs', naam: 'Kickoffs', kort: 'KO', vraag: 'Wie start sterker?',
    stats: [
      s('kow', 'Kickoffs gewonnen', 'duels.kickoffs_gewonnen'),
      s('kov', 'Kickoffs verloren', 'duels.kickoffs_verloren', { beter: 'laag' }),
      s('speedflips', 'Speedflips', 'mechanics.speed_flip'),
      s('sfkwal', 'Speedflip-kwaliteit', 'mechanics.speedflip_kwaliteit', { team: 'gem', decimalen: 2 }),
      s('cheats', 'Cheats', 'mechanics.kickoff_cheats', { beter: null, uitleg: 'Tweede man die naar voren komt voor de kickoff' }),
      s('fakes', 'Fakes', 'mechanics.kickoff_fakes', { beter: null }),
    ],
  },
  {
    id: 'boost', naam: 'Boost', kort: 'BST', vraag: 'Beheert hij zijn boost slim?',
    stats: [
      s('bpm', 'Boost per minuut', 'boost.per_minuut', { team: 'gem', beter: null }),
      s('gem', 'Gemiddelde boost', 'boost.gemiddeld', { team: 'gem' }),
      s('verzameld', 'Verzameld', 'boost.verzameld'),
      s('gestolen', 'Gestolen', 'boost.gestolen', { uitleg: 'Boost gepakt op de helft van de tegenstander' }),
      s('grote', 'Grote pads', 'boost.grote_pads'),
      s('kleine', 'Kleine pads', 'boost.kleine_pads'),
      s('nul', 'Tijd op 0 boost', 'boost.tijd_0_pct', { eenheid: '%', beter: 'laag', team: 'gem' }),
      s('overvol', 'Verspild (overvol)', 'boost.overvol', { beter: 'laag', uitleg: 'Boost gepakt boven de 100' }),
      s('ss', 'Verbruik op supersonic', 'boost.supersonic_verbruik', { beter: 'laag', uitleg: 'Boost geven terwijl je al op topsnelheid bent' }),
    ],
  },
  {
    id: 'positie', naam: 'Positie', kort: 'POS', vraag: 'Staat hij op de goede plek?',
    stats: [
      s('verdediging', 'Verdedigend derde', 'positie.derden_pct.0', { eenheid: '%', team: 'gem', beter: null }),
      s('midden', 'Middelste derde', 'positie.derden_pct.1', { eenheid: '%', team: 'gem', beter: null }),
      s('aanval', 'Aanvallend derde', 'positie.derden_pct.2', { eenheid: '%', team: 'gem', beter: null }),
      s('dichtst', 'Dichtst bij de bal', 'positie.dichtst_bij_bal_pct', { eenheid: '%', team: null, beter: null }),
      s('afstbal', 'Afstand tot de bal', 'positie.afstand_bal', { eenheid: 'uu', team: 'gem', beter: null }),
      s('afstmaat', 'Afstand tot teamgenoot', 'positie.afstand_teamgenoot', { eenheid: 'uu', team: 'gem', beter: null, uitleg: 'Spreiding: te dicht = double commits, te ver = gaten' }),
      s('aanspeelbaar', 'Aanspeelbaar', 'passen.aanspeelbaar_pct', { eenheid: '%', team: 'gem', uitleg: 'Als je teamgenoot de bal raakt: hoe vaak kon jij binnen 2 s op een steunplek (1000–2600 uu voor/naast de bal) zijn' }),
      s('gemist', 'Gemiste ontvangsten', 'passen.gemiste_ontvangsten', { beter: 'laag', uitleg: 'Goede pass (xPass ≥ 50%) naar jou, maar je raakte hem niet' }),
      s('beschikbaar', 'Ontvangen boven verwachting', 'passen.ontvangst_boven_verwachting', { decimalen: 1, uitleg: 'Passes die je echt raakte − hoeveel je er volgens xPass had moeten raken' }),
      s('pitch', 'Veldcontrole', null, { voetbal: 'Pitch control', uitleg: 'Deel van het veld waar jij als eerste kunt zijn' }),
    ],
  },
  {
    id: 'rotatie', naam: 'Rotatie', kort: 'ROT', vraag: 'Draait hij goed mee?',
    stats: [
      s('eerste', 'Tijd als 1e man', 'rotatie.rollen_pct.0', { eenheid: '%', team: null, beter: null }),
      s('tweede', 'Tijd als 2e man', 'rotatie.rollen_pct.1', { eenheid: '%', team: null, beter: null }),
      s('derde', 'Tijd als 3e man', 'rotatie.rollen_pct.2', { eenheid: '%', team: null, beter: null }),
      s('wissels', '1e-man-wissels', 'rotatie.eerste_man_wissels', { beter: null }),
      s('meestachter', 'Tijd als laatste man', 'positie.meest_achter_pct', { eenheid: '%', team: null, beter: null }),
      s('double', 'Double commits', null, { status: 'afgeleid', beter: 'laag', uitleg: 'Twee teamgenoten tegelijk op de bal' }),
      s('discipline', 'Rotatie-discipline', null, { status: 'afgeleid', uitleg: 'Terug via de achterpaal, niet door het midden' }),
    ],
  },
  {
    id: 'beweging', naam: 'Beweging', kort: 'BEW', vraag: 'Hoe snel en hoe efficiënt?',
    stats: [
      s('snelheid', 'Gem. snelheid', 'beweging.gem_snelheid', { eenheid: 'uu/s', team: 'gem' }),
      s('ssp', 'Tijd supersonic', 'beweging.supersonic_pct', { eenheid: '%', team: 'gem' }),
      s('afstand', 'Afgelegd', 'beweging.afstand_km', { eenheid: 'km', decimalen: 2, beter: null }),
      s('grond', 'Op de grond', 'beweging.grond_pct', { eenheid: '%', team: 'gem', beter: null }),
      s('lucht', 'Hoog in de lucht', 'beweging.hoog_lucht_pct', { eenheid: '%', team: 'gem', beter: null }),
      s('powerslides', 'Powerslides', 'beweging.powerslides', { beter: null }),
      s('herstel', 'Hersteltijd na landing', null, { status: 'afgeleid', beter: 'laag' }),
    ],
  },
  {
    id: 'mechanics', naam: 'Mechanics', kort: 'MEC', vraag: 'Welke technieken gebruikt hij?',
    stats: [
      s('lucht_t', 'Lucht-touches', 'balbezit.lucht_touches'),
      s('hoog_t', 'Hoge lucht-touches', 'balbezit.hoge_lucht_touches'),
      s('wavedash', 'Wavedashes', 'mechanics.wavedash'),
      s('halfflip', 'Half-flips', 'mechanics.half_flip'),
      s('flick', 'Flicks', 'mechanics.flick'),
      s('reset', 'Flip resets', 'mechanics.flip_reset'),
      s('airdribble', 'Air dribbles', 'mechanics.air_dribble'),
      s('wallaerial', 'Wall aerials', 'mechanics.wall_aerial'),
      s('backboard', 'Backboard-reads', 'aanval.backboards'),
    ],
  },
  {
    id: 'impact', naam: 'Impact', kort: 'IMP', vraag: 'Hoeveel maakt hij het verschil?',
    stats: [
      s('rating', 'Rating', 'impact.rating', { decimalen: 1, team: 'gem' }),
      s('impact', 'Impact (goal-equivalenten)', 'impact.impact', { decimalen: 2 }),
      s('r_schieten', 'Cijfer schieten', 'impact.Schieten', { decimalen: 1, team: 'gem' }),
      s('r_passen', 'Cijfer passen', 'impact.Passen', { decimalen: 1, team: 'gem' }),
      s('r_verdedigen', 'Cijfer verdedigen', 'impact.Verdedigen', { decimalen: 1, team: 'gem' }),
      s('r_duels', 'Cijfer duels', 'impact.Duels', { decimalen: 1, team: 'gem' }),
      s('r_kickoffs', 'Cijfer kickoffs', 'impact.Kickoffs', { decimalen: 1, team: 'gem' }),
      s('r_balbezit', 'Cijfer balbezit', 'impact.Balbezit', { decimalen: 1, team: 'gem' }),
      s('swing', 'Win-kans-swing', null, { voetbal: 'HLTV Round Swing', uitleg: 'Verandering in win-kans door jouw acties' }),
      s('rapm', 'RAPM', null, { voetbal: 'Plus-minus (basketbal)', uitleg: 'Eigen bijdrage los van teamgenoten, over veel wedstrijden' }),
      s('consistentie', 'Consistentie', null, { status: 'afgeleid', uitleg: 'Spreiding van rating per wedstrijd' }),
      s('clutch', 'Clutch', null, { status: 'afgeleid', uitleg: 'Impact in laatste minuut / overtime bij gelijke stand' }),
    ],
  },
]

// Uitleg uit uitleg.js aan elke stat hangen (sleutel 'groep.id'), en groep-id meegeven voor de ⓘ-popover
for (const g of GROEPEN) for (const st of g.stats) { st.groep = g.id; st.uitleg = UITLEG[`${g.id}.${st.id}`] ?? st.uitleg }
export const STAT_OP_PAD = Object.fromEntries(GROEPEN.flatMap((g) => g.stats.filter((x) => x.pad).map((x) => [x.pad, x])))

export const waarde = (st, pad) => pad.split('.').reduce((o, k) => (o == null ? o : o[k]), st)

export function format(stat, v) {
  if (v == null || Number.isNaN(v)) return '–'
  const d = stat.decimalen ?? (stat.eenheid === '%' ? 0 : 0)
  const getal = Number(v).toLocaleString('nl-NL', { minimumFractionDigits: d, maximumFractionDigits: d })
  return stat.eenheid === '%' ? `${getal}%` : stat.eenheid && stat.eenheid !== 'uu' && stat.eenheid !== 'uu/s' ? `${getal} ${stat.eenheid}` : getal
}

export function teamWaarde(stat, data, team) {
  const ids = data.spelers.filter((x) => x.team === team).map((x) => x.id)
  const vs = ids.map((id) => waarde(data.stats.spelers[id], stat.pad)).filter((v) => v != null)
  if (!vs.length || !stat.team) return null
  if (stat.id === 'bezit') return data.stats.teams[team].bezit_pct
  const som = vs.reduce((a, b) => a + b, 0)
  return stat.team === 'gem' ? som / vs.length : som
}
