"""Logo's (donkere achtergrond) → transparante varianten + alle formaten voor app, favicon en installer.

Achtergrond weghalen op lichtheid: bijna-zwart wordt transparant, met een zachte overgang zodat randen niet
kartelen. De donkere voegen tussen de balvlakken worden zo ook transparant en tonen de ondergrond.

Gebruik:
    uv run python ontwerp/maak_logos.py
"""
from pathlib import Path

import numpy as np
from PIL import Image

HIER = Path(__file__).resolve().parent
APP = HIER.parent / "app" / "public"
DESKTOP = HIER.parent / "desktop" / "bouw"


def transparant(pad: Path) -> Image.Image:
    a = np.asarray(Image.open(pad).convert("RGB")).astype(float)
    lum = a.max(axis=2)  # helderste kanaal: blauw/oranje/wit zijn hoog, achtergrond ~10–25
    alfa = np.clip((lum - 40) / (90 - 40), 0, 1)
    # Kleur 'ontmengen' van de donkere achtergrond, zodat halftransparante randen niet grauw worden
    bg = np.array([8, 12, 20], float)
    kleur = np.where(alfa[..., None] > 0.01, (a - bg * (1 - alfa[..., None])) / np.maximum(alfa[..., None], 0.01), 0)
    rgba = np.dstack([np.clip(kleur, 0, 255), alfa * 255]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def bijsnijden(img: Image.Image, marge: float = 0.04) -> Image.Image:
    box = img.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
    w, h = box[2] - box[0], box[3] - box[1]
    m = int(max(w, h) * marge)
    return img.crop((box[0] - m, box[1] - m, box[2] + m, box[3] + m))


def vierkant(img: Image.Image, achtergrond=None, opvulling: float = 0.0) -> Image.Image:
    z = max(img.size)
    z2 = int(z * (1 + 2 * opvulling))
    doek = Image.new("RGBA", (z2, z2), achtergrond or (0, 0, 0, 0))
    doek.alpha_composite(img, ((z2 - img.size[0]) // 2, (z2 - img.size[1]) // 2))
    return doek


def main() -> None:
    APP.mkdir(parents=True, exist_ok=True); DESKTOP.mkdir(parents=True, exist_ok=True)
    icoon = bijsnijden(transparant(HIER / "logo-icoon-origineel.png"))
    woord = bijsnijden(transparant(HIER / "logo-woordmerk-origineel.png"), 0.02)
    icoon_sq = vierkant(icoon)
    icoon_sq.resize((256, 256), Image.LANCZOS).save(APP / "logo.png")
    woord.save(APP / "logo-woordmerk.png")
    # App-iconen: logo op de donkere merk-achtergrond met wat ruimte (maskable-veilig)
    tegel = vierkant(icoon, (11, 14, 22, 255), 0.14)
    for n in (192, 512):
        tegel.resize((n, n), Image.LANCZOS).save(APP / f"icoon-{n}.png")
    tegel.resize((180, 180), Image.LANCZOS).save(APP / "apple-touch-icon.png")
    favicon = icoon_sq.resize((64, 64), Image.LANCZOS)
    favicon.save(APP / "favicon.png")
    # Windows-installer/snelkoppeling: .ico met meerdere maten + 512-png voor electron-builder
    tegel.resize((512, 512), Image.LANCZOS).save(DESKTOP / "icon.png")
    icoon_sq.save(DESKTOP / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icoon_sq.resize((64, 64), Image.LANCZOS).save(DESKTOP / "tray.png")
    print("klaar:", sorted(p.name for p in APP.glob("*.png")), sorted(p.name for p in DESKTOP.iterdir()))


if __name__ == "__main__":
    main()
