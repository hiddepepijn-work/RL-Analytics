import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js'
import { maakVeld, BAL_STRAAL, KLEUR } from './veld.js'
import { maakAuto, maakSchaduw, balTextuur } from './auto3d.js'
import { VolgCamera } from './volgcamera.js'

// Hitbox-maten (lengte, breedte, hoogte) in uu
const HITBOX = {
  Octane: [118.0, 84.2, 36.2], Dominus: [127.9, 83.3, 31.3], Plank: [128.8, 84.7, 29.4],
  Breakout: [131.5, 80.5, 30.3], Hybrid: [127.0, 82.2, 34.2], Merc: [120.7, 76.7, 41.7],
}
const BAL_STRIDE = 7, SPELER_STRIDE = 9
const SPOOR_SECONDEN = 1.6
// Visuele vergroting: op ware grootte zijn auto's in het overzicht maar een paar pixels
const AUTO_SCHAAL = 1.7, BAL_SCHAAL = 1.5
// Max. verplaatsing per frame (30 fps); verder = teleport (kickoff, respawn) → niet interpoleren
const SPRONG_BAL = 450, SPRONG_AUTO = 250
const VOLG = new Set(['bal', 'auto'])

// Replay-assen → three-assen (spiegeling y↔z, dus quaternion mee spiegelen)
// Echte objecten staan nooit op z = 0 (auto in rust 17, bal 92)
export const afwezig = (a, i) => a[i] === 0 && a[i + 1] === 0 && a[i + 2] === 0
const naarPos = (v, a, i) => v.set(a[i], a[i + 2], a[i + 1])
const naarQuat = (q, a, i) => q.set(-a[i], -a[i + 2], -a[i + 1], a[i + 3])

// Vergrote bal zou half in de vloer zakken; vlak bij de vloer tillen we hem geleidelijk op (monotoon, dus stuiters blijven kloppen)
const BAL_TIL = (BAL_SCHAAL - 1) * BAL_STRAAL
const balHoogte = (y) => y + BAL_TIL * Math.max(0, 1 - (y - BAL_STRAAL) / (3 * BAL_STRAAL))

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
    // Hoge-dpi telefoons: 1,5× is scherp genoeg en scheelt de helft aan pixels t.o.v. 3×
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
    this.volg = new VolgCamera()
    this.volgK = 0
    this.autos = []
    this.zetCamera('zij')

    // Bal + zachte schaduw (hoogte lezen) + spoor
    this.bal = new THREE.Mesh(new THREE.SphereGeometry(BAL_STRAAL, 32, 16),
      new THREE.MeshStandardMaterial({ map: balTextuur(), emissive: 0x1e293b, roughness: 0.35 }))
    this.bal.scale.setScalar(BAL_SCHAAL)
    this.scene.add(this.bal)
    this.balSchaduw = maakSchaduw(1, 1)
    this.scene.add(this.balSchaduw)
    this.spoorMax = 64
    this.spoorGeo = new THREE.BufferGeometry()
    this.spoorGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(this.spoorMax * 3), 3))
    this.spoorGeo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(this.spoorMax * 3), 3))
    this.scene.add(new THREE.Line(this.spoorGeo, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.9 })))

    this._p0 = new THREE.Vector3(); this._p1 = new THREE.Vector3(); this._p2 = new THREE.Vector3(); this._p3 = new THREE.Vector3()
    this._q = new THREE.Quaternion(); this._q2 = new THREE.Quaternion()
    this._v = new THREE.Vector3()

    // Tik/klik op een auto (zonder slepen) → die auto volgen in balcam/autocam
    let neer = null
    this.renderer.domElement.addEventListener('pointerdown', (e) => { neer = [e.clientX, e.clientY] })
    this.renderer.domElement.addEventListener('pointerup', (e) => {
      if (neer && Math.hypot(e.clientX - neer[0], e.clientY - neer[1]) < 6) this.kiesOpScherm(e)
      neer = null
    })

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
    this.zetFov()
    // Smal scherm (telefoon): camera verder weg zodat het hele veld in beeld blijft
    const factor = Math.min(2.4, Math.max(1, 1.9 / this.camera.aspect))
    if (factor !== this.afstandFactor) {
      this.afstandFactor = factor
      if (!VOLG.has(this.cameraModus)) this.zetCamera(this.cameraModus)
    }
  }

  // Volgcamera breder; op een smal scherm nog wat breder zodat bal en auto allebei in beeld blijven
  zetFov() {
    this.camera.fov = VOLG.has(this.cameraModus) ? (this.camera.aspect < 1.2 ? 72 : 58) : 42
    this.camera.updateProjectionMatrix()
  }

  zetCamera(modus) {
    this.vuil = true
    this.cameraModus = modus
    this.controls.enabled = !VOLG.has(modus)
    this.volg.reset()
    this.zetFov()
    const f = this.afstandFactor ?? 1
    if (modus === 'zij') { this.camera.position.set(-8200 * f, 4300 * f, 0); this.controls.target.set(0, 0, 0) }
    if (modus === 'boven') { this.camera.position.set(-1, 11000 * f, 0); this.controls.target.set(0, 0, 0) }
    if (!VOLG.has(modus)) this.controls.update()
    this.werkVolgBij()
  }

  // Welke auto de volgcamera volgt (index in data.spelers)
  volgSpeler(k) {
    if (!this.data || k < 0 || k >= this.autos.length) return
    this.volgK = k
    this.vuil = true
    this.werkVolgBij()
  }

  // In balcam/autocam: geen naam en teamring op de eigen (gevolgde) auto, ringen van de rest gedempt
  werkVolgBij() {
    const volg = VOLG.has(this.cameraModus)
    this.autos.forEach((a, k) => {
      a.eigen = volg && k === this.volgK
      a.label.visible = !a.weg && !a.eigen
      a.schijf.visible = !a.weg && !a.eigen
      a.schijf.material.opacity = volg ? 0.22 : 0.45
    })
  }

  kiesOpScherm(e) {
    const r = this.renderer.domElement.getBoundingClientRect()
    let beste = -1, min = 40 ** 2
    this.autos.forEach((a, k) => {
      if (!a.groep.visible) return
      const p = this._v.copy(a.groep.position).project(this.camera)
      if (p.z > 1) return
      const dx = ((p.x + 1) / 2) * r.width - (e.clientX - r.left), dy = ((1 - p.y) / 2) * r.height - (e.clientY - r.top)
      if (dx * dx + dy * dy < min) { min = dx * dx + dy * dy; beste = k }
    })
    if (beste >= 0) this.volgSpeler(beste)
  }

  laad(data) {
    this.data = data
    this._laatsteT = null
    this.vuil = true
    this.volg.reset()
    for (const a of this.autos) { this.scene.remove(a.groep, a.label, a.schijf, a.schaduw); a.label.element.remove() }
    this.autos = data.spelers.map((s) => {
      const hitbox = HITBOX[s.auto] ?? HITBOX.Octane
      const kleur = s.team === 0 ? KLEUR.blauw : KLEUR.oranje
      const { groep, vlam } = maakAuto(hitbox, kleur, AUTO_SCHAAL)
      // Teamschijf op de vloer: leesbaar in bovenaanzicht en bij luchtacties (projectie)
      const schijf = new THREE.Mesh(new THREE.RingGeometry(150, 190, 40),
        new THREE.MeshBasicMaterial({ color: kleur, transparent: true, opacity: 0.45, depthWrite: false, side: THREE.DoubleSide }))
      schijf.rotation.x = -Math.PI / 2
      const schaduw = maakSchaduw(hitbox[1] * AUTO_SCHAAL * 1.25, hitbox[0] * AUTO_SCHAAL * 1.2)
      const div = document.createElement('div')
      div.className = 'label3d'
      div.style.borderColor = s.team === 0 ? '#3d8bff' : '#e06a12'
      div.innerHTML = `${s.naam}<span class="boost"><i></i></span>`
      const label = new CSS2DObject(div)
      label.center.set(0.5, 1)
      this.scene.add(groep, label, schijf, schaduw)
      return { groep, vlam, label, schijf, schaduw, boostEl: div.querySelector('i'), vooruit: new THREE.Vector3(1, 0, 0), weg: true }
    })
    // Standaard de eigen speler volgen
    this.volgK = Math.max(0, data.spelers.findIndex((s) => s.id === data.meta?.ik))
    this.werkVolgBij()
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

  // Catmull-Rom tussen frame i en i+1 (met buren i-1 en i+2): haalt de 30 fps-knikken uit snelle banen.
  // Nooit over afwezige frames of teleports heen; een ontbrekende buur wordt lineair doorgetrokken.
  // Geeft false als er niet geïnterpoleerd kan worden (uit staat dan gewoon op frame i).
  interpoleer(uit, a, stride, i, f, sprong) {
    const n = this.data.t.length, s2 = sprong * sprong
    const p1 = naarPos(this._p1, a, i * stride)
    if (afwezig(a, i * stride) || i + 1 >= n || afwezig(a, (i + 1) * stride)) { uit.copy(p1); return false }
    const p2 = naarPos(this._p2, a, (i + 1) * stride)
    if (p1.distanceToSquared(p2) > s2) { uit.copy(p1); return false }
    let p0 = i > 0 && !afwezig(a, (i - 1) * stride) ? naarPos(this._p0, a, (i - 1) * stride) : null
    if (!p0 || p0.distanceToSquared(p1) > s2) p0 = this._p0.copy(p1).multiplyScalar(2).sub(p2)
    let p3 = i + 2 < n && !afwezig(a, (i + 2) * stride) ? naarPos(this._p3, a, (i + 2) * stride) : null
    if (!p3 || p3.distanceToSquared(p2) > s2) p3 = this._p3.copy(p2).multiplyScalar(2).sub(p1)
    const f2 = f * f, f3 = f2 * f
    const c0 = -0.5 * f3 + f2 - 0.5 * f, c1 = 1.5 * f3 - 2.5 * f2 + 1, c2 = -1.5 * f3 + 2 * f2 + 0.5 * f, c3 = 0.5 * f3 - 0.5 * f2
    uit.set(
      c0 * p0.x + c1 * p1.x + c2 * p2.x + c3 * p3.x,
      c0 * p0.y + c1 * p1.y + c2 * p2.y + c3 * p3.y,
      c0 * p0.z + c1 * p1.z + c2 * p2.z + c3 * p3.z)
    return true
  }

  toon(t) {
    if (!this.data || t === this._laatsteT) return
    // Grote sprong in de tijd (tijdlijn, event aanklikken) → volgcamera direct op de nieuwe plek
    if (this._laatsteT == null || Math.abs(t - this._laatsteT) > 1) this.volg.reset()
    this._laatsteT = t
    this.vuil = true
    const [i, f] = this.zoek(t)
    const j = Math.min(i + 1, this.data.t.length - 1)
    const b = this.data.bal, fps = this.data.fps || 30

    const balGlad = this.interpoleer(this.bal.position, b, BAL_STRIDE, i, f, SPRONG_BAL)
    naarQuat(this._q, b, i * BAL_STRIDE + 3)
    if (balGlad) { naarQuat(this._q2, b, j * BAL_STRIDE + 3); this.bal.quaternion.slerpQuaternions(this._q, this._q2, f) }
    else this.bal.quaternion.copy(this._q)
    const balY = this.bal.position.y
    this.bal.position.y = balHoogte(balY)
    // Schaduw groeit en vervaagt met de hoogte: zo lees je hoe hoog de bal is
    const sb = BAL_STRAAL * BAL_SCHAAL * 2.1 * (1 + balY / 1500)
    this.balSchaduw.position.set(this.bal.position.x, 2.5, this.bal.position.z)
    this.balSchaduw.scale.set(sb, 1, sb)
    this.balSchaduw.material.opacity = 0.62 * Math.max(0.18, 1 - balY / 1700)
    this.bal.visible = this.balSchaduw.visible = !afwezig(b, i * BAL_STRIDE)

    this.data.spelers.forEach((s, k) => {
      const a = this.autos[k], fr = s.frames, o = i * SPELER_STRIDE
      const pos = a.groep.position
      const glad = this.interpoleer(pos, fr, SPELER_STRIDE, i, f, SPRONG_AUTO)
      naarQuat(this._q, fr, o + 3)
      if (glad) { naarQuat(this._q2, fr, j * SPELER_STRIDE + 3); a.groep.quaternion.slerpQuaternions(this._q, this._q2, f) }
      else a.groep.quaternion.copy(this._q)
      a.boostEl.style.width = fr[o + 7] + '%'
      a.label.position.set(pos.x, pos.y + 160, pos.z)
      a.schijf.position.set(pos.x, 2, pos.z)
      // Gedemoleerd (kolom ≥ 0) of afwezig (parser vult (0,0,0) in, bv. tijdens goal-reset) → verbergen
      const weg = fr[o + 8] >= 0 || afwezig(fr, o)
      a.groep.visible = !weg
      a.label.visible = a.schijf.visible = !weg && !a.eigen
      a.weg = weg

      // Rijrichting (horizontaal) voor de volgcamera: snelheid als de auto rijdt, anders de neus
      if (glad) {
        this._v.set(fr[o + SPELER_STRIDE] - fr[o], 0, fr[o + SPELER_STRIDE + 1] - fr[o + 1]).multiplyScalar(fps)
        if (this._v.lengthSq() > 300 * 300) a.vooruit.copy(this._v).normalize()
        else {
          this._v.set(1, 0, 0).applyQuaternion(a.groep.quaternion); this._v.y = 0
          if (this._v.lengthSq() > 0.09) a.vooruit.copy(this._v).normalize()
        }
      }

      // Boost: meter loopt terug over een venster van 3 frames (de waarde staat soms 2 frames stil)
      const vorig = Math.max(0, i - 1), later = Math.min(this.data.t.length - 1, i + 2)
      a.vlam.visible = !weg && fr[later * SPELER_STRIDE + 7] < fr[vorig * SPELER_STRIDE + 7] - 0.5
      if (a.vlam.visible) a.vlam.scale.x = 0.85 + 0.25 * Math.abs(Math.sin(t * 47 + k * 1.7))

      // Contactschaduw: alleen als de auto dicht bij de vloer is
      const hoogte = pos.y - 17
      a.schaduw.visible = !weg && hoogte < 600
      if (a.schaduw.visible) {
        a.schaduw.position.set(pos.x, 2.5, pos.z)
        this._v.set(1, 0, 0).applyQuaternion(a.groep.quaternion)
        a.schaduw.rotation.y = Math.atan2(-this._v.z, this._v.x)
        a.schaduw.material.opacity = 0.55 * (1 - hoogte / 600)
      }
    })

    this.werkSpoorBij(i)
  }

  // Spoor van de bal over de laatste seconden; stopt bij een reset (afwezig/teleport) en sluit aan op de bal
  werkSpoorBij(i) {
    const stap = Math.max(1, Math.round((SPOOR_SECONDEN * this.data.fps) / this.spoorMax))
    const pos = this.spoorGeo.attributes.position.array, kl = this.spoorGeo.attributes.color.array
    const b = this.data.bal, max2 = (SPRONG_BAL * stap) ** 2
    let geknipt = false
    for (let n = this.spoorMax - 1; n >= 0; n--) {
      const o = n * 3
      if (n === this.spoorMax - 1) { pos[o] = this.bal.position.x; pos[o + 1] = this.bal.position.y; pos[o + 2] = this.bal.position.z }
      else {
        const idx = Math.max(0, i - (this.spoorMax - 2 - n) * stap) * BAL_STRIDE
        const x = b[idx], y = balHoogte(b[idx + 2]), z = b[idx + 1]
        const dx = x - pos[o + 3], dy = y - pos[o + 4], dz = z - pos[o + 5]
        if (!geknipt && (afwezig(b, idx) || dx * dx + dy * dy + dz * dz > max2)) geknipt = true
        // Na een knip vallen de oudere punten samen met het laatste geldige punt (lengte 0, onzichtbaar)
        if (geknipt) { pos[o] = pos[o + 3]; pos[o + 1] = pos[o + 4]; pos[o + 2] = pos[o + 5] }
        else { pos[o] = x; pos[o + 1] = y; pos[o + 2] = z }
      }
      const w = (n / this.spoorMax) ** 1.5
      kl[o] = w; kl[o + 1] = w * 0.95; kl[o + 2] = w * 0.8
    }
    this.spoorGeo.attributes.position.needsUpdate = true
    this.spoorGeo.attributes.color.needsUpdate = true
  }

  render() {
    const nu = performance.now(), dt = Math.min(0.1, (nu - (this._vorigeRender ?? nu)) / 1000)
    this._vorigeRender = nu
    let veranderd = this.vuil
    if (!VOLG.has(this.cameraModus)) veranderd = this.controls.update() || veranderd
    else {
      const a = this.autos[this.volgK]
      if (a) veranderd = this.volg.stap(this.camera, {
        auto: a.weg ? null : a.groep.position,
        bal: this.bal.visible ? this.bal.position : null,
        vooruit: a.vooruit, modus: this.cameraModus,
      }, dt) || veranderd
    }
    if (!veranderd) return
    this.vuil = false
    this.renderer.render(this.scene, this.camera)
    this.labels.render(this.scene, this.camera)
  }
}
