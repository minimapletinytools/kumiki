"""Ticket system for hierarchical naming and metadata.

Tickets are immutable labels that can be attached to timbers, joints, accessories,
and feature concepts. The path field encodes hierarchy using '/' as a separator,
e.g. "posts/frontleft" or "door/boards/1". Folders are implicit in the path and
will be rendered as actual folders in the layer view.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from enum import Enum
from itertools import count
from typing import Dict, Iterable, NewType, Optional, Union

from typing_extensions import Self, deprecated

# The path a Ticket has when nobody gave it one. Code that displays a name
# needs to recognise it, since it is a placeholder rather than a name; it was
# a bare literal in eight places before this.
UNNAMED_TICKET_PATH = "[no-name]"

KumikiId = NewType("KumikiId", int)
"""Runtime-only identifier type for the Kumiki viewer. See Ticket.kumiki_id."""

_kumiki_id_COUNTER = count(1)


def _next_kumiki_id() -> KumikiId:
    return KumikiId(next(_kumiki_id_COUNTER))


class Member(str, Enum):
    """The structural role a timber plays in a frame.

    Roles form a tree (see _MEMBER_PARENT): a summer beam is a beam, and a beam
    is horizontal. A timber wears at most one of these; ask about the broader
    roles with is_a rather than tagging them as well.

    Closed on purpose: the drawing system will key default marking instructions
    off these names, and a role with no instructions of its own can fall back to
    its parent's. Adding a role is a line here and a line in _MEMBER_PARENT; a
    label that is not a structural role belongs in a GenericTag.
    """

    VERTICAL = "vertical"
    POST = "post"
    CORNER_POST = "corner_post"
    QUEEN_POST = "queen_post"
    KING_POST = "king_post"
    STUD = "stud"

    HORIZONTAL = "horizontal"
    SILL = "sill"
    MUDSILL = "mudsill"
    JOIST = "joist"
    RIM_JOIST = "rim_joist"
    FLOOR_JOIST = "floor_joist"
    GIRDER = "girder"
    BEAM = "beam"
    SUMMER_BEAM = "summer_beam"
    TIE_BEAM = "tie_beam"
    RIDGE_BEAM = "ridge_beam"
    PLATE = "plate"
    TOP_PLATE = "top_plate"
    COLLAR_TIE = "collar_tie"
    GIRT = "girt"
    PURLIN = "purlin"

    RAFTER = "rafter"
    PRINCIPAL_RAFTER = "principal_rafter"
    COMMON_RAFTER = "common_rafter"

    BRACE = "brace"
    KNEE_BRACE = "knee_brace"

    def is_a(self, other: Union["Member", str]) -> bool:
        """True if this role is *other* or a kind of it. POST.is_a(POST) is True."""
        target = Member(other)
        current: Optional["Member"] = self
        while current is not None:
            if current is target:
                return True
            current = _MEMBER_PARENT[current]
        return False


# The member tree: each role maps to the role it is a kind of, roots to None.
# The indentation is the hierarchy.
_MEMBER_PARENT: Dict[Member, Optional[Member]] = {
    Member.VERTICAL: None,
        Member.POST: Member.VERTICAL,
            Member.CORNER_POST: Member.POST,
            Member.QUEEN_POST: Member.POST,
            Member.KING_POST: Member.POST,
        Member.STUD: Member.VERTICAL,
    Member.HORIZONTAL: None,
        Member.SILL: Member.HORIZONTAL,
            Member.MUDSILL: Member.SILL,
        Member.JOIST: Member.HORIZONTAL,
            Member.RIM_JOIST: Member.JOIST,
            Member.FLOOR_JOIST: Member.JOIST,
        Member.GIRDER: Member.HORIZONTAL,
        Member.BEAM: Member.HORIZONTAL,
            Member.SUMMER_BEAM: Member.BEAM,
            Member.TIE_BEAM: Member.BEAM,
            Member.RIDGE_BEAM: Member.BEAM,
        Member.PLATE: Member.HORIZONTAL,
            Member.TOP_PLATE: Member.PLATE,
        Member.COLLAR_TIE: Member.HORIZONTAL,
        Member.GIRT: Member.HORIZONTAL,
        Member.PURLIN: Member.HORIZONTAL,
    Member.RAFTER: None,
        Member.PRINCIPAL_RAFTER: Member.RAFTER,
        Member.COMMON_RAFTER: Member.RAFTER,
    Member.BRACE: None,
        Member.KNEE_BRACE: Member.BRACE,
}


def _validate_member_tree() -> None:
    """A role missing from the tree would silently read as a root."""
    missing = sorted(member.value for member in Member if member not in _MEMBER_PARENT)
    assert not missing, f"Member roles missing from _MEMBER_PARENT: {missing}"
    for member in Member:
        seen = set()
        current: Optional[Member] = member
        while current is not None:
            assert current not in seen, f"Cycle in the member tree at '{current.value}'"
            seen.add(current)
            current = _MEMBER_PARENT[current]


_validate_member_tree()


@dataclass(frozen=True)
class TimberTag(ABC):
    """A label on a timber ticket.

    The kind is the concrete subclass. A tag carries nothing but its name;
    anything shared between timbers wearing the same tag is looked up by that
    name elsewhere.
    """

    name: str


@dataclass(frozen=True)
class GenericTag(TimberTag):
    """User-space label. Bare strings become these."""


@dataclass(frozen=True)
class SliceTag(TimberTag):
    """Names a slice section this timber belongs to."""


@dataclass(frozen=True)
class MemberTag(TimberTag):
    """Names this timber's structural role. The name must be a Member value."""

    def __post_init__(self) -> None:
        try:
            member = Member(self.name)
        except ValueError:
            allowed = ", ".join(m.value for m in Member)
            raise ValueError(
                f"MemberTag name must be one of the Member values, got {self.name!r}. "
                f"Allowed: {allowed}"
            ) from None
        # Member is a str enum, so store the plain value and keep MemberTag
        # equality the same whether it was built from Member.POST or "post".
        object.__setattr__(self, "name", member.value)

    @property
    def member(self) -> Member:
        return Member(self.name)

    def is_a(self, other: Union[Member, str]) -> bool:
        """True if this tag's role is *other* or a kind of it."""
        return self.member.is_a(other)


def as_timber_tag(value: Union[TimberTag, str]) -> TimberTag:
    """Convert a tag parameter to a TimberTag, a bare string becoming a GenericTag."""
    if isinstance(value, TimberTag):
        return value
    if isinstance(value, str):
        return GenericTag(value)
    raise TypeError(f"Expected a TimberTag or a str, got {type(value).__name__}")


def normalize_timber_tags(tags: Iterable[Union[TimberTag, str]]) -> tuple[TimberTag, ...]:
    """Coerce, strip, drop empty names, dedupe on (kind, name), and sort for a stable order."""
    normalized: list[TimberTag] = []
    seen: set[tuple[type, str]] = set()
    for tag in tags:
        coerced = as_timber_tag(tag)
        stripped = coerced.name.strip()
        if not stripped:
            continue
        if stripped != coerced.name:
            coerced = replace(coerced, name=stripped)
        key = (type(coerced), coerced.name)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(coerced)
    normalized.sort(key=lambda tag: (type(tag).__name__, tag.name))

    # A timber is one member. Two roles at once would leave the drawing system
    # with two sets of default marking instructions and no way to choose; a
    # broader role is a question for Member.is_a, not a second tag.
    members = [tag.name for tag in normalized if isinstance(tag, MemberTag)]
    if len(members) > 1:
        raise ValueError(f"A timber has one member role, got {members}")

    return tuple(normalized)


@dataclass(frozen=True)
class Ticket(ABC):
    """Base ticket shared by all ticket categories.

    The category is represented by the concrete subclass rather than an enum field.

    path: hierarchical identifier using '/' as separator.
          e.g. "posts/frontleft", "door/boards/1"
          The last segment is the display name; preceding segments are folder names.
    """

    path: str = UNNAMED_TICKET_PATH
    # Runtime-only identifier for the Kumiki viewer. It has no meaning outside
    # the viewer runtime and should not be used as persistent data.
    kumiki_id: KumikiId = field(
        default_factory=_next_kumiki_id, init=False, compare=False, repr=False
    )

    def get_name(self) -> str:
        """Return the display name: the last segment of the path."""
        return self.path.rsplit("/", 1)[-1]

@dataclass(frozen=True)
class TimberTicket(Ticket):
    """Ticket metadata for physical timber members."""

    material: Optional[str] = None

    # TODO consider replacing with a list of reference long features taken in order of priority, with the first one being the main one that gets rendered as a red line?
    reference_faces: Optional[tuple[str, ...]] = None


    # Strings are coerced to GenericTag, the same way Timber's factories take
    # either a TimberTicket or a bare name.
    tags: tuple[TimberTag, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", normalize_timber_tags(self.tags))

    def with_tags(self, *tags: Union[TimberTag, str]) -> Self:
        """Return a copy of this ticket carrying these tags as well as its own."""
        return self._replace_tags((*self.tags, *tags))

    def with_member(self, member: Union[Member, str]) -> Self:
        """Return a copy in this member role, replacing whatever role it had.

        with_tags cannot do this: a second role is an error, not an addition.
        """
        kept = tuple(tag for tag in self.tags if not isinstance(tag, MemberTag))
        return self._replace_tags((*kept, MemberTag(member)))

    def _replace_tags(self, tags: Iterable[Union[TimberTag, str]]) -> Self:
        updated = replace(self, tags=tuple(tags))
        # replace() re-runs __init__, which mints a fresh kumiki_id. The viewer
        # identifies a member by that id, so the original has to come across.
        object.__setattr__(updated, "kumiki_id", self.kumiki_id)
        return updated


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
