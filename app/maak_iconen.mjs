// Rendert public/icoon.svg naar PNG's (192/512) voor de installeerbare app.
import { chromium } from 'playwright-core'
import fs from 'node:fs'
const svg = fs.readFileSync('public/icoon.svg', 'utf8')
const browser = await chromium.launch({ channel: 'msedge' })
for (const n of [192, 512]) {
  const page = await browser.newPage({ viewport: { width: n, height: n } })
  await page.setContent(`<html><body style="margin:0;background:transparent">${svg.replace('<svg ', `<svg width="${n}" height="${n}" `)}</body></html>`)
  await page.screenshot({ path: `public/icoon-${n}.png`, omitBackground: true })
  await page.close()
}
await browser.close()
