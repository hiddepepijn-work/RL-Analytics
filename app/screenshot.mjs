// Gebruik: node screenshot.mjs <uitvoer.png> "<query>" [breedte] [hoogte]
import { chromium } from 'playwright-core'
const [uit, query = '', w = '1600', h = '1000'] = process.argv.slice(2)
const browser = await chromium.launch({ channel: 'msedge', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
const page = await browser.newPage({ viewport: { width: +w, height: +h }, deviceScaleFactor: 1 })
const fouten = []
page.on('pageerror', (e) => fouten.push(e.message))
page.on('console', (m) => m.type() === 'error' && fouten.push(m.text()))
await page.goto(`http://localhost:${process.env.POORT ?? 8799}/?${query}`)
await page.waitForSelector(process.env.WACHT ?? '.speler', { timeout: 20000, state: 'attached' })
await page.waitForTimeout(2500)
const sel = process.env.SEL
  ? await page.locator(process.env.SEL).screenshot({ path: uit })
  : await page.screenshot({ path: uit, fullPage: true })
if (fouten.length) console.log('FOUTEN:\n' + fouten.join('\n'))
await browser.close()
