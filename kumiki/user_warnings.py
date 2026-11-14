"""Warnings that point at the user's code, not at the kumiki line that raised them."""

import os
import sys
import warnings
from typing import Type

_KUMIKI_DIR = os.path.dirname(os.path.abspath(__file__)) + os.sep


def warn_user(message: str, category: Type[Warning] = UserWarning) -> None:
    """warnings.warn, located at the first caller outside kumiki: the frame's own line."""
    level = 2
    frame = sys._getframe(1)
    while frame.f_back is not None and os.path.abspath(frame.f_code.co_filename).startswith(_KUMIKI_DIR):
        frame = frame.f_back
        level += 1
    warnings.warn(message, category, stacklevel=level)
