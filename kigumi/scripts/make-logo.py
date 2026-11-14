"""Kigumi's logo, 木 as a small timber frame, from a render of it (logo-source.png): writes the icons.

    .venv/bin/python kigumi/scripts/make-logo.py

  extension-icon.png    VS Code's extension icon (256 px)
  app-icon.png          the standalone app's icon (1024 px, inset as macOS draws app icons)
  hosts/pyodide/page/favicon.png   the browser version's favicon (64 px)
  hosts/pyodide/page/logo.png      the browser version's welcome page logo (256 px)
  ../website/public/favicon.png, apple-touch-icon.png   the website's icons (64 and 180 px)
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

KIGUMI = Path(__file__).resolve().parents[1]
WEBSITE = KIGUMI.parent / 'website' / 'public'
SOURCE = KIGUMI / 'logo-source.png'

# The square of the render the logo shows (pixels): the frame, with a margin around it.
CROP = (42, 116, 1134, 1208)
CORNER = 0.22  # the rounded square's corner radius, as a share of its side
CONTRAST = 1.0  # walnut on cream holds up when small without more
# Muted walnut timber on cream, in place of the render's pale timber on mint green.
WOOD = (133, 96, 66)
# The pegs and spline in honey, so they show against the walnut and the cream.
PEG = (218, 168, 92)
BACKGROUND = (240, 233, 220)
# The render's lightness of the timber and of the pegs: each is tinted relative to its own.
TIMBER_LIGHTNESS = 220
PEG_LIGHTNESS = 188


def timber_mask(image):
    """255 on the timber (its warm fill, outlines and pegs), 0 on the render's greenish background."""
    red, green, _blue = image.split()
    warm = ImageChops.subtract(red, green).point(lambda d: max(0, min(255, (d - 1) * 40)))
    dark = image.convert('L').point(lambda v: 255 if v < 215 else max(0, (232 - v) * 15))
    return ImageChops.lighter(warm, dark).filter(ImageFilter.GaussianBlur(0.6))


def peg_mask(image):
    """255 on the pegs and spline: yellower than the timber (red less blue about 60 to its 20)."""
    red, _green, blue = image.split()
    return ImageChops.subtract(red, blue).point(lambda d: max(0, min(255, (d - 38) * 18))).filter(ImageFilter.GaussianBlur(0.6))


def tinted(lightness, colour, base):
    """`colour` where `lightness` is `base`, lighter and darker with it: the render's shading and outlines."""
    return Image.merge('RGB', [lightness.point(lambda v, c=c: min(255, int(v * c / base))) for c in colour])


def wood_coloured(image):
    """`image` with its timber in WOOD and its pegs and spline in PEG, on BACKGROUND."""
    lightness = image.convert('L')
    out = Image.composite(tinted(lightness, WOOD, TIMBER_LIGHTNESS), Image.new('RGB', image.size, BACKGROUND),
                          timber_mask(image))
    return Image.composite(tinted(lightness, PEG, PEG_LIGHTNESS), out, peg_mask(image))


def render(size, inset=0.0, contrast=CONTRAST):
    """The logo as a `size` square PNG; `inset` leaves that share of each side clear (macOS app icons)."""
    margin = round(size * inset)
    side = size - 2 * margin
    source = Image.open(SOURCE).convert('RGB')
    square = wood_coloured(source.crop(CROP))
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
    render(64, contrast=1.15).save(KIGUMI / 'hosts/pyodide/page/favicon.png', optimize=True)
    render(256).save(KIGUMI / 'hosts/pyodide/page/logo.png', optimize=True)
    render(64, contrast=1.15).save(WEBSITE / 'favicon.png', optimize=True)
    render(180).save(WEBSITE / 'apple-touch-icon.png', optimize=True)
    print('Wrote extension-icon.png, app-icon.png, hosts/pyodide/page/favicon.png and logo.png, '
          'and the website\'s favicon.png and apple-touch-icon.png')


if __name__ == '__main__':
    main()
