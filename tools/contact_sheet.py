"""Build a contact sheet (grid of captioned thumbnails) from a folder of PNG screenshots.
Usage: python tools/contact_sheet.py artifacts/screenshots/after [--out contact-sheet.png] [--cols 5]"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--out", default="contact-sheet.png")
    ap.add_argument("--cols", type=int, default=5)
    a = ap.parse_args()
    folder = Path(a.folder)
    files = sorted(p for p in folder.glob("*.png") if p.name != a.out)
    cw, ch, pad, cap = 380, 540, 14, 34
    cols = a.cols
    rows = -(-len(files) // cols)
    sheet = Image.new("RGB", (cols * (cw + pad) + pad, rows * (ch + cap + pad) + pad), (236, 232, 222))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for n, p in enumerate(files):
        im = Image.open(p).convert("RGB")
        im.thumbnail((cw, ch))
        x, y = pad + (n % cols) * (cw + pad), pad + (n // cols) * (ch + cap + pad)
        sheet.paste(im, (x, y))
        d.rectangle([x - 1, y - 1, x + im.width, y + im.height], outline=(120, 120, 120))
        d.text((x, y + im.height + 6), p.stem[:58], fill=(20, 20, 20), font=font)
        d.text((x, y + im.height + 18), f"{Image.open(p).width}x{Image.open(p).height}px", fill=(90, 90, 90), font=font)
    sheet.save(folder / a.out, optimize=True)
    print(f"{len(files)} screenshots -> {folder / a.out} ({sheet.width}x{sheet.height})")


if __name__ == "__main__":
    main()
