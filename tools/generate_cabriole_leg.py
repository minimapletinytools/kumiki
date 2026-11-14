"""Generate the watertight, millimetre-unit cabriole-leg STL used by the examples."""
from pathlib import Path
import argparse
import numpy as np
import trimesh
from scipy.interpolate import PchipInterpolator


def generate(output: Path) -> None:
    # Height, diagonal sweep, radius, and superellipse exponent, from foot to square joinery block.
    stations = np.array([
        [0, 25, 30, 2], [12, 30, 42, 2], [35, 24, 36, 2], [80, 6, 24, 2],
        [150, -10, 22, 2], [260, -18, 26, 2], [380, -10, 34, 2],
        [480, 10, 45, 2.5], [550, 16, 48, 3], [630, 8, 40, 4],
        [680, 0, 35, 16], [720, 0, 35, 16],
    ])
    profile = PchipInterpolator(stations[:, 0], stations[:, 1:], axis=0)
    rings, sides = 145, 64
    vertices = []
    for z in np.linspace(0, 720, rings):
        sweep, radius, exponent = profile(z)
        for angle in np.linspace(0, 2 * np.pi, sides, endpoint=False):
            x, y = np.cos(angle), np.sin(angle)
            vertices.append([sweep + radius * np.sign(x) * abs(x) ** (2 / exponent),
                             sweep + radius * np.sign(y) * abs(y) ** (2 / exponent), z])
    faces = []
    for ring in range(rings - 1):
        for side in range(sides):
            a, b = ring * sides + side, ring * sides + (side + 1) % sides
            faces.extend([[a, b, b + sides], [a, b + sides, a + sides]])
    for side in range(1, sides - 1):
        faces.append([0, side + 1, side])
        top = (rings - 1) * sides
        faces.append([top, top + side, top + side + 1])
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    assert mesh.is_watertight and mesh.is_volume
    output.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(output)
    print(f'Wrote {output}: {len(mesh.faces)} triangles, units mm')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', nargs='?', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'patterns/assets/cabriole_leg.stl')
    generate(parser.parse_args().output)
