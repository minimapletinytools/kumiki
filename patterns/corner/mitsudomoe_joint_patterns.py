# Last checked on kumiki 0.9.7
"""Fit three cyclic tenons around a mitered outside corner."""

__title__ = {"en": "Mitsudomoe joint", "ja": "三つ巴の仕口"}

from typing import Optional

from kumiki import KUMIKI_PATTERN_FOLDERS, Joint, Kiwari, cut_mitsudomoe_joint, inches, kiwari, pattern, pattern_folders
from kumiki.example_shavings import create_canonical_example_tri_corner_timbers


pattern_folders(KUMIKI_PATTERN_FOLDERS)

TENONS = kiwari(
    position_from_outer_face=kiwari.length(inches(1), minimum=inches(0.5), maximum=inches(1.25),
                                          about="Inset from the shared outside face to the tenon"),
    position_from_outer_edge=kiwari.length(optional=True, minimum=inches(3.5), maximum=inches(4),
                                          about="Along the receiver from the corner to the far edge of the tenon"),
    width=kiwari.length(inches(1), minimum=inches(0.5), maximum=inches(1.25)),
    height=kiwari.length(inches(1), minimum=inches(0.5), maximum=inches(1)),
    length=kiwari.length(inches(1), minimum=inches(0.5), maximum=inches(1.5)),
    mortise_extra_depth=kiwari.length(inches(1, 8), minimum=0, maximum=inches(0.5)),
)


@pattern("corner/mitsudomoe_joint", name={"en": "Mitsudomoe joint", "ja": "三つ巴の仕口"}, kiwari=TENONS)
def mitsudomoe_joint(k: Optional[Kiwari] = None) -> Joint:
    k = TENONS.resolve(k)
    return cut_mitsudomoe_joint(
        create_canonical_example_tri_corner_timbers(),
        tenon_position_from_outer_face=k.length("position_from_outer_face"),
        tenon_position_from_outer_edge=k.length("position_from_outer_edge"),
        tenon_width=k.length("width"), tenon_height=k.length("height"),
        tenon_length=k.length("length"), mortise_extra_depth=k.length("mortise_extra_depth"),
    )
