# Background jobs in the runner: drawings in parallel, and one mechanism for slow work (2026-10-29)

## What is there

**Assembly** is the one thing that runs in the background, built by hand:
`get_assembly` starts a `threading.Thread`, keeps a cancel `Event` per slot in
`_active_assembly_cancels`, answers `{pending: true}` at once, and the thread emits an unsolicited
`assembly_result` when done; a reload of the slot sets the event, and the solver polls it
(`should_cancel`). The extension has a dedicated `onAssemblyResult` hook. A thread only keeps the
runner answering; under the GIL it doesn't run in parallel with anything CPU-bound.

**Drawings** aren't the runner's at all. The frame's own code generates them before it returns the
frame (`cat_corner_cot._with_auto_drawings`: a plan plus one piece drawing per group, each running
kumiki's auto-dimensioning). Measured:

| Frame | Build | Of it, drawings | Drawings |
|---|---|---|---|
| `cat_corner_cot` | 6.8 s | ~all (17.29 of 17.38 s profiled) | 27, 537 dimensions |
| `dovetailed_sawhorse` | 0.74 s | 0.74 s | 3 |
| `my_cute_frame_drawing_test` | 0.65 s | — | 3 |

So the frame doesn't appear until every drawing is dimensioned, and the 27 are independent of each
other. `collect_drawings` (file merge, measurement resolution) is cheap: 0.25 s for 537 dimensions.

Picklability (for worker processes): a cut timber and a `Drawing` pickle in under a millisecond at
~10–20 KB; a `Frame` doesn't (`cannot pickle 'mappingproxy'`). Python 3.13 with the GIL on.

## The two wins, separately

1. **Show the frame first.** Drawings computed after the frame is on screen, filling in as each
   finishes. This is most of the felt difference (6.8 s → the frame's ~0.1 s), and needs drawings to
   be declared as work to do rather than done during the build.
2. **Run them in parallel.** Independent drawings in a process pool: roughly ×(cores) on top.

## Status (2026-11-03)

Built:

- **Jobs** in the runner (`Jobs` / `JobContext`, thread backend): job events, `cancel_job`, `list_jobs`,
  cancelled on slot reload. Assembly runs on it.
- **Deferred work in kumiki** (`kumiki/deferred.py`): `frame.with_deferred(routine)`, where
  `routine(deferred: Deferred)` calls `deferred.add_drawing(...)` and `deferred.progress(...)`. Every
  call raises `DeferredCancelled` once cancelled. `frame.run_deferred()` runs them now, for scripts
  and tests. `overlay_frames` keeps each frame's routines. `with_auto_drawings` and `cat_corner_cot`
  generate their drawings this way.
- **Runner:** `run_deferred` starts one `deferred` job per slot, asked for by the extension once the
  frame is shown. Each drawing replaces the slot's frame with one that has it, and is announced in a
  `job_progress` event (`drawing`, `drawingsAdded`). Protocol output keeps the real stdout and
  `sys.stdout` goes to stderr, so a job thread's prints can't swallow replies.
- **Extension:** `frame-view-session.js` asks for `run_deferred` after each refresh and fetches the
  drawings again (debounced) as each one arrives.
- **Tools:** `Frame.tools`, a list of `ToolAd(name, description, run)`; runner `list_tools` and
  `run_tool`.

Left:

1. **Viewer:** "drawings 12/27" with a cancel, and a mark on the drawings list while more are coming.
   Progress events already carry `done`, `total` and `label`.
2. **Tools UI:** nothing lists or runs the tools yet.
3. **Parallel drawings:** a process backend. A routine is one opaque function, so this needs a way to
   hand the runner separate picklable calls (e.g. `deferred.add_drawing_later(fn, *args)`).
4. **Agent build report:** say when deferred drawings are still being made.
5. **Undecided:** whether a routine that fails shows in the drawings list or only in the log (now:
   the log, with its traceback).
