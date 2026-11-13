# Last checked on kumiki 0.9.0
"""
Free House Joint Patterns
"""

from kumiki import *


from kumiki.example_shavings import create_canonical_example_cross_joint_timbers


@pattern("free/free_house_joint")
def free_house_joint() -> Joint:
    """Cut a housing following a crossing timber's body."""
    arrangement = create_canonical_example_cross_joint_timbers(lateral_offset=inches(2))
    return cut_free_house_joint(arrangement.timber1, [arrangement.timber2])
