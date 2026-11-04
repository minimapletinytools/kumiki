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

## Proposal

### A. kumiki: drawings declared, not done, during the build

A frame says which drawings it has and how to make each, without making them:

```python
@frame
def cat_corner_cot(k) -> Frame:
    frame = Frame.from_joints(...)
    return frame.with_drawings([
        DrawingRecipe(_plan_drawing, cut_timbers, fixed_path, f"{name} plan (generated)"),
        *(DrawingRecipe(_piece_drawing, group) for group in match_timbers(cut_timbers)),
    ])
```

- `DrawingRecipe(fn, *args)`: a module-level function and picklable arguments (cut timbers and
  groups pickle). `frame.drawings` stays a list of `Drawing`; recipes are a separate field, so
  existing frames that build drawings eagerly keep working unchanged.
- `Frame.realize_drawings()` (sequential) for anything outside kigumi: scripts, tests, export.
- The examples that generate drawings (`cat_corner_cot`, `dovetailed_sawhorse`,
  `my_cute_frame_drawing_test`, the auto-drawing helpers in `kumiki.drawings.auto_drawings`) move to
  recipes.

### B. Runner: one job mechanism

```
jobs.start(kind, slot, fn, args, backend="thread"|"process") -> job id
```

- **Context for the work:** `should_cancel()`, `progress(done, total, label)`; assembly's solver
  already takes `should_cancel`.
- **Backends:** `thread` (runs against the live frame; assembly, which needs the unpicklable frame)
  and `process` (a persistent `ProcessPoolExecutor`, spawn start method, warm after the first use;
  arguments and results are pickled). Drawings use `process`, one task per recipe.
- **Tied to a slot generation:** reloading a slot cancels its jobs — queued tasks are cancelled
  outright, running ones are told to stop (threads) or their results dropped (processes) — and a
  result for an older generation is never delivered.
- **Events** (protocol, replacing `assembly_result`): `job_started {jobId, kind, slot, total}`,
  `job_progress {jobId, done, total, label}`, `job_result {jobId, result}`,
  `job_failed {jobId, error}`, `job_cancelled {jobId}`. Each carries timing: queued, started,
  finished, worker.
- **Commands:** `cancel_job {jobId}`, `list_jobs`.
- **Drawings:** after `reload_example` answers (frame shown), the runner starts one `drawings` job
  of N tasks; each finished `Drawing` is added to the slot and `collect_drawings` re-sent, so the
  drawings list fills in. Measurements in the drawings file attach as each arrives.

### C. Extension and viewer

- `runner-session.js`: one `onJobEvent`, replacing `onAssemblyResult`; `frame-view-session.js` routes
  by kind (assembly → the timeline, drawings → the scenes).
- The viewer shows jobs in flight ("drawings 12/27") with a cancel; the drawings list marks the ones
  still coming.
- Timing goes to the session log and the refresh profiler, so a slow drawing is named.
- The agent's build report says when drawings are still generating, rather than reporting a frame
  with none.

## Order

1. Job mechanism in the runner with the `thread` backend; move assembly onto it (no behaviour
   change), with `onJobEvent` on the extension side.
2. `DrawingRecipe` in kumiki, and drawings as a `thread` job: the frame shows first.
3. The `process` backend; drawings move to it: parallel.
4. Progress and cancel in the viewer; timing in the log and the build report.

## Decisions

- Drawings declared as recipes (A) — a kumiki API addition; eager drawings keep working.
- Processes for parallel drawings (spawn pool, pickled cut timbers) vs. staying on threads (no
  speedup, only frame-first). Free-threaded Python (3.13t/3.14) would let threads run in parallel
  later, but numpy/sympy wheels for it are not something to depend on yet.
- Whether a drawing that fails shows as a failed entry in the drawings list, or only in the log.
