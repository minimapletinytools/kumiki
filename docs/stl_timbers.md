# STL timbers

Agent-generated supplement to the concepts and authoring instructions.

`create_stl_timber(reference, stl_path, *, units='mm', placement=None)` imports a
watertight STL as stock. The reference timber supplies its joinery coordinate system,
nominal size, length, world transform, and ticket. The mesh supplies the actual surface.
STL timbers can receive ordinary CSG cuts, but cannot extend their ends for joints.

```python
leg = create_stl_timber(reference, 'assets/leg.stl', units='mm')
```

Paths are relative to the Python file containing the call. STL files do not encode units;
choose `mm`, `cm`, `m`, or `in` explicitly when the default millimetres is inappropriate.
The importer rejects open, inconsistently wound, and non-finite meshes.

## Placement

Omitting `placement` creates a placeholder: a rectangular reference timber in amber,
with `(needs stl placement)` after its tree label. Select it to enter STL placement.
An already configured STL has an **Edit STL placement** button in the selection panel.

The editor isolates one timber. Other viewer actions are disabled until **Cancel**,
Escape, or a successful **Update configuration**. A frame refresh cancels the preview.
Move, Rotate, and Scale select a gizmo; numeric fields allow precise placement. Quarter
turn buttons rotate around the reference timber's axes. Scale handles follow the mesh's
rotated axes; uniform scaling is enabled initially. Right-drag orbits and the wheel zooms.
**Fit to reference** resets rotation and uniformly fits and centers the mesh in the
reference prism. **Reset** restores the placement present when the editor opened.

```python
leg = create_stl_timber(reference, 'assets/leg.stl', placement={
    'translation': [0, 0, 0],
    'rotation': [0, 0, 90],
    'scale': [1, 1, 1],
})
```

Scale is positive and dimensionless; rotation is intrinsic XYZ Euler angles in degrees;
translation is metres in the reference timber's local coordinates. The order is scale,
rotation, translation, then the reference timber's world transform. Local Z runs from
the bottom toward the top; X and Y run across the reference cross-section. An empty
mapping `placement={}` accepts the mesh with the identity transform.

**Update configuration** replaces or inserts only the creating call's `placement`
argument. Each independently editable timber needs a separate direct
`create_stl_timber(...)` call. A call shared by several timbers, aliased calls without
identifiable provenance, `**kwargs`, source outside the project, changed source, and
unsaved editor changes cannot be updated automatically. The editor reports the error
and offers **Copy configuration** and **Copy prompt for agent**. Preview changes do
not modify the model or file until the source update succeeds.

## Cabriole example and asset

Open `patterns/structures/cabriole_table.py` in Kigumi. It contains a four-leg table
with accepted placements and a separate placeholder beside it for practicing alignment.
It demonstrates stock shape and placement, without modeled fasteners.

Regenerate the included procedural mesh from the repository root:

```sh
uv run python tools/generate_cabriole_leg.py
```

An optional output path writes another copy. The generator creates a closed
millimetre-unit mesh with a swept profile, rounded foot, and square upper block.
The asset is generated locally; no external modeling service is required.

## Implementation map

- `kumiki/stl.py`: import, units, immutable placement and source-call provenance.
- `kumiki/csg/meshcsg.py`: triangle solid, membership, boundary and bounds; the common
  triangulator handles it alongside the existing CSG primitives.
- `kigumi/runner.py`: placement preview and source-edit preparation commands.
- `kigumi/stl_placement.py`: AST call matching and proposed text replacement; no write.
- `kigumi/stl-placement-source.js`: dirty-document and disk-content checks before writing.
- `kigumi/webview/stl-placement-editor.js`: isolated canvas, controls and resource lifetime.
  It owns its event listeners and disposes them together; existing viewer modes do not
  acquire placement-specific combinations of behavior.

STL surfaces have triangle geometry rather than named analytic face/curve features.
Use the reference timber's features for joinery and measurements. STL export uses the
actual mesh; exact STEP export of imported triangle stock is not provided.
