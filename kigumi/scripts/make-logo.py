"""Kigumi's logo, 木 as a small timber frame, from a render of it (logo-source.png): writes the icons.

    .venv/bin/python kigumi/scripts/make-logo.py

  extension-icon.png    VS Code's extension icon (256 px)
  app-icon.png          the standalone app's icon (1024 px, inset as macOS draws app icons)
  hosts/pyodide/page/favicon.png   the browser version's favicon (64 px)
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

KIGUMI = Path(__file__).resolve().parents[1]
SOURCE = KIGUMI / 'logo-source.png'

# The square of the render the logo shows (pixels): the frame, with a margin around it.
CROP = (38, 100, 1638, 1700)
# The viewer's floor reflection under the post (x from, x to, from y): painted over with the background beside it.
REFLECTION = (770, 906, 1563)
CORNER = 0.22  # the rounded square's corner radius, as a share of its side
CONTRAST = 1.15  # a little more than the render, so the pale timber holds up when small


def render(size, inset=0.0, contrast=CONTRAST):
    """The logo as a `size` square PNG; `inset` leaves that share of each side clear (macOS app icons)."""
    margin = round(size * inset)
    side = size - 2 * margin
    source = Image.open(SOURCE).convert('RGB')
    left, right, top = REFLECTION
    beside = source.crop((left - (right - left), top, left, source.height))
    source.paste(beside, (left, top))
    square = source.crop(CROP)
    square = ImageEnhance.Contrast(square).enhance(contrast).resize((side, side), Image.LANCZOS)
    scale_up = 4  # the corners drawn large, then shrunk: smooth edges
    mask = Image.new('L', (side * scale_up, side * scale_up), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, side * scale_up - 1, side * scale_up - 1],
                                           radius=round(CORNER * side * scale_up), fill=255)
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    image.paste(square, (margin, margin), mask.resize((side, side), Image.LANCZOS))
    return image


def main():
    render(256).save(KIGUMI / 'extension-icon.png', optimize=True)
    # macOS draws an app icon's rounded square at 824 of 1024 px.
    render(1024, inset=100 / 1024).save(KIGUMI / 'app-icon.png', optimize=True)
    # A browser tab shows it at 16 px: more contrast still.
    render(64, contrast=1.5).save(KIGUMI / 'hosts/pyodide/page/favicon.png', optimize=True)
    print('Wrote extension-icon.png, app-icon.png and hosts/pyodide/page/favicon.png')


if __name__ == '__main__':
    main()
