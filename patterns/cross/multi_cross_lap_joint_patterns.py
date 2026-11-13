# Last checked on kumiki 0.9.0
"""Multi-cross-lap joint examples."""

from kumiki import *
from kumiki.example_shavings import create_canonical_example_cross_joint_timbers


@pattern("cross/multi_cross_lap_joint")
def multi_cross_lap() -> Joint:
    arrangement = create_canonical_example_cross_joint_timbers()
    return cut_multi_cross_lap_joint_on_plane_aligned_timbers(
        [arrangement.timber1, arrangement.timber2], TimberFace.RIGHT)
