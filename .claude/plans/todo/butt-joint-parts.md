<!-- 🤖🤖🤖🤖🤖🤖 -->
# Butt joints built from parts (2026-11-13)

Status: investigated, not started.

Build every butt joint from a shoulder and a list of pieces (tenons, slots, pegs, reliefs), each
returning `ButtJointCSGParts`, combined by one shared step into the joint's `Cutting`s. Today each joint
assembles the same few things by hand, in its own way.

`ButtJointCSGParts` (`shavings/build_a_butt.py`, added 2026-03-27) and `build_dovetail_shoulder_geometery`
(2026-04) were meant for this and are used nowhere yet.

## What every butt joint does

1. A shoulder: a plane, or a shaped region, past which the butt timber's end is cut away.
2. What the shoulder keeps: a tenon, tongue, dovetail or housing profile, or stubby tenons. The waste is
   "past the shoulder" minus these.
3. What's cut from the receiving timber: the mortise, socket, slot or fork.
4. Relief: scribing (`apply_scribe_relief_if_configured`), or a shoulder notch
   (`ShoulderReliefCSGGeometry`, a cut on each timber).
5. The `Cutting`s: an end cut at the furthest kept part, labels, assembly freedom.

## Where it repeats

- The shoulder is found three ways: `compute_butt_joint_shoulder` (mortise and tenon, wedged half
  dovetail); `locate_mortise_timber_shoulder_plane_from_…` called directly (tongue and fork, splined
  opposing double butt); the joint's own maths (plain butt, drop-in housed, drop-in dovetail).
- The "past the shoulder" waste, `HalfSpace(normal=-shoulder_plane.normal, …)`, is written five times
  (mortise and tenon, tongue and fork butt twice, tongue and fork corner, splined); `dovetail_tenon_geometry`
  builds its own.
- `maybe_top_end_cut_distance_from_bottom=x if end == TimberEnd.TOP else None, maybe_bottom_…` is written
  26 times in 15 joint files, splice and corner joints included.
- `_union_into_cut` is copied in `mixed/mortise_and_tenon_joints.py` and `butt/wedged_half_dovetail_joint.py`.
- `cut_dropin_housed_butt_joint_on_face_aligned_timbers` and `cut_dropin_dovetail_butt_joint_on_face_aligned_timbers`
  are nearly the same function: shoulder, profile on a face, end prism, notch, socket. Only the profile differs.
- `ShoulderReliefCSGGeometry` is `ButtJointCSGParts` with only the two negative fields.

## The semantics to settle first

`ButtJointCSGParts` says "union the positive parts, then difference the negative parts". The butt timber
needs three roles, not two:

- the shoulder's waste, past the shoulder;
- what the shoulder keeps (tenons), which only the shoulder's waste spares;
- cuts that go through everything, kept parts included (peg holes, spline slots).

Today's joints do `(shoulder waste − kept parts) ∪ other cuts`. So either the parts get a shoulder field,
or "positive" is defined as "kept from the shoulder's waste only". The receiving timber has no positive
parts anywhere (nothing adds material to it), so that field can probably go.

## Steps, smallest risk first

1. Helpers. An end-cut helper, or a `Cutting` factory taking the end and its distance, for the 26 copies;
   one shared `_union_into_cut`. Mechanical; helps splice and corner joints too.
2. One shoulder function: the plane and its "past the shoulder" waste, for every butt joint. Retire the
   hand-rolled copies.
3. `ButtJointCSGParts`: settle the semantics above, fold `ShoulderReliefCSGGeometry` into it, and write the
   step that turns parts into `Cutting`s, its end cut at the furthest kept part.
4. Move the joints over one at a time, the existing tests guarding each:
   - the two drop-ins, into one function and two profiles;
   - tongue and fork (butt, and the corner one);
   - splined opposing double butt, its stubby tenons becoming a tenon piece;
   - wedged half dovetail, through `dovetail_tenon_geometry`;
   - mortise and tenon last, having the most options (round, wedges, pegs, tusks, bored mortises, reliefs).
5. `build_dovetail_shoulder_geometery`: give it a joint, or delete it.

## Related

- [Several tenons on one timber end](../archive/multi-mortise-and-tenon.md) uses one shoulder cut that spares every tenon.
