"""Sticker, the debugging marker accessory."""

from kumiki import *
from kumiki.timber import Sticker


def test_a_sticker_has_a_shape():
    assert Sticker(transform=Transform.identity()).get_csg_local() is not None
