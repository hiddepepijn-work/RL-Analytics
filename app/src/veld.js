import * as THREE from 'three'

// Arena-maten in Unreal units (uu ≈ cm). Three-assen: x = rl.x, y = rl.z (hoogte), z = rl.y (lengte).
export const VELD = { breedte: 4096, lengte: 5120, hoogte: 2044, hoek: 1152, doelBreedte: 893, doelHoogte: 642.775, doelDiepte: 880 }
export const BAL_STRAAL = 91.25
export const KLEUR = { blauw: 0x3d8bff, oranje: 0xe06a12 }

const GROTE_PADS = [[-3584, 0], [3584, 0], [-3072, 4096], [3072, 4096], [-3072, -4096], [3072, -4096]]

function omtrek() {
  const { breedte: b, lengte: l, hoek: h } = VELD
  return [[-b + h, -l], [b - h, -l], [b, -l + h], [b, l - h], [b - h, l], [-b + h, l], [-b, l - h], [-b, -l + h]]
}

function lijnen(punten, kleur, opacity = 1) {
  const g = new THREE.BufferGeometry().setFromPoints(punten.map(([x, y, z]) => new THREE.Vector3(x, y, z)))
  return new THREE.Line(g, new THREE.LineBasicMaterial({ color: kleur, transparent: opacity < 1, opacity }))
}

function doel(scene, kant, kleur) {
  const { doelBreedte: w, doelHoogte: h, doelDiepte: d, lengte: l } = VELD
  const z0 = kant * l, z1 = kant * (l + d)
  const groep = new THREE.Group()
  const rand = [[-w, 0, z0], [-w, h, z0], [w, h, z0], [w, 0, z0]]
  groep.add(lijnen(rand, kleur))
  groep.add(lijnen([[-w, 0, z1], [-w, h, z1], [w, h, z1], [w, 0, z1], [-w, 0, z1]], kleur, 0.5))
  for (const [x, y] of [[-w, 0], [-w, h], [w, h], [w, 0]]) groep.add(lijnen([[x, y, z0], [x, y, z1]], kleur, 0.5))
  // Doelvlak als zachte gloed
  const vlak = new THREE.Mesh(new THREE.PlaneGeometry(2 * w, h),
    new THREE.MeshBasicMaterial({ color: kleur, transparent: true, opacity: 0.08, side: THREE.DoubleSide, depthWrite: false }))
  vlak.position.set(0, h / 2, z0)
  groep.add(vlak)
  scene.add(groep)
}

export function maakVeld(scene) {
  const punten = omtrek()

  // Vloer
  const vorm = new THREE.Shape(punten.map(([x, y]) => new THREE.Vector2(x, y)))
  const vloer = new THREE.Mesh(new THREE.ShapeGeometry(vorm), new THREE.MeshStandardMaterial({ color: 0x0f1620, roughness: 0.95 }))
  vloer.rotation.x = Math.PI / 2 // shape-y → three-z
  vloer.material.side = THREE.DoubleSide
  scene.add(vloer)

  // Helften licht ingekleurd
  for (const [kant, kleur] of [[-1, KLEUR.blauw], [1, KLEUR.oranje]]) {
    const helft = new THREE.Mesh(new THREE.PlaneGeometry(2 * VELD.breedte - 40, VELD.lengte - 40),
      new THREE.MeshBasicMaterial({ color: kleur, transparent: true, opacity: 0.035, depthWrite: false }))
    helft.rotation.x = -Math.PI / 2
    helft.position.set(0, 1, kant * VELD.lengte / 2)
    scene.add(helft)
  }

  // Raster op de vloer (per 512 uu)
  const raster = new THREE.GridHelper(10240, 20, 0x1d2735, 0x16202c)
  raster.position.y = 0.5
  scene.add(raster)

  // Belijning
  const wit = 0x9fb1c9
  scene.add(lijnen([[-VELD.breedte, 2, 0], [VELD.breedte, 2, 0]], wit, 0.45))
  const cirkel = []
  for (let i = 0; i <= 64; i++) { const a = (i / 64) * Math.PI * 2; cirkel.push([Math.cos(a) * 1000, 2, Math.sin(a) * 1000]) }
  scene.add(lijnen(cirkel, wit, 0.45))
  for (const kant of [-1, 1]) {
    const z0 = kant * VELD.lengte, z1 = kant * (VELD.lengte - 1200)
    scene.add(lijnen([[-1800, 2, z0], [-1800, 2, z1], [1800, 2, z1], [1800, 2, z0]], wit, 0.3))
  }

  // Omtrek: vloerrand, plafondrand, staanders
  const rondom = [...punten, punten[0]]
  scene.add(lijnen(rondom.map(([x, z]) => [x, 2, z]), 0x3a4a60))
  scene.add(lijnen(rondom.map(([x, z]) => [x, VELD.hoogte, z]), 0x243040, 0.6))
  for (const [x, z] of punten) scene.add(lijnen([[x, 0, z], [x, VELD.hoogte, z]], 0x243040, 0.5))

  // Wanden: zeer transparant zodat de diepte leesbaar blijft
  const wandMat = new THREE.MeshBasicMaterial({ color: 0x5b7aa6, transparent: true, opacity: 0.035, side: THREE.DoubleSide, depthWrite: false })
  for (let i = 0; i < punten.length; i++) {
    const [x0, z0] = punten[i], [x1, z1] = punten[(i + 1) % punten.length]
    const len = Math.hypot(x1 - x0, z1 - z0)
    const wand = new THREE.Mesh(new THREE.PlaneGeometry(len, VELD.hoogte), wandMat)
    wand.position.set((x0 + x1) / 2, VELD.hoogte / 2, (z0 + z1) / 2)
    wand.rotation.y = -Math.atan2(z1 - z0, x1 - x0)
    scene.add(wand)
  }

  doel(scene, -1, KLEUR.blauw)
  doel(scene, 1, KLEUR.oranje)

  // Grote boostpads
  const padMat = new THREE.MeshBasicMaterial({ color: 0xffc23d, transparent: true, opacity: 0.55 })
  for (const [x, y] of GROTE_PADS) {
    const pad = new THREE.Mesh(new THREE.CylinderGeometry(160, 160, 6, 32), padMat)
    pad.position.set(x, 3, y)
    scene.add(pad)
  }
}
