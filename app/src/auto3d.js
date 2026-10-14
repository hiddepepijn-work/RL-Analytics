import * as THREE from 'three'
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js'

// Octane-achtige auto uit een paar primitieven: romp + cabine (zijprofiel geëxtrudeerd), wielen, lampen, boostvlam.
// Ontworpen in uu van een echte Octane, y vanaf de grond, x vanaf het draaipunt (hitbox ligt 14 uu naar voren).
// Lokale assen = replay-assen na omzetting: +x rijrichting, +y dak, z zijkant.
const REF = { l: 118, b: 84.2, h: 36.2 }
const DRAAIPUNT_HOOGTE = 17 // auto in rust staat met zijn draaipunt 17 uu boven de vloer

const ROMP = [[-45, 12], [64, 12], [74, 18], [75, 25], [58, 31], [24, 37], [-30, 41], [-43, 45], [-47, 37], [-46, 18]]
const CABINE = [[-32, 39], [20, 36], [2, 51], [-20, 53], [-31, 47]]
// [x, straal, z-afstand] per as: Octane heeft grotere achterwielen
const ASSEN = [[51, 13, 33], [-34, 15, 35]]

function extrudeer(punten, breedte, rand) {
  const vorm = new THREE.Shape(punten.map(([x, y]) => new THREE.Vector2(x, y)))
  const diepte = breedte - 2 * rand
  const g = new THREE.ExtrudeGeometry(vorm, {
    depth: diepte, curveSegments: 1, bevelEnabled: true,
    bevelThickness: rand, bevelSize: rand, bevelOffset: -rand, bevelSegments: 2,
  })
  g.translate(0, 0, -diepte / 2)
  return g
}

function wiel(x, r, z, breedte) {
  const g = new THREE.CylinderGeometry(r, r, breedte, 14)
  g.rotateX(Math.PI / 2)
  g.translate(x, r, z)
  return g
}

let geoCache = null
function geometrie() {
  if (geoCache) return geoCache
  const banden = [], velgen = []
  for (const [x, r, z] of ASSEN) for (const kant of [-1, 1]) {
    banden.push(wiel(x, r, kant * z, 13))
    velgen.push(wiel(x, r * 0.62, kant * (z + 6.8), 1))
  }
  // Donkere onderrand: geeft de romp een tweekleurige, lage lijn
  const rand = new THREE.BoxGeometry(112, 6, 72); rand.translate(13, 13, 0)
  const lamp = (x, y, z, l, h, b) => { const g = new THREE.BoxGeometry(l, h, b); g.translate(x, y, z); return g }
  geoCache = {
    romp: extrudeer(ROMP, 70, 5),
    cabine: extrudeer(CABINE, 52, 4),
    donker: mergeGeometries([...banden.map((g) => g.toNonIndexed()), rand.toNonIndexed()]),
    velgen: mergeGeometries(velgen),
    koplampen: mergeGeometries([lamp(74.5, 21.5, -21, 2, 4, 13), lamp(74.5, 21.5, 21, 2, 4, 13)]),
    achterlichten: mergeGeometries([lamp(-46.5, 32, -24, 2, 4, 14), lamp(-46.5, 32, 24, 2, 4, 14)]),
    // Kegel met de punt naar achteren (-x), basis op x = 0
    vlam: new THREE.ConeGeometry(1, 1, 12, 1, true).rotateZ(Math.PI / 2).translate(-0.5, 0, 0),
  }
  return geoCache
}

const matCache = new Map()
function materialen(kleur) {
  if (matCache.has(kleur)) return matCache.get(kleur)
  const c = new THREE.Color(kleur)
  const m = {
    // Lichte eigen gloed zodat de teamkleur in de donkere arena leesbaar blijft, zonder neon
    romp: new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: 0.14, roughness: 0.42, metalness: 0.25 }),
    cabine: new THREE.MeshStandardMaterial({ color: 0x0d131c, roughness: 0.18, metalness: 0.6 }),
    donker: new THREE.MeshStandardMaterial({ color: 0x14171c, roughness: 0.85 }),
    velgen: new THREE.MeshStandardMaterial({ color: 0x9aa4b2, roughness: 0.4, metalness: 0.7 }),
    koplampen: new THREE.MeshBasicMaterial({ color: 0xe9eef6 }),
    achterlichten: new THREE.MeshBasicMaterial({ color: 0x8a2a2a }),
    vlamBuiten: new THREE.MeshBasicMaterial({ color: kleur === 0x3d8bff ? 0x6fa8ff : 0xff9a45, transparent: true, opacity: 0.55, depthWrite: false }),
    vlamBinnen: new THREE.MeshBasicMaterial({ color: 0xfff1d6, transparent: true, opacity: 0.85, depthWrite: false }),
  }
  matCache.set(kleur, m)
  return m
}

// Groep met draaipunt in de oorsprong. `schaal` = visuele vergroting; het model wordt zo opgetild dat de
// wielen na vergroting precies de vloer raken (anders zakt een vergrote auto erdoorheen).
export function maakAuto(hitbox, kleur, schaal) {
  const [l, b, h] = hitbox
  const g = geometrie(), m = materialen(kleur)
  const groep = new THREE.Group()
  const model = new THREE.Group()
  for (const naam of ['romp', 'cabine', 'donker', 'velgen', 'koplampen', 'achterlichten']) model.add(new THREE.Mesh(g[naam], m[naam]))
  model.scale.set(l / REF.l, h / REF.h, b / REF.b)
  model.position.y = -DRAAIPUNT_HOOGTE / schaal
  const vlam = new THREE.Group()
  const buiten = new THREE.Mesh(g.vlam, m.vlamBuiten); buiten.scale.set(46, 10, 10)
  const binnen = new THREE.Mesh(g.vlam, m.vlamBinnen); binnen.scale.set(26, 5.5, 5.5)
  vlam.add(buiten, binnen)
  vlam.position.set(-47, 28, 0)
  vlam.visible = false
  model.add(vlam)
  groep.add(model)
  groep.scale.setScalar(schaal)
  return { groep, vlam }
}

// Zachte ronde schaduwvlek (radiaal verloop), gedeeld door bal en auto's
let schaduwTex = null
export function schaduwTextuur() {
  if (schaduwTex) return schaduwTex
  const c = document.createElement('canvas'); c.width = c.height = 64
  const g = c.getContext('2d'), r = g.createRadialGradient(32, 32, 0, 32, 32, 32)
  r.addColorStop(0, 'rgba(0,0,0,1)'); r.addColorStop(0.45, 'rgba(0,0,0,0.75)'); r.addColorStop(1, 'rgba(0,0,0,0)')
  g.fillStyle = r; g.fillRect(0, 0, 64, 64)
  schaduwTex = new THREE.CanvasTexture(c)
  return schaduwTex
}

export function maakSchaduw(breedte, lengte) {
  const geo = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2)
  const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ map: schaduwTextuur(), transparent: true, opacity: 0.5, depthWrite: false }))
  mesh.scale.set(lengte, 1, breedte)
  mesh.renderOrder = 1
  return mesh
}

// Baltextuur: lichte bal met zachte zeshoeknaden, zodat je de spin ziet
export function balTextuur() {
  const c = document.createElement('canvas'); c.width = 512; c.height = 256
  const g = c.getContext('2d')
  g.fillStyle = '#e9edf3'; g.fillRect(0, 0, 512, 256)
  g.strokeStyle = 'rgba(92,108,130,0.55)'; g.lineWidth = 3
  const r = 26, dx = r * Math.sqrt(3), dy = r * 1.5
  for (let rij = -1; rij * dy < 256 + r; rij++) for (let kol = -1; kol * dx < 512 + dx; kol++) {
    const cx = kol * dx + (rij % 2 ? dx / 2 : 0), cy = rij * dy
    g.beginPath()
    for (let k = 0; k <= 6; k++) { const a = Math.PI / 6 + (k * Math.PI) / 3; g.lineTo(cx + r * Math.cos(a), cy + r * Math.sin(a)) }
    g.stroke()
  }
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 4
  return tex
}
