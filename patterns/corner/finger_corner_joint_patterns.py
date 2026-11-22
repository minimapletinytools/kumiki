# Last checked on kumiki 0.9.8
"""Through box corner with adjustable finger count or width."""

from typing import Optional

from kumiki import (Joint, Kiwari, KUMIKI_PATTERN_FOLDERS, create_v2, cut_uniform_finger_corner_joint,
                    kiwari, mm, pattern, pattern_folders)
from kumiki.example_shavings import create_canonical_example_right_angle_corner_joint_timbers

__title__ = {"en": "Box corner", "ja": "あられ組み"}
pattern_folders(KUMIKI_PATTERN_FOLDERS)
BOX = kiwari(
    finger_count=kiwari.count(7, optional=True, minimum=2, about="Clear to use finger width"),
    finger_width=kiwari.length(optional=True, about="Measure inward from the front face"),
)


@pattern("corner/finger_corner_joint", name=__title__, kiwari=BOX)
def box_corner(k: Optional[Kiwari] = None) -> Joint:
    """Join two 18 mm boards with a through box corner."""
    k = BOX.resolve(k)
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(
        timber_size=create_v2(mm(84), mm(18)), timber_length=mm(115))
    return cut_uniform_finger_corner_joint(arrangement, finger_count=k.count("finger_count"),
                                           finger_width=k.length("finger_width"))
