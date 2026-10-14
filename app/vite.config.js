import { defineConfig } from 'vite'
import fs from 'node:fs'
import path from 'node:path'

const DATA = path.resolve(__dirname, '../data')
const MAPPEN = { '/verwerkt': path.join(DATA, 'verwerkt'), '/modellen': path.join(DATA, 'modellen') }
const TYPES = { '.json': 'application/json', '.jsonl': 'text/plain; charset=utf-8' }

// Serveert parser-uitvoer en modelrapporten, zodat data buiten de app-map blijft.
const dataBron = {
  name: 'data-bron',
  configureServer(server) { koppel(server) },
  configurePreviewServer(server) { koppel(server) },
}

function koppel(server) {
  for (const [route, map] of Object.entries(MAPPEN)) {
    server.middlewares.use(route, (req, res, next) => {
      const bestand = path.join(map, decodeURIComponent(req.url.split('?')[0]))
      if (!bestand.startsWith(map) || !fs.existsSync(bestand) || fs.statSync(bestand).isDirectory()) return next()
      res.setHeader('Content-Type', TYPES[path.extname(bestand)] ?? 'application/octet-stream')
      res.setHeader('Cache-Control', 'no-store')
      fs.createReadStream(bestand).pipe(res)
    })
  }
}

export default defineConfig({
  plugins: [dataBron],
  server: { port: 8799, strictPort: true },
  preview: { port: 8800, strictPort: true },
})
