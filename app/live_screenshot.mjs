// Screenshot van de live site (met wachtwoord uit ../toegang.txt)
import { chromium } from 'playwright-core'
import fs from 'node:fs'
const t = fs.readFileSync('../toegang.txt', 'utf8')
const ww = t.match(/Wachtwoord: (.+)/)[1].trim(), gebruiker = t.match(/Gebruiker: (.+)/)[1].trim()
const [uit, query = '', w = '1600', h = '1000', wacht = '.replay'] = process.argv.slice(2)
const browser = await chromium.launch({ channel: 'msedge' })
const ctx = await browser.newContext({ viewport: { width: +w, height: +h }, httpCredentials: { username: gebruiker, password: ww }, isMobile: +w < 600, deviceScaleFactor: +w < 600 ? 2 : 1 })
const page = await ctx.newPage()
await page.goto(`https://rl.51-75-74-94.sslip.io/?${query}`)
await page.waitForSelector(wacht, { state: 'attached', timeout: 30000 })
await page.waitForTimeout(2500)
await page.screenshot({ path: uit })
await browser.close()
