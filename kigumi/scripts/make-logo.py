"""Kigumi's logo, 木 as a small timber frame: writes logo.svg and the PNG icons from one drawing.

    .venv/bin/python kigumi/scripts/make-logo.py

  logo.svg              the logo, full bleed
  extension-icon.png    VS Code's extension icon (256 px)
  app-icon.png          the standalone app's icon (1024 px, inset as macOS draws app icons)
  hosts/pyodide/page/favicon.png   the browser version's favicon (64 px)
"""
from pathlib import Path

from PIL import Image, ImageDraw

KIGUMI = Path(__file__).resolve().parents[1]

# The frame, traced from a render of it (pixels, y down): post, tie beam, two braces, pegs. The post is
# a little wider than drawn, and the pegs bigger, to hold up at icon sizes.
POST = [(937, 150), (965, 141), (1001.5, 137), (1038, 141), (1066, 150), (1066, 1688), (937, 1688)]
BEAM_LEFT = [(369, 608), (486, 596), (604, 585), (721, 578), (838, 574), (955, 573), (955, 690), (369, 690)]
BRACE_LEFT = [(955, 755), (930, 780), (852, 857), (768, 935), (690, 1001), (601, 1074), (511, 1141), (421, 1206),
              (521, 1306), (955, 875)]
SQUARE_PEGS = [(870, 647), (1133, 647)]
ROUND_PEGS = [(970, 800), (1033, 800)]
PEG = 34  # a peg's size
MIDDLE = 1001.5


def mirror(points):
    return [(2 * MIDDLE - x, y) for x, y in reversed(points)]


# The square the frame sits in, in the same pixels, and its colours.
VIEW_X, VIEW_Y, VIEW = 102, 13, 1800
SKY_TOP, SKY_BOTTOM = (206, 226, 199), (173, 203, 164)
WOOD, WOOD_EDGE = (243, 230, 208), (110, 82, 55)
BRASS, BRASS_EDGE = (214, 178, 95), (110, 82, 55)
EDGE = 18  # outline width, in the frame's pixels
CORNER = 0.22  # the rounded square's corner radius, as a share of its side

SHAPES = [  # (points, fill, outline), back to front
    (BEAM_LEFT, WOOD, WOOD_EDGE), (mirror(BEAM_LEFT), WOOD, WOOD_EDGE),
    (BRACE_LEFT, WOOD, WOOD_EDGE), (mirror(BRACE_LEFT), WOOD, WOOD_EDGE),
    (POST, WOOD, WOOD_EDGE),
]


def hex_colour(rgb):
    return '#%02x%02x%02x' % rgb


def svg():
    corner = CORNER * VIEW
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{VIEW_X} {VIEW_Y} {VIEW} {VIEW}">',
        '<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{hex_colour(SKY_TOP)}"/><stop offset="1" stop-color="{hex_colour(SKY_BOTTOM)}"/>'
        '</linearGradient></defs>',
        f'<rect x="{VIEW_X}" y="{VIEW_Y}" width="{VIEW}" height="{VIEW}" rx="{corner:g}" fill="url(#sky)"/>',
    ]
    for points, fill, edge in SHAPES:
        path = ' '.join(f'{x:g},{y:g}' for x, y in points)
        parts.append(f'<polygon points="{path}" fill="{hex_colour(fill)}" stroke="{hex_colour(edge)}" '
                     f'stroke-width="{EDGE}" stroke-linejoin="round"/>')
    for x, y in SQUARE_PEGS:
        parts.append(f'<rect x="{x - PEG / 2:g}" y="{y - PEG / 2:g}" width="{PEG}" height="{PEG}" fill="{hex_colour(BRASS)}" '
                     f'stroke="{hex_colour(BRASS_EDGE)}" stroke-width="7"/>')
    for x, y in ROUND_PEGS:
        parts.append(f'<circle cx="{x:g}" cy="{y:g}" r="{PEG / 2:g}" fill="{hex_colour(BRASS)}" '
                     f'stroke="{hex_colour(BRASS_EDGE)}" stroke-width="7"/>')
    parts.append('</svg>')
    return '\n'.join(parts) + '\n'


def render(size, inset=0.0, bold=1.0):
    """The logo as a `size` square PNG; `inset` leaves that share of each side clear (macOS app icons), and
    `bold` thickens the outlines (a favicon, seen at 16 px)."""
    scale_up = 4  # drawn large, then shrunk: smooth edges
    big = size * scale_up
    margin = round(big * inset)
    side = big - 2 * margin
    k = side / VIEW

    def at(x, y):
        return (margin + (x - VIEW_X) * k, margin + (y - VIEW_Y) * k)

    image = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    sky = Image.new('RGBA', (side, side))
    sky_draw = ImageDraw.Draw(sky)
    for row in range(side):
        t = row / max(side - 1, 1)
        sky_draw.line([(0, row), (side, row)], fill=tuple(round(a + (b - a) * t) for a, b in zip(SKY_TOP, SKY_BOTTOM)))
    mask = Image.new('L', (side, side), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, side - 1, side - 1], radius=round(CORNER * side), fill=255)
    image.paste(sky, (margin, margin), mask)

    draw = ImageDraw.Draw(image)
    edge = max(1, round(EDGE * k * bold))
    for points, fill, outline in SHAPES:
        scaled = [at(x, y) for x, y in points]
        draw.polygon(scaled, fill=fill)
        draw.line(scaled + [scaled[0]], fill=outline, width=edge, joint='curve')
    for x, y in SQUARE_PEGS:
        (ax, ay), (bx, by) = at(x - PEG / 2, y - PEG / 2), at(x + PEG / 2, y + PEG / 2)
        draw.rectangle([ax, ay, bx, by], fill=BRASS, outline=BRASS_EDGE, width=max(1, round(7 * k)))
    for x, y in ROUND_PEGS:
        (ax, ay), (bx, by) = at(x - PEG / 2, y - PEG / 2), at(x + PEG / 2, y + PEG / 2)
        draw.ellipse([ax, ay, bx, by], fill=BRASS, outline=BRASS_EDGE, width=max(1, round(7 * k)))
    return image.resize((size, size), Image.LANCZOS)


def main():
    (KIGUMI / 'logo.svg').write_text(svg())
    render(256).save(KIGUMI / 'extension-icon.png', optimize=True)
    # macOS draws an app icon's rounded square at 824 of 1024 px.
    render(1024, inset=100 / 1024).save(KIGUMI / 'app-icon.png', optimize=True)
    render(64, bold=1.8).save(KIGUMI / 'hosts/pyodide/page/favicon.png', optimize=True)
    print('Wrote logo.svg, extension-icon.png, app-icon.png and hosts/pyodide/page/favicon.png')


if __name__ == '__main__':
    main()
