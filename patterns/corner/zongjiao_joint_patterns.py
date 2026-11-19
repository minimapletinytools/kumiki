# Last checked on kumiki 0.9.7
"""Fit a Zongjiao corner with two rails and a locking post."""

__title__ = {"en": "Rice dumpling joint", "ja": "粽角榫"}

from typing import Optional

from kumiki import (
    KUMIKI_PATTERN_FOLDERS, Joint, Kiwari, create_v2, cut_zongjiao_joint, inches, kiwari, pattern, pattern_folders,
)
from kumiki.example_shavings import create_canonical_example_tri_corner_timbers

pattern_folders(KUMIKI_PATTERN_FOLDERS)

LAYOUT = kiwari(
    cheek_thickness=kiwari.length(inches(0.5), minimum=inches(0.25), maximum=inches(0.75)),
    post_tenon_inset=kiwari.length(inches(1), minimum=inches(0.75), maximum=inches(1.25)),
    rail_tenon_inset=kiwari.length(inches(1.25), minimum=inches(0.25), maximum=inches(1.5)),
    tenon_width=kiwari.length(inches(1), minimum=inches(0.5), maximum=inches(1.25)),
    tenon_thickness=kiwari.length(inches(0.75), minimum=inches(0.5), maximum=inches(1)),
)


@pattern("corner/zongjiao_joint", name={"en": "Rice dumpling joint", "ja": "粽角榫"}, kiwari=LAYOUT)
def zongjiao_joint(k: Optional[Kiwari] = None) -> Joint:
    k = LAYOUT.resolve(k)
    return cut_zongjiao_joint(
        create_canonical_example_tri_corner_timbers(),
        timber1_miter_thickness=k.length("cheek_thickness"),
        timber_1_tenon_distance_from_outer_faces=k.length("post_tenon_inset"),
        timber_2_tenon_distance_from_outer_face=k.length("rail_tenon_inset"),
        tenon_size=create_v2(k.length("tenon_width"), k.length("tenon_thickness")),
    )
