# Last checked on kumiki 0.9.8
"""End-to-end finger splice with adjustable pitch, overlap and taper."""

from dataclasses import replace
from typing import Optional

from kumiki import (Joint, Kiwari, KUMIKI_PATTERN_FOLDERS, TimberLongFace, atan, create_v2, cut_finger_splice_joint,
                    kiwari, mm, pattern, pattern_folders, scalar)
from kumiki.example_shavings import create_canonical_example_splice_joint_timbers

__title__ = {"en": "Finger splice", "ja": "フィンガージョイント"}
pattern_folders(KUMIKI_PATTERN_FOLDERS)
SPLICE = kiwari(finger_count=kiwari.count(7, minimum=2), finger_length=kiwari.length(mm(36), minimum=mm(1)),
                taper_angle=kiwari.angle(atan(scalar(1, 8))))


@pattern("splice/finger_splice_joint", name=__title__, kiwari=SPLICE)
def finger_splice(k: Optional[Kiwari] = None) -> Joint:
    """Splice two boards with fingers laid out across their broad face."""
    k = SPLICE.resolve(k)
    arrangement = create_canonical_example_splice_joint_timbers(timber_size=create_v2(mm(18), mm(84)),
                                                               timber_length=mm(100))
    return cut_finger_splice_joint(replace(arrangement, front_face_on_timber1=TimberLongFace.FRONT),
                                   finger_length=k.length("finger_length"), finger_count=k.count("finger_count"),
                                   taper_angle=k.angle("taper_angle"))
