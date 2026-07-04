"""Ticket system for hierarchical naming and metadata.

Tickets are immutable labels that can be attached to timbers, joints, accessories,
and feature concepts. The path field encodes hierarchy using '/' as a separator,
e.g. "posts/frontleft" or "door/boards/1". Folders are implicit in the path and
will be rendered as actual folders in the layer view.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from itertools import count
from typing import Optional


_KUMIKI_ID_COUNTER = count(1)


def _next_kumiki_id() -> int:
    return next(_KUMIKI_ID_COUNTER)


@dataclass(frozen=True)
class Ticket(ABC):
    """Base ticket shared by all ticket categories.

    The category is represented by the concrete subclass rather than an enum field.

    path: hierarchical identifier using '/' as separator.
          e.g. "posts/frontleft", "door/boards/1"
          The last segment is the display name; preceding segments are folder names.
    """

    path: str = "[no-name]"
    # Runtime-only identifier for the Kumiki viewer. It has no meaning outside
    # the viewer runtime and should not be used as persistent data.
    kumiki_id: int = field(default_factory=_next_kumiki_id, init=False, compare=False, repr=False)

    def get_name(self) -> str:
        """Return the display name: the last segment of the path."""
        return self.path.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class TimberTicket(Ticket):
    """Ticket metadata for physical timber members."""

    material: Optional[str] = None
    reference_faces: Optional[tuple[str, ...]] = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class AccessoryTicket(Ticket):
    """Ticket metadata for accessories (pegs, wedges, hardware, etc.)."""


@dataclass(frozen=True)
class BoardTicket(TimberTicket):
    """Ticket metadata for board-like members."""

@dataclass(frozen=True)
class JointTicket(Ticket):
    """Concept ticket metadata for joints."""

    joint_type: Optional[str] = None
    tags: tuple[str, ...] = ()
