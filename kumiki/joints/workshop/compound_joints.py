"""
Kumiki - Compound joint construction functions
Contains functions for creating complex joints that combine multiple joint types.
"""

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from kumiki.measuring import get_center_point_on_face_global
from .cross_joints import cut_plain_cross_lap_joint
from .shavings import *

_LONG_FACES = (TimberFace.RIGHT, TimberFace.FRONT, TimberFace.LEFT, TimberFace.BACK)


# TODO replace with get_closest_oriented_face_from_global_direction
def _find_long_face_aligned_with_direction(timber: TimberLike, direction: Direction3D) -> TimberLongFace:
    """Find the long face on timber whose outward normal is (anti)parallel to direction, preferring the
    one pointing the same way. Asserts that such a face actually exists (within tolerance)."""
    best_face: Optional[TimberFace] = None
    best_dot = None
    for face in _LONG_FACES:
        dot = safe_dot_product(timber.get_face_direction_global(face), direction)
        if best_dot is None or dot > best_dot:
            best_dot = dot
            best_face = face
    assert best_face is not None and are_vectors_parallel(timber.get_face_direction_global(best_face), direction), \
        f"timber '{timber.ticket.path}' has no long face axis parallel to the starting face"
    return best_face.to.long_face()


def cut_multi_cross_lap_joint(timbers : List[TimberLike], starting_face_on_first_timber : TimberFace, cut_distance_ratios : List[Numeric] = []) -> Joint:
  """
  Weave a chain of N timbers together with N-1 cross-lap joints, cut in order between
  timbers[n] and timbers[n+1].

  All timbers must share a common "stacking axis": a long-face axis that is parallel across every timber in the list. starting_face_on_first_timber names one of these faces on timbers[0] called the "starting" face and the opposing face on timbers[-1] is called the "finish" face.

  cut_distance_ratios places the N-1 cut boundaries (one per pair of adjacent timbers)
  along that start-to-finish axis, as fractions of the total distance between the
  starting face and the finish face: 0.0 is at the starting face, 1.0 is at the finish
  face, and ratios must be strictly increasing. If fewer than N-1 ratios are given, the
  remaining boundaries are spaced uniformly between the last explicit ratio (or the
  starting face, if none were given) and the finish face.

  Each of these ratios is relative to the starting and finish face, NOT the local
  cut_ratio parameter of the underlying cut_plain_cross_lap_joint call. 

  Args:
      timbers: Ordered chain of at least 2 timbers to weave together.
      starting_face_on_first_timber: The long face on timbers[0] marking the start of
          the shared stacking axis (e.g. the global-bottom face shared by all timbers).
      cut_distance_ratios: Strictly increasing global position ratios in (0, 1) for the
          first len(cut_distance_ratios) boundaries; any remaining boundaries are filled
          in uniformly up to the finish face.
  """
  assert len(timbers) >= 2, "cut_multi_cross_lap_joint requires at least 2 timbers"
  assert starting_face_on_first_timber in _LONG_FACES, \
      f"starting_face_on_first_timber must be a long face (RIGHT/FRONT/LEFT/BACK), got {starting_face_on_first_timber}"

  # global direction pointing from the starting face towards the finish face: the
  # starting face's own outward normal points away from the timber stack, so the
  # start-to-finish direction is the opposite of it.
  axis_direction = -safe_normalize_vector(timbers[0].get_face_direction_global(starting_face_on_first_timber))

  for ratio in cut_distance_ratios:
      assert 0 < ratio < 1, f"cut_distance_ratios must all be in (0, 1), got {ratio}"
  for prev_ratio, next_ratio in zip(cut_distance_ratios, cut_distance_ratios[1:]):
      assert prev_ratio < next_ratio, f"cut_distance_ratios must be monotonically increasing, got {cut_distance_ratios}"

  # for each timber, the long face pointing towards the finish direction and the one pointing towards the start
  finish_facing_faces = [_find_long_face_aligned_with_direction(timber, axis_direction) for timber in timbers]
  start_facing_faces = [face.to.face().get_opposite_face().to.long_face() for face in finish_facing_faces]

  starting_face_position = get_center_point_on_face_global(starting_face_on_first_timber, timbers[0])
  finish_face_position = get_center_point_on_face_global(finish_facing_faces[-1], timbers[-1])

  start_coord = safe_dot_product(starting_face_position, axis_direction)
  finish_coord = safe_dot_product(finish_face_position, axis_direction)

  num_boundaries = len(timbers) - 1
  assert len(cut_distance_ratios) <= num_boundaries, \
      f"got {len(cut_distance_ratios)} cut_distance_ratios but only {num_boundaries} boundaries between {len(timbers)} timbers"

  cut_position_coords: List[Numeric] = [
      start_coord + ratio * (finish_coord - start_coord) for ratio in cut_distance_ratios
  ]

  # uniformly fill in any remaining cut positions between the last computed one (or the starting
  # face if none were computed yet) and the finish face
  remaining = num_boundaries - len(cut_position_coords)
  last_coord = cut_position_coords[-1] if cut_position_coords else start_coord
  for i in range(1, remaining + 1):
      t = scalar(i, remaining + 1)
      cut_position_coords.append(last_coord + t * (finish_coord - last_coord))

  joints = []
  for n in range(num_boundaries):
      timber1 = timbers[n]
      timber2 = timbers[n + 1]
      front_face_on_timber1 = finish_facing_faces[n]

      face1_position = get_center_point_on_face_global(front_face_on_timber1, timber1)
      face2_position = get_center_point_on_face_global(start_facing_faces[n + 1], timber2)
      coord1 = safe_dot_product(face1_position, axis_direction)
      coord2 = safe_dot_product(face2_position, axis_direction)

      cut_ratio = (cut_position_coords[n] - coord1) / (coord2 - coord1)

      joints.append(cut_plain_cross_lap_joint(
          CrossJointTimberArrangement(
              timber1=timber1,
              timber2=timber2,
              front_face_on_timber1=front_face_on_timber1,
          ),
          cut_ratio=cut_ratio,
      ))

  from kumiki.cutcsg import adopt_csg, Difference, HalfSpace as _HalfSpace

  # --- Fill-in cuts for non-adjacent board pairs ---
  # Boards that share no direct cross-lap joint can still collide outside their
  # pairwise intersection region (where neither joint trimmed them).
  # We fix this by adding extra cuts for every non-adjacent pair (timbers[n], timbers[n+k], k>=2).
  #
  # Forward pass: timbers[n] "owns" the start-side below cut_coord[n].
  # Boards further up the stack (timbers[n+2:]) must not intrude there.
  for n in range(num_boundaries):
      source = timbers[n]
      cut_coord = cut_position_coords[n]
      R = source.transform.orientation.matrix
      t_dot_axis = safe_dot_product(source.transform.position, axis_direction)
      # axis_direction expressed in source's local coordinate frame
      local_axis = safe_transform_vector(R.T, axis_direction)
      # Prism of source cropped to start-side: Difference(prism, above-cut-half-space)
      above_hs = _HalfSpace(normal=local_axis, offset=cut_coord - t_dot_axis)
      source_prism_below = Difference(source.get_actual_csg_local(), [above_hs])
      for target_idx in range(n + 2, len(timbers)):
          target = timbers[target_idx]
          neg_csg = adopt_csg(source.transform, target.transform, source_prism_below)
          joints.append(Joint(
              cuttings={f"fill_fwd_{n}_{target_idx}": Cutting(timber=target, negative_csg=neg_csg)},
              ticket=JointTicket(joint_type="multi_cross_lap_fill"),
              jointAccessories={},
          ))

  # Backward pass: timbers[n+1] "owns" the finish-side above cut_coord[n].
  # Boards further down the stack (timbers[0:n]) must not intrude there.
  for n in range(num_boundaries):
      source = timbers[n + 1]
      cut_coord = cut_position_coords[n]
      R = source.transform.orientation.matrix
      t_dot_axis = safe_dot_product(source.transform.position, axis_direction)
      local_axis = safe_transform_vector(R.T, axis_direction)
      # Prism of source cropped to finish-side: Difference(prism, below-cut-half-space)
      below_hs = _HalfSpace(normal=-local_axis, offset=t_dot_axis - cut_coord)
      source_prism_above = Difference(source.get_actual_csg_local(), [below_hs])
      for target_idx in range(0, n):
          target = timbers[target_idx]
          neg_csg = adopt_csg(source.transform, target.transform, source_prism_above)
          joints.append(Joint(
              cuttings={f"fill_bwd_{n}_{target_idx}": Cutting(timber=target, negative_csg=neg_csg)},
              ticket=JointTicket(joint_type="multi_cross_lap_fill"),
              jointAccessories={},
          ))

  return make_compound_joint(joints, ticket=JointTicket(joint_type="multi_cross_lap"))


# chatGPT translates this to Japanese as:
# 小根付き通しほぞの十字相欠き梁組
# kone-tsuki tōshi-hozo no jūji aigaki harigumi
def cut_cross_lap_beam_assembly_on_post_with_stepped_mortise_and_tenon(T
        # arrangement.cross_timber_1 is always assumed to be the "bottom" in the cross lap joint
        arrangement: CrossCapJointTimberArrangement,

        # the size of the tenon as it passes through cross_timber_1 measured relative to post_timber
        tenon_size_in_cross_timber_1: V2,
        # the size of the tenon as it passes through cross_timber_2 measured relative to post_timber, must be smaller than tenon_size_in_cross_timber_1
        tenon_size_in_cross_timber_2: V2,

        # length of the tenon, stops exactly at the face of cross_timber_2 if None
        tenon_length: Optional[Numeric] = None,
        # depth of the mortise through both cross timbers mesaured from the face of cross_timber_1, through mortise if None
        mortise_depth: Optional[Numeric] = None,

        # location of the cross lap cut measured from the bottom of cross_timber_2, 0 means the cut is at the bottom of cross_timber_2 (relative to the joint)
        cross_lap_cut_ratio: Numeric = scalar(1, 2),
        ):
    raise NotImplementedError("cross lap beam assembly on post with stepped mortise and tenon not implemented yet")
