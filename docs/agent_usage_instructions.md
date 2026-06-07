# Kumiki Usage Instructions

## Background

When a workspace is initialized with Kigumi, `kumiki` is installed into that workspace `.venv`. Resolve the installed package path with `.venv/bin/python3 -c "import kumiki, pathlib; print(pathlib.Path(kumiki.__file__).resolve().parent)"` (on Windows use `.venv\\Scripts\\python.exe`), then read `<that_path>/docs/concepts.md` first to understand Kumiki core concepts and architecture.

## General Usage Pattern *START HERE*

Unless the user is specific about what they want, always follow the following implementation pattern. Details on how to do these steps are later in this doc.

- for structure, define a `Footprint` for the whole structure
- create initial timbers by placing posts vertically on the footprint or place mudsilles horizontally on the footprint
- for timbers spanning between existing timbers always use the join_timbers method
- only create timbers manually if the above methods are insufficient
- at this point, you can show the user the design and confirm it's what they are looking for
- once all timbers are in place, create joints binding everything together
- iterate with the user until they are satisfied

## Imports

Import via the top-level `kumiki` module:
```python
from kumiki import *
```

## Numeric Values

- **Always use SymPy types (Rational or Float) -- never Python floats.**
- Use the `inches()` and `feet()` helpers for imperial measurements:
  ```python
  inches(3)               # 3 inches
  inches(3, 2)            # 3/2 inches = 1.5"
  feet(Rational(7, 2))    # 3.5 feet
  ```
- Use `mm()`, `cm()` and `m()` for metric
- Use `degrees()` and `radians()` for angles
- Use `Matrix([...])` for vectors, always with `Rational` or `Integer` values.

## Creating Timbers

Timbers for a typical structure are usually defined

- first create a `Footprint` for the footprint of the structure.
- then use methods in `footprint.py` to define timbers directly on the footprint (touching the ground)
    - `create_horizontal_timber_on_footprint`
    - `create_vertical_timber_on_footprint`
- use methods in `construction.py` to define remaining timbers based on existing timbers
    - `join_face_aligned_on_face_aligned_timbers` for connecting timbers at right angles
    - `join_timbers` for simple connections between two timbers
    - `create_axis_aligned_timber` for timbers aligned to cartesian axis
    - `timber_from_directions` for arbitrarily aligned timbers

## Cutting Joints

Once timbers have been laid out, use the various `cut_*` methods to cut joints joining the timbers. There are many types of joints.

Almost all joints have a `cut_basic_*` variation inside of basic_joints.py which take minimal parameters. Always use the basic variants until the user provides specific requirements.

### finding joint parameters

Joint parameters are always set relative to one of the features on one of the timbers in the arrangement. Oftentimes the user will want to set the parameter relative to some other feature. Use the methods in measuring.py to convert measurements between features.

### default joints for generic designs

If the user does not specify which joint, use the following (or one of its variants) as defaults:

- for butt joints use cut_mortise_and_tenon_joint
- for corner joints use cut_plain_miter_joint or cut_plain_corner_lap_joint
- for splice joint use cut_plain_splice_lap_joint_on_aligned_timbers
- for cross joints use cut_plain_cross_lap_joint

### default joints for timber frames

- for beam-to-post joints use cut_mortise_and_tenon_joint, with a peg if the beam butts into the post, and without a peg if the beam sits above the post
- for tie-beams or beams under substantial loads, consider using cut_wedged_half_dovetail_mortise_and_tenon_joint instead as it's much stronger
- for rafter-to-rafter joints use cut_tongue_and_fork_corner_joint
- for mudsill splice joints use cut_lapped_gooseneck_joint with the gooseneck facing upwards
- for mudsill corner joints use either
    - cut_plain_corner_lap_joint (simplest)
    - cut_mortise_and_tenon_joint (more complicated)
    - cut_mitered_and_keyed_lap_joint (most complicated, no end grain exposed)
- for joist-to-beam or joist-to-mudsill joints use
    - cut_dropin_housed_butt_joint (simplest)
    - cut_housed_dovetail_butt_joint (if joist needs to resist spreading forces)

## Combining everything into a Frame

Your file should typically have some `example` function that returns a Frame. The function must be explicity typed to return type `Frame` in order for it be to picked up by the project scanner.

Use `Frame.from_joints` to merge cuts on shared timbers across multiple joints.

```python
def example() -> Frame:
    # establish footprint
    # create timbers
    # create joints
    # merge into a frame and return the results
    return Frame.from_joints([joint1, joint2, joint3], name="my_frame")
```

The `example` function name is special, it is what kigumi will scan for and render when opening your file.

Supported arguments types added to the `example` function will be displayed in the parametrization section in Kigumi. However remember that since the update flow is agentic, having constants in the example file is often better. All arguments to the `example` function must have default values.

# Validation Workflow

When authoring a frame for the user, always test locally first just by running the python script directly to confirm there are no errors and the logging looks accurate.

Afterwards, if the user is wanting a full agentic development loop, test the frame by actually opening it in Kigumi

## VS Code Commands for Full Agentic Development Loop

Use this sequence after headless local validation passes.

1. Open the frame in viewer
    - Command Palette: `Kigumi: Open Current File In Viewer`
    - Command id: `kigumi.openCurrentFileInViewer`
2. Open Kigumi explorer (optional but useful for pattern workflows)
    - Command Palette: `Kigumi: Open Explorer`
    - Command id: `kigumi.explorer`
3. Toggle auto refresh on file change as needed for the current task
    - Command Palette: `Kigumi: Toggle Auto Refresh On File Change`
    - Command id: `kigumi.toggleAutoRefreshOnFileChange`

For automation-driven checks (agent/testing flows), call these command ids directly:

1. Open a specific file in viewer: `kigumi.automationOpenFileInViewer` (with `filePath`)
2. List active sessions: `kigumi.automationListSessions`
3. Refresh a specific session: `kigumi.automationRefreshSession`
4. Read disk-backed JSONL logs: `kigumi.automationReadSessionLogs`
5. Read camera state: `kigumi.automationGetCameraState`
6. Set camera state: `kigumi.automationSetCameraState`
7. Capture 3D viewport screenshot: `kigumi.captureScreenshot`

Expected artifacts from the automated loop:

- Session logs in `.kigumi/logs/*.jsonl`
- Screenshots in `.kigumi/automation/`

Common automation loop example:

1. `kigumi.automationOpenFileInViewer` with `filePath: "/absolute/path/to/frame.py"`
2. `kigumi.automationListSessions`
3. `kigumi.automationRefreshSession` with `dirtyOnce: true`
4. `kigumi.automationReadSessionLogs` filtering for warnings/errors
5. `kigumi.automationGetCameraState`
6. `kigumi.captureScreenshot`

# Creating new Patterns

TODO
