import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js'
import { maakVeld, BAL_STRAAL, KLEUR } from './veld.js'

// Hitbox-maten (lengte, breedte, hoogte) in uu
const HITBOX = {
  Octane: [118.0, 84.2, 36.2], Dominus: [127.9, 83.3, 31.3], Plank: [128.8, 84.7, 29.4],
  Breakout: [131.5, 80.5, 30.3], Hybrid: [127.0, 82.2, 34.2], Merc: [120.7, 76.7, 41.7],
}
const BAL_STRIDE = 7, SPELER_STRIDE = 9
const SPOOR_SECONDEN = 1.6
// Visuele vergroting: op ware grootte zijn auto's in het overzicht maar een paar pixels
const AUTO_SCHAAL = 1.7, BAL_SCHAAL = 1.5

// Replay-assen → three-assen (spiegeling y↔z, dus quaternion mee spiegelen)
// Echte objecten staan nooit op z = 0 (auto in rust 17, bal 92)
export const afwezig = (a, i) => a[i] === 0 && a[i + 1] === 0 && a[i + 2] === 0
const naarPos = (v, a, i) => v.set(a[i], a[i + 2], a[i + 1])
const naarQuat = (q, a, i) => q.set(-a[i], -a[i + 2], -a[i + 1], a[i + 3])

function achtergrond() {
  const c = document.createElement('canvas'); c.width = 512; c.height = 256
  const g = c.getContext('2d'), r = g.createRadialGradient(256, 90, 10, 256, 128, 330)
  r.addColorStop(0, '#142033'); r.addColorStop(1, '#070a0f')
  g.fillStyle = r; g.fillRect(0, 0, 512, 256)
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

export class Viewer {
  constructor(el) {
    this.el = el
    // Ondoorzichtig canvas: browser hoeft het 3D-beeld niet elk frame met de pagina te mengen
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' })
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5))
    el.appendChild(this.renderer.domElement)

    this.labels = new CSS2DRenderer()
    Object.assign(this.labels.domElement.style, { position: 'absolute', inset: '0', pointerEvents: 'none' })
    el.appendChild(this.labels.domElement)

    this.scene = new THREE.Scene()
    this.scene.fog = new THREE.Fog(0x070a0f, 9000, 22000)
    this.scene.background = achtergrond()
    this.scene.add(new THREE.HemisphereLight(0xcfe0ff, 0x0b0f16, 1.1))
    const zon = new THREE.DirectionalLight(0xffffff, 1.4)
    zon.position.set(2000, 6000, 1500)
    this.scene.add(zon)
    maakVeld(this.scene)

    this.camera = new THREE.PerspectiveCamera(42, 1, 10, 40000)
    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.maxPolarAngle = Math.PI * 0.495
    this.zetCamera('zij')

    // Bal + spoor
    this.bal = new THREE.Mesh(new THREE.SphereGeometry(BAL_STRAAL, 32, 16),
      new THREE.MeshStandardMaterial({ color: 0xf2f4f8, emissive: 0x334155, roughness: 0.35 }))
    this.bal.scale.setScalar(BAL_SCHAAL)
    this.scene.add(this.bal)
    this.balSchaduw = new THREE.Mesh(new THREE.CircleGeometry(BAL_STRAAL * BAL_SCHAAL, 32),
      new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.35, depthWrite: false }))
    this.balSchaduw.rotation.x = -Math.PI / 2
    this.scene.add(this.balSchaduw)
    this.spoorMax = 64
    this.spoorGeo = new THREE.BufferGeometry()
    this.spoorGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(this.spoorMax * 3), 3))
    this.spoorGeo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(this.spoorMax * 3), 3))
    this.scene.add(new THREE.Line(this.spoorGeo, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.9 })))

    this.autos = []
    this.cameraModus = 'zij'
    this._p = new THREE.Vector3(); this._p2 = new THREE.Vector3()
    this._q = new THREE.Quaternion(); this._q2 = new THREE.Quaternion()

    new ResizeObserver(() => this.pasGrootteAan()).observe(el)
    this.pasGrootteAan()
  }

  // Alleen tekenen als er iets veranderd is (tijd, camera, grootte); stilstaand beeld kost dan niets
  markeer() { this.vuil = true }

  pasGrootteAan() {
    this.vuil = true
    const { clientWidth: w, clientHeight: h } = this.el
    if (!w || !h) return
    this.renderer.setSize(w, h)
    this.labels.setSize(w, h)
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    // Smal scherm (telefoon): camera verder weg zodat het hele veld in beeld blijft
    const factor = Math.min(2.4, Math.max(1, 1.9 / this.camera.aspect))
    if (factor !== this.afstandFactor) {
      this.afstandFactor = factor
      if (this.cameraModus === 'zij' || this.cameraModus === 'boven') this.zetCamera(this.cameraModus)
    }
  }

  zetCamera(modus) {
    this.vuil = true
    this.cameraModus = modus
    this.controls.enabled = modus !== 'bal'
    const f = this.afstandFactor ?? 1
    if (modus === 'zij') { this.camera.position.set(-8200 * f, 4300 * f, 0); this.controls.target.set(0, 0, 0) }
    if (modus === 'boven') { this.camera.position.set(-1, 11000 * f, 0); this.controls.target.set(0, 0, 0) }
    this.controls.update()
  }

  laad(data) {
    this.data = data
    this._laatsteT = null
    this.vuil = true
    for (const a of this.autos) { this.scene.remove(a.mesh, a.label, a.schijf); a.label.element.remove() }
    this.autos = data.spelers.map((s) => {
      const [l, b, h] = HITBOX[s.auto] ?? HITBOX.Octane
      const kleur = s.team === 0 ? KLEUR.blauw : KLEUR.oranje
      const mesh = new THREE.Group()
      const romp = new THREE.Mesh(new THREE.BoxGeometry(l, h, b),
        new THREE.MeshStandardMaterial({ color: kleur, emissive: kleur, emissiveIntensity: 0.25, roughness: 0.5 }))
      // Neus-markering zodat rijrichting zichtbaar is
      const neus = new THREE.Mesh(new THREE.BoxGeometry(14, h + 2, b * 0.7), new THREE.MeshBasicMaterial({ color: 0xffffff }))
      neus.position.x = l / 2 - 7
      mesh.add(romp, neus)
      mesh.scale.setScalar(AUTO_SCHAAL)
      // Teamschijf op de vloer: leesbaar in bovenaanzicht en bij luchtacties (projectie)
      const schijf = new THREE.Mesh(new THREE.RingGeometry(150, 200, 40),
        new THREE.MeshBasicMaterial({ color: kleur, transparent: true, opacity: 0.55, depthWrite: false, side: THREE.DoubleSide }))
      schijf.rotation.x = -Math.PI / 2
      this.scene.add(schijf)
      const div = document.createElement('div')
      div.className = 'label3d'
      div.style.borderColor = s.team === 0 ? '#3d8bff' : '#e06a12'
      div.innerHTML = `${s.naam}<span class="boost"><i></i></span>`
      const label = new CSS2DObject(div)
      label.center.set(0.5, 1)
      this.scene.add(mesh, label)
      return { mesh, label, schijf, boostEl: div.querySelector('i') }
    })
  }

  // Frame-index + fractie voor tijd t (binair zoeken in data.t)
  zoek(t) {
    const ts = this.data.t
    let lo = 0, hi = ts.length - 1
    if (t <= ts[0]) return [0, 0]
    if (t >= ts[hi]) return [hi, 0]
    while (hi - lo > 1) { const m = (lo + hi) >> 1; ts[m] <= t ? (lo = m) : (hi = m) }
    return [lo, (t - ts[lo]) / (ts[hi] - ts[lo] || 1)]
  }

  toon(t) {
    if (!this.data || (t === this._laatsteT && this.cameraModus !== 'bal')) return
    this._laatsteT = t
    this.vuil = true
    const [i, f] = this.zoek(t)
    const j = Math.min(i + 1, this.data.t.length - 1)
    const b = this.data.bal

    naarPos(this._p, b, i * BAL_STRIDE); naarPos(this._p2, b, j * BAL_STRIDE)
    this.bal.position.lerpVectors(this._p, this._p2, f)
    naarQuat(this._q, b, i * BAL_STRIDE + 3); naarQuat(this._q2, b, j * BAL_STRIDE + 3)
    this.bal.quaternion.slerpQuaternions(this._q, this._q2, f)
    this.balSchaduw.position.set(this.bal.position.x, 1.5, this.bal.position.z)
    this.bal.visible = this.balSchaduw.visible = !afwezig(b, i * BAL_STRIDE)

    this.data.spelers.forEach((s, k) => {
      const a = this.autos[k], fr = s.frames
      naarPos(this._p, fr, i * SPELER_STRIDE); naarPos(this._p2, fr, j * SPELER_STRIDE)
      a.mesh.position.lerpVectors(this._p, this._p2, f)
      naarQuat(this._q, fr, i * SPELER_STRIDE + 3); naarQuat(this._q2, fr, j * SPELER_STRIDE + 3)
      a.mesh.quaternion.slerpQuaternions(this._q, this._q2, f)
      a.boostEl.style.width = fr[i * SPELER_STRIDE + 7] + '%'
      a.label.position.set(a.mesh.position.x, a.mesh.position.y + 160, a.mesh.position.z)
      a.schijf.position.set(a.mesh.position.x, 2, a.mesh.position.z)
      // Gedemoleerd (kolom ≥ 0) of afwezig (parser vult (0,0,0) in, bv. tijdens goal-reset) → verbergen
      const weg = fr[i * SPELER_STRIDE + 8] >= 0 || afwezig(fr, i * SPELER_STRIDE)
      a.mesh.visible = a.label.visible = a.schijf.visible = !weg
    })

    this.werkSpoorBij(i)
    if (this.cameraModus === 'bal') {
      const doelZ = this.bal.position.z > 0 ? -1 : 1
      this._p.set(this.bal.position.x * 0.6, Math.max(this.bal.position.y + 900, 1100), this.bal.position.z + doelZ * 2600)
      this.camera.position.lerp(this._p, 0.12)
      this.controls.target.lerp(this.bal.position, 0.25)
    }
  }

  werkSpoorBij(i) {
    const stap = Math.max(1, Math.round((SPOOR_SECONDEN * this.data.fps) / this.spoorMax))
    const pos = this.spoorGeo.attributes.position.array, kl = this.spoorGeo.attributes.color.array
    for (let n = 0; n < this.spoorMax; n++) {
      const idx = Math.max(0, i - (this.spoorMax - 1 - n) * stap) * BAL_STRIDE
      pos[n * 3] = this.data.bal[idx]; pos[n * 3 + 1] = this.data.bal[idx + 2]; pos[n * 3 + 2] = this.data.bal[idx + 1]
      const w = (n / this.spoorMax) ** 1.5
      kl[n * 3] = w; kl[n * 3 + 1] = w * 0.95; kl[n * 3 + 2] = w * 0.8
    }
    this.spoorGeo.attributes.position.needsUpdate = true
    this.spoorGeo.attributes.color.needsUpdate = true
  }

  render() {
    let veranderd = this.vuil
    if (this.cameraModus !== 'bal') veranderd = this.controls.update() || veranderd
    else { this.camera.lookAt(this.controls.target); veranderd = true }
    if (!veranderd) return
    this.vuil = false
    this.renderer.render(this.scene, this.camera)
    this.labels.render(this.scene, this.camera)
  }
}
