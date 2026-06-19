# Kumiki Usage Instructions

## Background

When starting work in a workspace, if in dout, run the **`init-kumiki-project`** skill (`docs/skills/init-kumiki-project/SKILL.md`).

## General Usage Pattern *START HERE*

Unless the user is specific about what they want, always follow the following implementation pattern:

- for structures, define a `Footprint` for the whole structure
- create initial timbers by placing posts vertically on the footprint or place mudsilles horizontally on the footprint
- for timbers spanning between existing timbers always use the join_timbers method
- only create timbers manually if the above methods are insufficient
- at this point, you can show the user the design and confirm it's what they are looking for
- once all timbers are in place, create joints binding everything together
- iterate with the user until they are satisfied


In addition, validate changes you make:

- run the frame code using python to ensure there are no errors
- use command `kigumi.automationOpenFileInViewer` with `filePath: "/absolute/path/to/frame.py"` to reload the frame after making changes
- use command `kigumi.automationReadSessionLogs` to get logs filtering for errors and warnings to validate your changes
- use command `kigumi.captureScreenshot` to get a screenshot of the rendered frame


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

- first create a `Footprint` for the footprint of the structure
- then use methods in `footprint.py` to define timbers directly on the footprint (touching the ground)
    - `create_horizontal_timber_on_footprint`
    - `create_vertical_timber_on_footprint`
    - placing on the inside of the footprint should be the default behavior
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

## VS Code Commands for Full Agentic Development Loop (only if you have access to VSCode commands, sorry Claude)

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

# Common Design Patterns

## splicing patterns

When members exceed a certain length it may be desireable to splice the member for the following reasons:

- very long timbers are harder to work with physically
- warping is more pronounced on very long timbers
- it is harder to source very long timbers

In these case, a splice joint is used. There are many types of splice joints. You will choose which splice joint to use based on the following:

- directional load requirements of the joint
- which direction the spliced timber will be typically seen from in the structure
- size of the timber being joined
- desired difficulty and complexity of the joint

Here are some typical guidelines:

- for mudsills which are usually bolted to the foundation and experience no loads except during disaster scenarios
    - use `cut_plain_splice_lap_joint_on_aligned_timbers` for simple construction
    - use `cut_lapped_gooseneck_joint` for premium construction
    - you can even use `cut_plain_butt_splice_joint_on_aligned_timbers` 🫠
- use `cut_plain_butt_splice_joint_on_aligned_timbers` as a placeholder in other scenarios until more splice joint types are added
    - otherwise never use `cut_plain_butt_splice_joint_on_aligned_timbers` as it resists no loads whatsoever


## structure patterns

### posts on mudsills

A very common pattern for a timber framed structure is to lay out mudsills on the perimeter of the footprint with posts on top. See `examples/oscarshed.py` for a structure built witth this pattern.

Posts in the middle of mudsills are joined with mortise and tenon joints without pegs, the tenon size must be longer in the length direction of the mudsill and typically 1/3rd the width of the mudsill in the other dimension.

For posts on top of a corner joint, you have a few options:

- rather than place posts directly on the corner, move them inwards a little bit so there is more space to cut joiner (this is what we did in oscarshed)
- use a 3 way corner joint (currently none exist)


### posts on ground with floor beams into posts

A less common and more complex pattern is to have posts directly touching the ground as if the house is on stilts. See `examples/tinyhouse120.py` for an example of this pattern

Floor beams connecting into corner posts can be joined with mortise and tenon joints, offsetting the tennons on each beam by a bit so that they do not intersect each other (this is what we did in tinyhouse120)

For beams connecting into non-corner posts, you have a few options:

- let the beam be continuous and split the post in two connecting to the floating floor beam with mortise and tenon joints such that there is a tiny stub post below the beam to support it from below
- use something like the `cut_splined_opposing_double_butt_joint` (complex) (this is what we did in tinyhouse120)

### girts between vertical members

`examples/tinyhouse120.py` uses this pattern

### top plates on posts

`examples/tinyhouse120.py` and `examples/oscarshed.py` use this pattern

### studs go between horizontal members

TODO 
`examples/tinyhouse120.py` and `examples/oscarshed.py` use this pattern

### braces go between vertical and horizontal members

TODO

# Creating new Patterns

TODO
