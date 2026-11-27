#!/usr/bin/env python3
"""v12 asset polish: remove magenta/color fringes, pad to square, export 128/256/512 WebP."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

ROOT = Path("/workspace/slot-app")
ASSETS = ROOT / "assets"


def load_rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def clean_fringe(im: Image.Image, alpha_cut: int = 28, mag_alpha: int = 160) -> Image.Image:
    """Zero out magenta/pink in low-alpha edge pixels and despill semi-transparent fringes.

    Interior high-alpha purple (neon lightning, gems) is left alone.
    """
    im = im.copy()
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                px[x, y] = (0, 0, 0, 0)
                continue
            magenta = (r > 130 and b > 70 and g < 110 and (r - g) > 40 and (b - g) > 10)
            pink = (r > 150 and g < 90 and b > 60 and (r - g) > 50)
            if a < alpha_cut and (magenta or pink):
                px[x, y] = (0, 0, 0, 0)
                continue
            if a < mag_alpha and (magenta or pink):
                # shrink the halo rather than keep a coloured fringe
                na = max(0, a - 80) if a < 120 else int(a * 0.35)
                # pull RGB toward neutral/black so leftover colour does not halo
                px[x, y] = (int(r * 0.25), int(g * 0.25), int(b * 0.25), na)
    return im


def pad_square(im: Image.Image, size: int) -> Image.Image:
    im = im.copy()
    # trim fully transparent borders first, keep a little padding
    bbox = im.getbbox()
    if bbox:
        l, t, r, b = bbox
        pad = 4
        l = max(0, l - pad)
        t = max(0, t - pad)
        r = min(im.width, r + pad)
        b = min(im.height, b + pad)
        im = im.crop((l, t, r, b))
    w, h = im.size
    scale = (size * 0.92) / max(w, h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(im, ((size - nw) // 2, (size - nh) // 2), im)
    # mild crispness
    canvas = canvas.filter(ImageFilter.UnsharpMask(radius=1.2, percent=110, threshold=2))
    return canvas


def save_webp(im: Image.Image, path: Path, quality: int = 90) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "WEBP", quality=quality, method=6)


def export_symbol(src: Path, dest_dir: Path, stem: str) -> None:
    im = clean_fringe(load_rgba(src))
    master = pad_square(im, 512)
    save_webp(master, dest_dir / f"{stem}-512.webp", 90)
    save_webp(master.resize((256, 256), Image.Resampling.LANCZOS), dest_dir / f"{stem}.webp", 90)
    save_webp(master.resize((128, 128), Image.Resampling.LANCZOS), dest_dir / f"{stem}-128.webp", 88)
    print(f"  symbol {dest_dir.name}/{stem}")


def upscale_rect(src: Path, dest: Path, scale: float = 1.6, quality: int = 86) -> None:
    im = load_rgba(src)
    w, h = im.size
    out = im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    out = out.filter(ImageFilter.UnsharpMask(radius=1.0, percent=90, threshold=2))
    # tiles are opaque photos
    if dest.suffix == ".webp":
        out.convert("RGB").save(dest, "WEBP", quality=quality, method=6)
    else:
        out.save(dest)
    print(f"  upscale {dest.relative_to(ASSETS)} {out.size}")


def draw_chip(diameter: int, body: tuple, edge: tuple, inlay: tuple, label: str) -> Image.Image:
    im = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    m = 4
    # drop shadow
    d.ellipse((m + 4, m + 8, diameter - m + 2, diameter - m + 6), fill=(0, 0, 0, 80))
    # outer rim
    d.ellipse((m, m, diameter - m, diameter - m), fill=edge)
    # body
    inset = int(diameter * 0.08)
    d.ellipse((m + inset, m + inset, diameter - m - inset, diameter - m - inset), fill=body)
    # edge notches (12)
    cx = cy = diameter / 2
    r_out = diameter / 2 - m - 1
    r_in = r_out - diameter * 0.07
    for i in range(12):
        a0 = math.radians(i * 30 - 7)
        a1 = math.radians(i * 30 + 7)
        pts = []
        for a in (a0, a1):
            pts.append((cx + r_out * math.cos(a), cy + r_out * math.sin(a)))
        for a in (a1, a0):
            pts.append((cx + r_in * math.cos(a), cy + r_in * math.sin(a)))
        d.polygon(pts, fill=(255, 236, 180, 230))
    # inner ring
    inset2 = int(diameter * 0.22)
    d.ellipse((inset2, inset2, diameter - inset2, diameter - inset2), outline=edge, width=3)
    d.ellipse((inset2 + 4, inset2 + 4, diameter - inset2 - 4, diameter - inset2 - 4), fill=inlay)
    # highlight
    d.arc((m + 8, m + 6, diameter - m - 8, diameter * 0.62), 200, 340, fill=(255, 255, 255, 90), width=3)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(diameter * 0.22))
    except Exception:
        font = ImageFont.load_default()
    # center label
    tw = d.textbbox((0, 0), label, font=font)
    tw, th = tw[2] - tw[0], tw[3] - tw[1]
    d.text(((diameter - tw) / 2, (diameter - th) / 2 - 2), label, font=font, fill=(255, 248, 220, 255))
    return im


CHIP_COLORS = {
    100: ((40, 110, 210), (20, 60, 140), (25, 80, 180)),
    500: ((40, 150, 90), (20, 90, 50), (30, 120, 70)),
    1000: ((200, 40, 50), (130, 15, 25), (170, 30, 40)),
    5000: ((30, 30, 34), (10, 10, 12), (50, 50, 56)),
    10000: ((150, 90, 210), (90, 40, 150), (120, 60, 180)),
    25000: ((200, 140, 30), (140, 90, 10), (180, 120, 20)),
    50000: ((220, 210, 200), (140, 120, 90), (180, 160, 130)),
}


def label_for(n: int) -> str:
    if n >= 1000:
        return f"{n // 1000}K"
    return str(n)


def main() -> None:
    symbols = ["amethyst", "citrine", "coin", "emerald", "greentea", "quartz",
               "ruby", "sapphire", "scatter", "shard", "topaz", "wild"]

    print("crystal symbols")
    for stem in symbols:
        src = ASSETS / "symbols" / f"{stem}.webp"
        if src.exists():
            export_symbol(src, ASSETS / "symbols", stem)

    for theme in ("dragon", "pharaoh", "neon"):
        print("theme", theme)
        d = ASSETS / "themes" / theme
        for stem in symbols:
            src = d / f"{stem}.webp"
            if src.exists():
                export_symbol(src, d, stem)

    print("cards")
    for name in ("royal-A", "royal-J", "royal-K", "royal-Q"):
        src = ASSETS / "cards" / f"{name}.webp"
        if src.exists():
            im = clean_fringe(load_rgba(src))
            master = pad_square(im, 512)
            save_webp(master, ASSETS / "cards" / f"{name}.webp", 90)
            print("  card", name)
    back = ASSETS / "cards" / "back.webp"
    if back.exists():
        im = load_rgba(back)
        w, h = 600, 840
        out = im.resize((w, h), Image.Resampling.LANCZOS).filter(
            ImageFilter.UnsharpMask(radius=1.0, percent=90, threshold=2)
        )
        save_webp(out, ASSETS / "cards" / "back.webp", 88)
        save_webp(out.resize((150, 210), Image.Resampling.LANCZOS), ASSETS / "cards" / "back-sm.webp", 86)
        print("  card back")

    print("tiles")
    tiles = ASSETS / "tiles"
    for p in sorted(tiles.glob("*.webp")):
        if p.name.endswith("-sm.webp"):
            continue
        im = Image.open(p)
        if im.size[0] < 1100:
            upscale_rect(p, p, scale=1.6, quality=85)
            # refresh sm
            sm = tiles / p.name.replace(".webp", "-sm.webp")
            small = Image.open(p).convert("RGB")
            small = small.resize((640, int(640 * small.height / small.width)), Image.Resampling.LANCZOS)
            small.save(sm, "WEBP", quality=80, method=6)

    print("ui")
    av = ASSETS / "ui" / "avatar.webp"
    if av.exists():
        im = clean_fringe(load_rgba(av))
        master = pad_square(im, 256)
        save_webp(master, av, 90)
        print("  avatar")
    logo = ASSETS / "ui" / "logo.webp"
    if logo.exists() and (ASSETS / "ui" / "logo-512.webp").exists():
        # re-export 256 from 512 for consistency
        im = load_rgba(ASSETS / "ui" / "logo-512.webp")
        save_webp(im.resize((256, 256), Image.Resampling.LANCZOS), logo, 90)
        print("  logo 256")

    print("chips")
    chip_dir = ASSETS / "chips"
    for n, colors in CHIP_COLORS.items():
        body, edge, inlay = colors
        im = draw_chip(256, body, edge, inlay, label_for(n))
        save_webp(im, chip_dir / f"chip-{n}.webp", 90)
        save_webp(im.resize((128, 128), Image.Resampling.LANCZOS), chip_dir / f"chip-{n}-128.webp", 88)
        print("  chip", n)

    # coin particle for fountains
    coin = pad_square(clean_fringe(load_rgba(ASSETS / "symbols" / "coin.webp")), 128)
    save_webp(coin, ASSETS / "ui" / "coin-fx.webp", 90)
    print("done")


if __name__ == "__main__":
    main()
