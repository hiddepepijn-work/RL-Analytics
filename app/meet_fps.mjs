import { chromium } from 'playwright-core'
const browser = await chromium.launch({ channel: 'msedge', args: ['--use-angle=d3d11', '--enable-gpu', '--ignore-gpu-blocklist'] })
const gpu = await (await browser.newPage()).evaluate(() => { const g = document.createElement('canvas').getContext('webgl2'); const e = g.getExtension('WEBGL_debug_renderer_info'); return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'onbekend' }); console.log('GPU:', gpu)
for (const [naam, q] of [['arena', 'thema=arena'], ['carbon', 'thema=carbon'], ['arena, ander tabblad', 'thema=arena&tab=teamstats']]) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
  await page.goto(`http://localhost:8799/?replay=EquippedTitleStatValue&speel=1&${q}`)
  await page.waitForSelector('.speler', { state: 'attached' }); await page.waitForTimeout(1500)
  const fps = await page.evaluate(() => new Promise((ok) => { let n = 0; const t0 = performance.now(); const s = () => { n++; performance.now() - t0 < 3000 ? requestAnimationFrame(s) : ok(n / 3) }; requestAnimationFrame(s) }))
  console.log(naam.padEnd(22), 'fps', fps.toFixed(1))
  await page.close()
}
await browser.close()
