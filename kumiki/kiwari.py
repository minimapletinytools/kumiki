"""Kiwari -- the numbers a frame is built from, and what they are allowed to be.

*Kiwari* (木割) is the traditional system that sets every member's dimension
from a small set of base numbers. That is what this is: a frame declares the
handful of numbers it is proportioned from, and kigumi puts a control on each.

A builder declares its kiwari in its own body and hands it back on the frame::

    def build_frame(k: Kiwari | None = None) -> Frame:
        k = kiwari(
            legs=count(4, minimum=3, about="Number of legs"),
            seat_height=length(mm(450)),
            butt_end=choice(TimberEnd, TimberEnd.TOP),
        ).resolve(k)

        for i in range(k.count("legs")):
            ...
        return Frame.from_joints(joints, kiwari=k)

Nothing here is global and nothing is mutated: `kiwari(...)` makes a
declaration whose values are its defaults, `resolve` returns a new one with
incoming values laid over the top, and `Frame` carries the result. Calling
`build_frame()` bare gets the defaults, which is what a script or a test wants.

Declaring and binding are one type on purpose. Values are never useful without
the declarations -- you cannot validate, coerce, or fall back to a default
without them -- so splitting them would mean every caller carried both and
something had to check they agreed. Here there is only ever one schema in the
room, and an accessor asking for the wrong thing says so at the call site::

    k.length("legs")   # TypeError: 'legs' is a count, not a length

Reading a value back out is typed, because a length and a count are both
floats once they are numbers, and the declaration is the only thing that knows
which one a key is.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple, Union

from .rule import (
    V2,
    V3,
    create_v2,
    create_v3,
    format_angle,
    format_length,
    parse_angle,
    parse_length,
    scalar,
)

__all__ = [
    "Kiwari",
    "Declaration",
    "kiwari",
    "length",
    "angle",
    "count",
    "number",
    "flag",
    "text",
    "choice",
    "point2",
    "point3",
]


# What a parameter is. The kind decides how it is written down, how text is
# read back into it, and which accessor is allowed to ask for it.
LENGTH = "length"
ANGLE = "angle"
COUNT = "count"
NUMBER = "number"
FLAG = "flag"
TEXT = "text"
CHOICE = "choice"
POINT2 = "point2"
POINT3 = "point3"

_KINDS = (LENGTH, ANGLE, COUNT, NUMBER, FLAG, TEXT, CHOICE, POINT2, POINT3)

# The kinds whose value is a measurement, and so can be written as text.
_MEASURED = {LENGTH: (parse_length, format_length), ANGLE: (parse_angle, format_angle)}

# The kinds whose value is several measurements at once.
_VECTOR_AXES = {POINT2: ("x", "y"), POINT3: ("x", "y", "z")}


@dataclass(frozen=True)
class Declaration:
    """One parameter: what it is, what it defaults to, and what it may be."""

    kind: str
    default: Any
    about: str = ""
    optional: bool = False
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    choices: Optional[type] = None

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValueError(f"{self.kind!r} is not a kind of parameter. Expected one of {_KINDS}")
        if self.kind == CHOICE:
            if self.choices is None or not (isinstance(self.choices, type) and issubclass(self.choices, Enum)):
                raise ValueError("a choice must name the Enum class its options come from")
        if self.default is None and not self.optional:
            raise ValueError(
                "a parameter with no default has nothing to build with. "
                "Pass optional=True if it is genuinely allowed to be nothing."
            )


# ---------------------------------------------------------------------------
# Declaring
# ---------------------------------------------------------------------------


def length(default, *, about: str = "", minimum=None, maximum=None, optional: bool = False) -> Declaration:
    """A distance, in metres. Written and read as "450mm", "18in", "1 1/4"."""
    return Declaration(LENGTH, default, about, optional, minimum, maximum)


def angle(default, *, about: str = "", minimum=None, maximum=None, optional: bool = False) -> Declaration:
    """An angle, in radians. Written and read as "30deg", "1.5rad"."""
    return Declaration(ANGLE, default, about, optional, minimum, maximum)


def count(default, *, about: str = "", minimum=None, maximum=None, optional: bool = False) -> Declaration:
    """A whole number of things -- legs, bays, pegs."""
    return Declaration(COUNT, default, about, optional, minimum, maximum)


def number(default, *, about: str = "", minimum=None, maximum=None, optional: bool = False) -> Declaration:
    """A plain number with no dimension -- a ratio, a factor."""
    return Declaration(NUMBER, default, about, optional, minimum, maximum)


def flag(default: bool, *, about: str = "", optional: bool = False) -> Declaration:
    """On or off."""
    return Declaration(FLAG, default, about, optional)


def text(default: str, *, about: str = "", optional: bool = False) -> Declaration:
    """Free text -- a name, a label."""
    return Declaration(TEXT, default, about, optional)


def choice(choices: type, default=None, *, about: str = "", optional: bool = False) -> Declaration:
    """One of an Enum's members. Defaults to the first one declared."""
    if not (isinstance(choices, type) and issubclass(choices, Enum)):
        raise ValueError("a choice must name the Enum class its options come from")
    if default is None and not optional:
        default = next(iter(choices))
    return Declaration(CHOICE, default, about, optional, choices=choices)


def point2(default, *, about: str = "", optional: bool = False) -> Declaration:
    """Two lengths -- a cross section, a point on a face."""
    return Declaration(POINT2, default, about, optional)


def point3(default, *, about: str = "", optional: bool = False) -> Declaration:
    """Three lengths -- a position, an offset."""
    return Declaration(POINT3, default, about, optional)


# ---------------------------------------------------------------------------
# Reading text into a value
# ---------------------------------------------------------------------------


def _coerce(key: str, declaration: Declaration, value: Any) -> Any:
    """Turn whatever arrived into the value this declaration says it is."""
    kind = declaration.kind

    if value is None:
        if not declaration.optional:
            raise ValueError(f"{key!r} is not allowed to be nothing")
        return None

    if kind == FLAG:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
        raise ValueError(f"{key!r} is on or off, and {value!r} is neither")

    if kind == TEXT:
        return str(value)

    if kind == CHOICE:
        options = declaration.choices
        if isinstance(value, options):
            return value
        wanted = str(getattr(value, "name", value))
        for option in options:
            if option.name == wanted or str(option.value) == wanted:
                return option
        names = [option.name for option in options]
        raise ValueError(f"{key!r} must be one of {names}, and {wanted!r} is not")

    if kind in _VECTOR_AXES:
        axes = _VECTOR_AXES[kind]
        parts = _vector_parts(key, value, axes)
        numbers = [_coerce_measurement(f"{key}.{axis}", LENGTH, part) for axis, part in zip(axes, parts)]
        return create_v2(*numbers) if kind == POINT2 else create_v3(*numbers)

    coerced = _coerce_measurement(key, kind, value)
    if kind == COUNT:
        whole = round(coerced)
        if abs(coerced - whole) > 1e-9:
            raise ValueError(f"{key!r} counts things, so it has to be a whole number, not {value!r}")
        coerced = int(whole)
    _check_bounds(key, declaration, coerced)
    return coerced


def _coerce_measurement(key: str, kind: str, value: Any) -> float:
    """A number, or text read as one in whatever this kind measures."""
    if isinstance(value, bool):
        raise ValueError(f"{key!r} is a number, and on/off is not one")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        if kind in _MEASURED:
            parse, _ = _MEASURED[kind]
            return parse(value)
        try:
            return float(scalar(value))
        except Exception as exc:
            raise ValueError(f"{key!r} is a number, and {value!r} does not read as one") from exc
    raise ValueError(f"{key!r} is a number, and {value!r} does not read as one")


def _vector_parts(key: str, value: Any, axes: Tuple[str, ...]):
    if isinstance(value, Mapping):
        missing = [axis for axis in axes if axis not in value]
        if missing:
            raise ValueError(f"{key!r} is missing {', '.join(missing)}")
        return [value[axis] for axis in axes]
    shape = getattr(value, "shape", None)
    if shape in ((len(axes), 1), (1, len(axes))):
        return [value[index] for index in range(len(axes))]
    if isinstance(value, (list, tuple)) and len(value) == len(axes):
        return list(value)
    raise ValueError(f"{key!r} needs {len(axes)} numbers ({', '.join(axes)}), and {value!r} is not that")


def _check_bounds(key: str, declaration: Declaration, value) -> None:
    if declaration.minimum is not None and value < declaration.minimum:
        raise ValueError(f"{key!r} must be at least {declaration.minimum}, and {value} is not")
    if declaration.maximum is not None and value > declaration.maximum:
        raise ValueError(f"{key!r} must be at most {declaration.maximum}, and {value} is not")


# ---------------------------------------------------------------------------
# The kiwari itself
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Kiwari:
    """What a frame is proportioned from: the declarations and their values.

    Made by :func:`kiwari`. A bare one's values are its defaults; `resolve`
    returns a new one with incoming values laid over the top. Both halves are
    one type so an accessor always has the declaration to check itself against.
    """

    declarations: Mapping[str, Declaration]
    values: Mapping[str, Any] = field(default_factory=dict)
    # What the numbers were typed as, where anyone typed them. Kept so a value
    # written "1 1/4"" comes back that way rather than as 32mm -- writing a
    # length back out is lossy in inches, so the text is the better record.
    texts: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Frozen stops the attributes being rebound, not the dicts behind them
        # being written to. A kiwari that quietly changed under a frame that
        # had already been built from it would be the worst kind of bug here.
        for name in ("declarations", "values", "texts"):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))

    # -- reading ----------------------------------------------------------

    def _look_up(self, key: str, wanted: str):
        try:
            declaration = self.declarations[key]
        except KeyError:
            known = ", ".join(self.declarations) or "nothing at all"
            raise KeyError(f"this kiwari has no {key!r} in it. It declares: {known}") from None
        if declaration.kind != wanted:
            raise TypeError(
                f"{key!r} is a {declaration.kind}, not a {wanted}. Read it with .{declaration.kind}()"
            )
        return self.values.get(key, declaration.default)

    def length(self, key: str) -> float:
        """A distance, in metres."""
        return self._look_up(key, LENGTH)

    def angle(self, key: str) -> float:
        """An angle, in radians."""
        return self._look_up(key, ANGLE)

    def count(self, key: str) -> int:
        """A whole number of things."""
        return self._look_up(key, COUNT)

    def number(self, key: str) -> float:
        """A plain dimensionless number."""
        return self._look_up(key, NUMBER)

    def flag(self, key: str) -> bool:
        """On or off."""
        return self._look_up(key, FLAG)

    def text(self, key: str) -> str:
        """Free text."""
        return self._look_up(key, TEXT)

    def choice(self, key: str, choices: Optional[type] = None) -> Any:
        """One of an Enum's members.

        Pass the Enum class to be told at the call site if the declaration has
        changed under you.
        """
        value = self._look_up(key, CHOICE)
        if choices is not None:
            declared = self.declarations[key].choices
            if declared is not choices:
                raise TypeError(
                    f"{key!r} chooses from {declared.__name__}, not {choices.__name__}"
                )
        return value

    def v2(self, key: str) -> V2:
        """Two lengths."""
        return self._look_up(key, POINT2)

    def v3(self, key: str) -> V3:
        """Three lengths."""
        return self._look_up(key, POINT3)

    # -- binding ----------------------------------------------------------

    def resolve(self, incoming: Union["Kiwari", Mapping[str, Any], None]) -> "Kiwari":
        """This kiwari with *incoming*'s values laid over its own.

        Takes another kiwari (whose values are used, not its declarations), a
        plain mapping of key to value, or None for "just the defaults". Every
        value is checked against *this* kiwari's declarations -- which is what
        makes editing the file while the viewer is open come out right: the
        declarations made on this run win, and values for keys that survived
        carry over.

        A key that is no longer declared is dropped with a warning rather than
        raising: it means the file changed under a saved value, which the
        author cannot fix from inside the build.
        """
        if incoming is None:
            return self

        # Recognised by shape, not by isinstance: the runner purges and
        # re-imports kumiki on every reload so source edits take effect, which
        # makes the Kiwari held from the previous build a different class
        # object from this one. It is still a kiwari.
        if hasattr(incoming, "declarations") and hasattr(incoming, "values"):
            arriving = dict(incoming.values)
            arriving_texts = dict(getattr(incoming, "texts", {}))
        elif isinstance(incoming, Mapping):
            arriving, arriving_texts = _split_values_and_texts(incoming)
        else:
            raise TypeError(
                f"a kiwari resolves against another kiwari or a mapping, not {type(incoming).__name__}"
            )

        stale = [key for key in arriving if key not in self.declarations]
        if stale:
            warnings.warn(
                f"{', '.join(sorted(stale))} {'is' if len(stale) == 1 else 'are'} no longer "
                f"declared by this kiwari, so {'it was' if len(stale) == 1 else 'they were'} "
                f"ignored. Declares: {', '.join(self.declarations) or 'nothing'}."
            )

        values = dict(self.values)
        texts = dict(self.texts)
        for key, declaration in self.declarations.items():
            if key not in arriving:
                continue
            values[key] = _coerce(key, declaration, arriving[key])
            written = arriving_texts.get(key)
            if written is not None:
                texts[key] = written
            else:
                texts.pop(key, None)
        return replace(self, values=values, texts=texts)

    # -- describing -------------------------------------------------------

    def default(self, key: str) -> Any:
        """What *key* is when nobody has said otherwise."""
        return self.declarations[key].default

    def changed_from_defaults(self) -> Tuple[str, ...]:
        """The keys whose value is not what the code declares.

        What the viewer highlights, and the only thing a companion file saves:
        writing every value out would mean changing a default in the source
        silently did nothing.
        """
        return tuple(
            key for key, declaration in self.declarations.items()
            if key in self.values and not _same_value(self.values[key], declaration.default)
        )

    def written(self, key: str) -> str:
        """*key*'s value as it would be typed.

        What somebody actually typed, where they did. Writing a length back out
        is lossy in inches, so the text beats anything we could regenerate.
        """
        if key in self.texts:
            return self.texts[key]
        declaration = self.declarations[key]
        return _write(declaration, self.values.get(key, declaration.default))

    def to_payload(self) -> Dict[str, Any]:
        """The whole kiwari as JSON-able data, for the viewer."""
        return {
            "schema": [
                _declaration_payload(key, declaration)
                for key, declaration in self.declarations.items()
            ],
            "applied": {
                key: self.value_payload(key)
                for key in self.declarations
            },
            "changed": list(self.changed_from_defaults()),
        }

    def value_payload(self, key: str) -> Dict[str, Any]:
        """One value, as the viewer holds it: the number and how it was typed."""
        declaration = self.declarations[key]
        value = self.values.get(key, declaration.default)
        payload: Dict[str, Any] = {"value": _plain(declaration, value)}
        written = self.texts.get(key)
        if written is None and value is not None and declaration.kind in _MEASURED:
            written = _write(declaration, value)
        if written is not None:
            payload["text"] = written
        return payload


def kiwari(**declarations: Declaration) -> Kiwari:
    """Declare what a frame is proportioned from.

    Each keyword is a parameter's key and each value is a declaration::

        kiwari(
            legs=count(4, minimum=3),
            seat_height=length(mm(450)),
        )
    """
    for key, declaration in declarations.items():
        if not isinstance(declaration, Declaration):
            raise TypeError(
                f"{key!r} must be declared with one of length(), angle(), count(), number(), "
                f"flag(), text(), choice(), point2() or point3() -- got {type(declaration).__name__}"
            )
    # Coerced now so a default that is not what it claims to be is an error
    # where it was written, not on whichever later run first reads it.
    values = {
        key: _coerce(key, declaration, declaration.default)
        for key, declaration in declarations.items()
    }
    return Kiwari(declarations=dict(declarations), values=values)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_values_and_texts(incoming: Mapping[str, Any]):
    """Accept both {key: value} and the viewer's {key: {value, text}}."""
    values: Dict[str, Any] = {}
    texts: Dict[str, str] = {}
    for key, entry in incoming.items():
        if isinstance(entry, Mapping) and ("value" in entry or "text" in entry):
            if "text" in entry and entry["text"] is not None:
                texts[key] = str(entry["text"])
            values[key] = entry.get("value", entry.get("text"))
        else:
            values[key] = entry
    return values, texts


def _same_value(one: Any, other: Any) -> bool:
    if one is None or other is None:
        return one is other
    one_shape = getattr(one, "shape", None)
    if one_shape is not None and getattr(other, "shape", None) == one_shape:
        return all(
            abs(float(one[i]) - float(other[i])) <= 1e-12
            for i in range(one_shape[0] * one_shape[1])
        )
    if isinstance(one, bool) or isinstance(other, bool):
        return bool(one) == bool(other)
    if isinstance(one, (int, float)) and isinstance(other, (int, float)):
        return abs(float(one) - float(other)) <= 1e-12
    return one == other


def _write(declaration: Declaration, value: Any) -> str:
    if value is None:
        return ""
    if declaration.kind in _MEASURED:
        _, write = _MEASURED[declaration.kind]
        return write(value)
    if declaration.kind in _VECTOR_AXES:
        axes = _VECTOR_AXES[declaration.kind]
        return ", ".join(format_length(value[index]) for index in range(len(axes)))
    if declaration.kind == CHOICE:
        return value.name
    return str(value)


def _plain(declaration: Declaration, value: Any) -> Any:
    """A value as JSON holds it."""
    if value is None:
        return None
    if declaration.kind == CHOICE:
        return value.name
    if declaration.kind in _VECTOR_AXES:
        axes = _VECTOR_AXES[declaration.kind]
        return {axis: float(value[index]) for index, axis in enumerate(axes)}
    if declaration.kind == FLAG:
        return bool(value)
    if declaration.kind == TEXT:
        return str(value)
    if declaration.kind == COUNT:
        return int(value)
    return float(value)


def _declaration_payload(key: str, declaration: Declaration) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "key": key,
        "kind": declaration.kind,
        "about": declaration.about,
        "default": {"value": _plain(declaration, declaration.default)},
    }
    if declaration.default is not None and declaration.kind in _MEASURED:
        payload["default"]["text"] = _write(declaration, declaration.default)
    if declaration.optional:
        payload["optional"] = True
    if declaration.minimum is not None:
        payload["minimum"] = float(declaration.minimum)
    if declaration.maximum is not None:
        payload["maximum"] = float(declaration.maximum)
    if declaration.choices is not None:
        payload["choices"] = [
            {"value": option.name, "label": _label_for(option)}
            for option in declaration.choices
        ]
    return payload


def _label_for(option: Enum) -> str:
    """A member's name as a person would read it: TOP -> Top."""
    return option.name.replace("_", " ").title()
