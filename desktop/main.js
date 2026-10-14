// RL Analytics — desktop-app.
// 1. Venster met de stats (de site op de VPS), logt zelf in met versleuteld opgeslagen gegevens.
// 2. Systeemvak-icoon: blijft actief als het venster dicht is.
// 3. Bewaakt de Rocket League-replaymap en stuurt nieuwe replays via SSH naar de server-inbox;
//    zodra de server de wedstrijd heeft verwerkt komt er een melding met de uitslag.
const { app, BrowserWindow, Tray, Menu, Notification, safeStorage, nativeImage, ipcMain, shell, screen } = require('electron')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const { execFile } = require('node:child_process')

const URL_SITE = 'https://rl.51-75-74-94.sslip.io'
const SERVER = 'ubuntu@51.75.74.94'
const INBOX = '/var/lib/rl-analytics-inbox'
const REPLAYMAPPEN = [
  path.join(os.homedir(), 'Documents', 'My Games', 'Rocket League', 'TAGame', 'DemosEpic'),
  path.join(os.homedir(), 'Documents', 'My Games', 'Rocket League', 'TAGame', 'Demos'),
]
const SSH_MAP = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'OpenSSH')
const DATA = app.getPath('userData')
const CONFIG = path.join(DATA, 'config.json')
const GEZIEN = path.join(DATA, 'gezien.json')
const LOG = path.join(DATA, 'app.log')
const BRON = (n) => path.join(app.isPackaged ? process.resourcesPath : __dirname, app.isPackaged ? 'app.asar' : '', n)

let venster = null, tray = null, inlogVenster = null
const verborgenStart = process.argv.includes('--verborgen')

function log(t) { fs.appendFileSync(LOG, `[${new Date().toISOString()}] ${t}\n`) }
const leesJson = (p, standaard) => { try { return JSON.parse(fs.readFileSync(p, 'utf8')) } catch { return standaard } }
const schrijfJson = (p, d) => fs.writeFileSync(p, JSON.stringify(d, null, 1))

// ── Inloggegevens (versleuteld met Windows-gebruikerssleutel via safeStorage) ──
function gegevens() {
  const c = leesJson(CONFIG, {})
  if (c.gebruiker && c.wachtwoord) {
    try { return { gebruiker: c.gebruiker, wachtwoord: safeStorage.decryptString(Buffer.from(c.wachtwoord, 'base64')) } } catch {}
  }
  // Eerste start op Hidde's pc: gegevens uit RL-Analytics\toegang.txt overnemen (alleen als dat bestand bestaat)
  const t = path.join(os.homedir(), 'Documents', 'RL-Analytics', 'toegang.txt')
  if (fs.existsSync(t)) {
    const s = fs.readFileSync(t, 'utf8')
    const g = s.match(/Gebruiker: (.+)/)?.[1]?.trim(), w = s.match(/Wachtwoord: (.+)/)?.[1]?.trim()
    if (g && w) { bewaarGegevens(g, w); return { gebruiker: g, wachtwoord: w } }
  }
  return null
}
function bewaarGegevens(gebruiker, wachtwoord) {
  const c = leesJson(CONFIG, {})
  schrijfJson(CONFIG, { ...c, gebruiker, wachtwoord: safeStorage.encryptString(wachtwoord).toString('base64') })
}

function vraagGegevens() {
  return new Promise((klaar) => {
    if (inlogVenster) return inlogVenster.focus()
    inlogVenster = new BrowserWindow({ width: 420, height: 380, resizable: false, parent: venster ?? undefined, modal: !!venster,
      backgroundColor: '#06070c', autoHideMenuBar: true, icon: BRON('bouw/icon.png'), title: 'RL Analytics — inloggen',
      webPreferences: { preload: undefined, contextIsolation: true, nodeIntegration: false, sandbox: true } })
    inlogVenster.loadFile(BRON('inloggen.html'))
    ipcMain.removeAllListeners('rl-inloggen')
    inlogVenster.webContents.on('will-navigate', (e, u) => {
      // Het formulier navigeert naar rl-inloggen://?g=..&w=.. ; vang dat af i.p.v. een preload-brug
      if (!u.startsWith('rl-inloggen:')) return
      e.preventDefault()
      const q = new URL(u.replace('rl-inloggen:', 'http://x/')).searchParams
      bewaarGegevens(q.get('g'), q.get('w'))
      inlogVenster.close(); inlogVenster = null
      klaar({ gebruiker: q.get('g'), wachtwoord: q.get('w') })
    })
    inlogVenster.on('closed', () => { inlogVenster = null })
  })
}

// ── Hoofdvenster ──
function maakVenster() {
  const werk = screen.getPrimaryDisplay().workAreaSize
  venster = new BrowserWindow({
    width: Math.min(1480, Math.round(werk.width * 0.92)), height: Math.min(940, Math.round(werk.height * 0.92)), center: true, minWidth: 380, backgroundColor: '#06070c', show: !verborgenStart,
    autoHideMenuBar: true, icon: BRON('bouw/icon.png'), title: 'RL Analytics',
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  })
  venster.loadURL(URL_SITE)
  venster.webContents.on('did-finish-load', () => { app.mislukt = 0 })
  venster.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' } })
  venster.on('close', (e) => { if (!app.isQuitting) { e.preventDefault(); venster.hide() } })
}

app.on('login', async (e, _wc, _details, _auth, terug) => {
  e.preventDefault()
  let g = app.mislukt ? null : gegevens()
  app.mislukt = (app.mislukt || 0) + 1
  if (!g || app.mislukt > 2) g = await vraagGegevens()
  terug(g.gebruiker, g.wachtwoord)
})

function toon(pad = '') {
  if (!venster) maakVenster()
  if (pad) venster.loadURL(URL_SITE + pad)
  venster.show(); venster.focus()
}

// ── Systeemvak ──
function bouwTrayMenu() {
  const c = leesJson(CONFIG, {})
  const autostart = app.getLoginItemSettings({ args: ['--verborgen'] }).openAtLogin
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'RL Analytics openen', click: () => toon() },
    { label: 'Mijn profiel', click: () => toon('/?view=spelers') },
    { label: 'Laatste wedstrijd', enabled: !!c.laatste, click: () => toon(`/?replay=${c.laatste}`) },
    { type: 'separator' },
    { label: `Replays doorsturen: ${c.doorsturen === false ? 'uit' : 'aan'}`, click: () => { schrijfJson(CONFIG, { ...c, doorsturen: c.doorsturen === false }); bouwTrayMenu() } },
    { label: 'Starten met Windows', type: 'checkbox', checked: autostart,
      click: (m) => { app.setLoginItemSettings({ openAtLogin: m.checked, args: ['--verborgen'] }); bouwTrayMenu() } },
    { label: 'Logboek openen', click: () => shell.openPath(LOG) },
    { type: 'separator' },
    { label: 'Afsluiten', click: () => { app.isQuitting = true; app.quit() } },
  ]))
  tray.setToolTip(`RL Analytics${c.doorsturen === false ? ' (doorsturen uit)' : ' — replays worden doorgestuurd'}`)
}

// ── Replays doorsturen ──
const run = (exe, args) => new Promise((ok) => execFile(path.join(SSH_MAP, exe), args, { windowsHide: true, timeout: 120000 }, (err, so, se) => ok({ ok: !err, uit: (se || so || '').toString().trim() })))
const SSH_OPTIES = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=20', '-o', 'KexAlgorithms=curve25519-sha256,curve25519-sha256@libssh.org']
let bezig = false

async function scan() {
  if (bezig || leesJson(CONFIG, {}).doorsturen === false) return
  bezig = true
  try {
    const gezien = new Set(leesJson(GEZIEN, null) ?? [])
    const eersteKeer = !fs.existsSync(GEZIEN)
    for (const map of REPLAYMAPPEN) {
      if (!fs.existsSync(map)) continue
      for (const naam of fs.readdirSync(map).filter((n) => n.endsWith('.replay'))) {
        if (gezien.has(naam)) continue
        if (eersteKeer) { gezien.add(naam); continue } // bestaande replays zijn al geïmporteerd
        const pad = path.join(map, naam)
        const g1 = fs.statSync(pad).size
        await new Promise((r) => setTimeout(r, 3000))
        if (fs.statSync(pad).size !== g1) continue // RL schrijft nog
        const doel = `${INBOX}/${naam}`
        const up = await run('scp.exe', ['-q', ...SSH_OPTIES, pad, `${SERVER}:${doel}.part`])
        if (!up.ok) { log(`upload mislukt ${naam}: ${up.uit}`); continue }
        await run('ssh.exe', [...SSH_OPTIES, SERVER, `mv ${doel}.part ${doel}`])
        gezien.add(naam)
        log(`doorgestuurd: ${naam}`)
        wachtOpVerwerking(naam.replace(/\.replay$/, ''))
      }
    }
    schrijfJson(GEZIEN, [...gezien])
  } catch (e) { log(`scan-fout: ${e.message}`) } finally { bezig = false }
}

// Na upload: server-index bekijken tot de wedstrijd verwerkt is, dan melding
async function wachtOpVerwerking(stem) {
  const g = gegevens(); if (!g) return
  const kop = { Authorization: 'Basic ' + Buffer.from(`${g.gebruiker}:${g.wachtwoord}`).toString('base64') }
  for (let i = 0; i < 30; i++) {
    await new Promise((r) => setTimeout(r, 10000))
    try {
      const index = await (await fetch(`${URL_SITE}/verwerkt/index.json`, { headers: kop, cache: 'no-store' })).json()
      const w = index.find((x) => x.naam === stem)
      if (!w) continue
      const c = leesJson(CONFIG, {}); schrijfJson(CONFIG, { ...c, laatste: stem }); bouwTrayMenu()
      if (!w.eigen) return log(`verwerkt maar niet als eigen wedstrijd: ${stem}`)
      const uitslag = w.uitslag === 'W' ? 'Gewonnen' : 'Verloren'
      const melding = new Notification({ title: `${uitslag} ${w.score[0]}–${w.score[1]}`, body: `${w.categorie === 'mee' ? 'Toegevoegd aan je profiel' : 'Opgeslagen (telt niet mee voor je profiel)'} · klik om te bekijken`, icon: BRON('bouw/icon.png') })
      melding.on('click', () => toon(`/?replay=${stem}`))
      melding.show()
      return log(`verwerkt: ${stem} (${w.uitslag})`)
    } catch (e) { log(`index ophalen mislukt: ${e.message}`) }
  }
  log(`niet (tijdig) verwerkt: ${stem}`)
}

// ── Opstarten ──
if (!app.requestSingleInstanceLock()) app.quit()
else {
  app.on('second-instance', () => toon())
  app.setAppUserModelId('nl.rlanalytics.desktop')
  app.whenReady().then(() => {
    // Eerste start: automatisch mee laten starten met Windows (uit te zetten via het systeemvak)
    const c = leesJson(CONFIG, {})
    if (!c.autostartIngesteld) { app.setLoginItemSettings({ openAtLogin: true, args: ['--verborgen'] }); schrijfJson(CONFIG, { ...c, autostartIngesteld: true }) }
    tray = new Tray(nativeImage.createFromPath(BRON('bouw/tray.png')).resize({ width: 16, height: 16 }))
    tray.on('click', () => toon())
    bouwTrayMenu()
    maakVenster()
    scan(); setInterval(scan, 15000)
    log(`gestart${verborgenStart ? ' (verborgen)' : ''}`)
  })
  app.on('window-all-closed', (e) => e.preventDefault())
}
