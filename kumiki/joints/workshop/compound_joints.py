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

  All timbers must share a common "stacking axis": a long-face axis (RIGHT/LEFT or
  FRONT/BACK) that is parallel across every timber in the list, regardless of how each
  timber is otherwise rotated about that axis. starting_face_on_first_timber names the
  face on timbers[0] at the "start" of that axis; the corresponding face on timbers[-1]
  (the one facing the same way as starting_face_on_first_timber) is the "finish" face,
  and its opposite is where the stack ends.

  cut_distance_ratios places the N-1 cut boundaries (one per pair of adjacent timbers)
  along that start-to-finish axis, as fractions of the total distance between the
  starting face and the finish face: 0.0 is at the starting face, 1.0 is at the finish
  face, and ratios must be strictly increasing. If fewer than N-1 ratios are given, the
  remaining boundaries are spaced uniformly between the last explicit ratio (or the
  starting face, if none were given) and the finish face.

  Each of these ratios is a *global* position along the stacking axis, not the local
  cut_ratio parameter of the underlying cut_plain_cross_lap_joint call (which is defined
  relative to the two faces of that specific pair, per its own 0=timber2-fully-cut /
  1=timber1-fully-cut convention). This function converts each global boundary position
  into the local cut_ratio needed to actually land the cut there, so the printed/passed
  cut_ratio for a given pair will generally differ from the global ratio that produced it.

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

    # TODO we're not done yet! boards that did not have joints cut between them may overlap so we need to make some additional cuts to fix the issue
    # here is the algorithm
    # iterate through all boards, starting from the first board and the first cut_ratio, call this board[n] and cut_ratio[n]
    # draw a half space below cut_ration[n], in this half space region, we want to remove the timber prism (intersected with the cut ratio plane) from all of boards [n+2:]
    # (rather than doing cut_ratio[n] half space intersected with the timber prism, just construct a new prism that is the timber prism cropped below the cut_ratio[n] plane, as this is more efficient)
    # next, go from the last board and the last cut ratio, and work backwards
    # this time, we will do the opposite for all boards [0:n-2], removing the timebr prism, this time cropping the timber prism above the cut_ratio[n] plane 

  return make_compound_joint(joints, ticket=JointTicket(joint_type="multi_cross_lap"))


# chatGPT translates this to Japanese as:
# 小根付き通しほぞの十字相欠き梁組
# kone-tsuki tōshi-hozo no jūji aigaki harigumi
def cut_cross_lap_beam_assembly_on_post_with_stepped_mortise_and_tenon(
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
