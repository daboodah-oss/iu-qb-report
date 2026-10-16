#!/usr/bin/env python3
"""Draw the 512px app icons from the trident's own vector path.

    python3 tools/make_icons.py

Writes icons/icon-512.png (crimson rounded square, white trident, the same
proportions as the hand-made icons/icon-192.png) and icons/icon-maskable-512.png
(crimson to the edge, trident inside the central 80% circle so a launcher
that crops to a circle or squircle never cuts it).  Both are referenced by
manifest.webmanifest.

The trident comes from assets/iu-trident.svg: one path of straight segments
(M, h, v, l, z), so it is parsed here rather than needing an SVG renderer.
One-time tool, run by hand when the logo changes; the scheduled build never
calls it.  Needs Pillow (pip install pillow), which requirements.txt does not.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CRIMSON = (0x99, 0x00, 0x00)
WHITE = (255, 255, 255)
SS = 4  # supersampling factor for smooth edges


def trident():
    """The trident's outline as [(x, y), ...] in SVG units, and (width, height)."""
    svg = (ROOT / "assets" / "iu-trident.svg").read_text(encoding="utf-8")
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
    d = re.search(r'<path d="([^"]+)"', svg).group(1)
    tokens = re.findall(r"[MmHhVvLlZz]|-?\d*\.?\d+", d)
    pts, x, y, cmd, i = [], 0.0, 0.0, None, 0
    while i < len(tokens):
        t = tokens[i]
        if t.isalpha():
            cmd = t; i += 1
            if cmd in "Zz":
                continue
            continue
        if cmd in "Mm":
            nx, ny = float(tokens[i]), float(tokens[i + 1]); i += 2
            x, y = (nx, ny) if cmd == "M" else (x + nx, y + ny)
        elif cmd in "Ll":
            nx, ny = float(tokens[i]), float(tokens[i + 1]); i += 2
            x, y = (nx, ny) if cmd == "L" else (x + nx, y + ny)
        elif cmd in "Hh":
            v = float(tokens[i]); i += 1
            x = v if cmd == "H" else x + v
        elif cmd in "Vv":
            v = float(tokens[i]); i += 1
            y = v if cmd == "V" else y + v
        else:
            sys.exit(f"make_icons: unsupported path command {cmd!r}")
        pts.append((x, y))
    return pts, (vb[2], vb[3])


def draw(size, height_frac=None, safe_frac=None, radius_frac=0.0):
    """One icon.  height_frac sizes the trident by the icon's height;
    safe_frac sizes it so its farthest corner sits inside that fraction
    of the icon (0.4 = the maskable safe circle's radius)."""
    from PIL import Image, ImageDraw
    pts, (w, h) = trident()
    n = size * SS
    if height_frac is not None:
        scale = height_frac * n / h
    else:
        cx, cy = w / 2, h / 2
        far = max(((px - cx) ** 2 + (py - cy) ** 2) ** 0.5 for px, py in pts)
        scale = safe_frac * n / far
    ox, oy = (n - w * scale) / 2, (n - h * scale) / 2
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    g = ImageDraw.Draw(img)
    if radius_frac:
        g.rounded_rectangle([0, 0, n - 1, n - 1], radius=radius_frac * n, fill=CRIMSON)
    else:
        g.rectangle([0, 0, n - 1, n - 1], fill=CRIMSON)
    g.polygon([(ox + px * scale, oy + py * scale) for px, py in pts], fill=WHITE)
    return img.resize((size, size), Image.LANCZOS)


def main():
    try:
        import PIL  # noqa: F401
    except ImportError:
        sys.exit("make_icons needs Pillow: pip install pillow")
    out = ROOT / "icons"
    # Proportions measured from icons/icon-192.png: trident 69% of the height,
    # corner radius about 20% of the side.
    draw(512, height_frac=0.693, radius_frac=0.2).save(out / "icon-512.png", optimize=True)
    # 0.38, not 0.40: a small margin inside the safe circle for antialiasing.
    draw(512, safe_frac=0.38).convert("RGB").save(out / "icon-maskable-512.png", optimize=True)
    print("wrote icons/icon-512.png and icons/icon-maskable-512.png")


if __name__ == "__main__":
    main()
