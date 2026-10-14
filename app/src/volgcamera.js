import * as THREE from 'three'

// Volgcamera in Rocket League-stijl: achter de gevolgde auto, kijkend naar de bal (balcam) of in de rijrichting (autocam).
// Alle demping rekent met de echte dt, dus het beeld is even rustig op 30, 60 of 120 Hz.
// Alleen de kijkrichting (yaw/pitch) zit op een kritisch gedempte veer: een bal die snel van richting wisselt
// geeft dan een vloeiende draai in plaats van schokken. Het anker volgt de (al gladde) auto bijna direct.
const AFSTAND = 780, HOOGTE = 250, VOORUIT = 1500
const OMEGA_RICHTING = 6.5, K_ANKER = 16
const SPRONG = 1200 // verder dan dit in één beeld = teleport (kickoff, respawn, zoeken) → meteen overschakelen
const MIN_Y = 45, MAX_Y = 1950

// Kritisch gedempte veer (Game Programming Gems 4, 'SmoothDamp'); s = { x, v }
function veer(s, doel, omega, dt) {
  const e = omega * dt, exp = 1 / (1 + e + 0.48 * e * e + 0.235 * e * e * e)
  const d = s.x - doel, tmp = (s.v + omega * d) * dt
  s.v = (s.v - omega * tmp) * exp
  s.x = doel + (d + tmp) * exp
}
const hoekVerschil = (a, b) => Math.atan2(Math.sin(a - b), Math.cos(a - b))
const glad = (x, a, b) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t) }

export class VolgCamera {
  constructor() {
    this.anker = new THREE.Vector3()
    this.yaw = { x: 0, v: 0 }
    this.pitch = { x: 0, v: 0 }
    this.klaar = false
    this._d = new THREE.Vector3(); this._pos = new THREE.Vector3(); this._kijk = new THREE.Vector3()
  }

  reset() { this.klaar = false }

  // auto/bal: Vector3 of null (afwezig, gedemoleerd). vooruit: horizontale rijrichting van de auto.
  // Geeft true zolang de camera nog beweegt; stilstaand beeld hoeft dan niet opnieuw getekend.
  stap(camera, { auto, bal, vooruit, modus }, dt) {
    let snap = !this.klaar
    if (auto) {
      if (snap || this.anker.distanceToSquared(auto) > SPRONG * SPRONG) { this.anker.copy(auto); snap = true }
      else this.anker.lerp(auto, 1 - Math.exp(-K_ANKER * dt))
    } else if (!this.klaar) return false // nog niets om te volgen: camera laten staan

    // Gewenste kijkrichting
    const vYaw = Math.atan2(vooruit.x, vooruit.z)
    let yaw = vYaw, pitch = 0.04
    if (modus === 'bal' && bal) {
      const d = this._d.subVectors(bal, this.anker), len = d.length()
      // Bal vlak bij de auto: richting wordt onrustig → mengen met de rijrichting
      const w = glad(len, 220, 900)
      yaw = vYaw + hoekVerschil(Math.atan2(d.x, d.z), vYaw) * w
      pitch = pitch + (Math.min(0.7, Math.max(-0.25, Math.asin(d.y / (len || 1)))) - pitch) * w
    }
    if (snap) {
      this.yaw.x = yaw; this.pitch.x = pitch; this.yaw.v = this.pitch.v = 0
    } else {
      veer(this.yaw, this.yaw.x + hoekVerschil(yaw, this.yaw.x), OMEGA_RICHTING, dt)
      veer(this.pitch, pitch, OMEGA_RICHTING, dt)
    }
    this.klaar = true

    const cp = Math.cos(this.pitch.x)
    const d = this._d.set(Math.sin(this.yaw.x) * cp, Math.sin(this.pitch.x), Math.cos(this.yaw.x) * cp)
    const pos = this._pos.copy(this.anker).addScaledVector(d, -AFSTAND)
    pos.y = Math.min(MAX_Y, Math.max(MIN_Y, pos.y + HOOGTE))
    const kijk = this._kijk.copy(this.anker).addScaledVector(d, VOORUIT)
    kijk.y += HOOGTE * 0.25
    const verschoven = camera.position.distanceToSquared(pos) > 0.25
    camera.position.copy(pos)
    camera.lookAt(kijk)
    return snap || verschoven || Math.abs(this.yaw.v) > 1e-4 || Math.abs(this.pitch.v) > 1e-4
  }
}
