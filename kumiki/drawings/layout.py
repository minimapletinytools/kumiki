"""Lays out a drawing's viewports on a page: a rect per leaf viewport, as fractions of the page."""

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from dataclasses import dataclass, replace

from .drawing import (Length, Page, Portion, Rect, Share, Size, SplitDirection,
                      Subdivision, Viewport, viewport_names)
from ..identity import ViewportId
from ..rule import Numeric


@dataclass(frozen=True)
class PlacedViewport:
    """A leaf viewport with its name (`id`) and its rect on the page."""

    #: Its name: `Viewport.id`, else its label, else its position (drawing.viewport_names).
    id: ViewportId
    viewport: Viewport
    rect: Rect
    z: int

    @property
    def label(self) -> Optional[str]:
        return self.viewport.label


def _length_fraction(size: Length, page_extent: float) -> float:
    """Return a page-unit length as a fraction of the axis being divided."""
    return float(size.value) / page_extent


def _inset(rect: Rect, padding: Numeric, page: Page) -> Rect:
    """Return `rect` shrunk by `padding` page units on every side."""
    if not padding:
        return rect
    x, y, width, height = rect
    horizontal = float(padding) / float(page.width)
    vertical = float(padding) / float(page.height)
    inset = (x + horizontal, y + vertical, width - 2 * horizontal, height - 2 * vertical)
    if inset[2] <= 0 or inset[3] <= 0:
        raise ValueError(
            f"Padding of {padding} leaves nothing of a viewport {width} x {height} of the page"
        )
    return inset


def _divide(subdivision: Subdivision, rect: Rect, page: Page) -> List[Rect]:
    """Return each portion's rect in order. Lengths are taken first; shares divide the rest."""
    x, y, width, height = rect
    along_columns = subdivision.direction is SplitDirection.COLUMNS
    # Lengths are in page units and rects are fractions of the page, so
    # everything crosses through the page's size on the axis being divided.
    page_extent = float(page.width if along_columns else page.height)
    span = width if along_columns else height

    gap = float(subdivision.gap) / page_extent
    free = span - gap * (len(subdivision.portions) - 1)

    lengths = {
        index: _length_fraction(portion.size, page_extent)
        for index, portion in enumerate(subdivision.portions)
        if isinstance(portion.size, Length)
    }
    shares = {
        index: float(portion.size.value)
        for index, portion in enumerate(subdivision.portions)
        if isinstance(portion.size, Share)
    }

    left_over = free - sum(lengths.values())
    if left_over < 0:
        raise ValueError(
            f"A {subdivision.direction.value} subdivision asks for more fixed size than "
            f"its cell has: {sum(lengths.values()) * page_extent:.4g} of "
            f"{free * page_extent:.4g} page units"
        )
    total_shares = sum(shares.values())

    rects: List[Rect] = []
    offset = x if along_columns else y
    for index in range(len(subdivision.portions)):
        if index in lengths:
            extent = lengths[index]
        else:
            extent = left_over * shares[index] / total_shares if total_shares else 0.0
        rects.append((offset, y, extent, height) if along_columns
                     else (x, offset, width, extent))
        offset += extent + gap
    return rects


def _place(viewport: Viewport, rect: Rect, path: Tuple[int, ...], z: int, page: Page,
           into: List[PlacedViewport]) -> None:
    """Add every leaf under `viewport` to `into`."""
    cell = _inset(rect, viewport.padding, page)
    if viewport.subdivision is None:
        into.append(PlacedViewport(
            id=ViewportId(".".join(str(step) for step in path)),
            viewport=viewport, rect=cell, z=z,
        ))
        return
    portions = viewport.subdivision.portions
    for index, (portion, child_rect) in enumerate(
            zip(portions, _divide(viewport.subdivision, cell, page))):
        _place(portion.viewport, child_rect, path + (index,), z, page, into)


def resolve_viewports(viewports: Sequence[Viewport], page: Page) -> Tuple[PlacedViewport, ...]:
    """Return every leaf viewport with its rect, ordered by z then position (draw order)."""
    placed: List[PlacedViewport] = []
    for index, root in enumerate(viewports):
        if root.rect is None:
            raise ValueError(
                f"Viewport {index} floats on the page and needs a rect. "
                f"Drawing checks this; resolving a bare list does not."
            )
        _place(root, root.rect, (index,), root.z, page, placed)
    names = viewport_names(viewports)
    placed = [replace(view, id=ViewportId(names.get(str(view.id), str(view.id)))) for view in placed]
    # Sorted on z alone, with Python's stable sort keeping written order within
    # a z. Sorting on the id as well would order "0.10" before "0.2".
    return tuple(sorted(placed, key=lambda view: view.z))


def resolve_drawing(drawing) -> Tuple[PlacedViewport, ...]:
    """Return a drawing's leaf viewports laid out on its own page."""
    if drawing.page is None:
        raise ValueError(
            f"Drawing {drawing.drawing_id} has no page, so there is nothing for its "
            f"viewports to be fractions of."
        )
    return resolve_viewports(drawing.viewports, drawing.page)


# --- the layout as JSON ------------------------------------------------------
#
# The viewer edits a drawing's layout as this, and the drawings file keeps an edited one:
# {"roots": [node]}, a node being {"rect": [x, y, w, h], "z": int} at a root, an optional
# "padding", and either {"leaf": name} or {"split": {"direction", "gap", "portions": [{"share"|"length", "node"}]}}.
# Leaves go by name (viewport_names), so a moved view keeps its measurements.

LayoutWire = Dict[str, Any]


def layout_to_wire(viewports: Sequence[Viewport]) -> LayoutWire:
    """Return a viewport tree as JSON, each leaf by its name."""
    names = viewport_names(viewports)

    def node(viewport: Viewport, position: str) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if viewport.padding:
            out["padding"] = float(viewport.padding)
        if viewport.subdivision is None:
            out["leaf"] = names.get(position, position)
            return out
        split = viewport.subdivision
        out["split"] = {
            "direction": split.direction.value,
            "gap": float(split.gap),
            "portions": [
                {("length" if isinstance(portion.size, Length) else "share"): float(portion.size.value),
                 "node": node(portion.viewport, f"{position}.{index}")}
                for index, portion in enumerate(split.portions)
            ],
        }
        return out

    roots = []
    for index, root in enumerate(viewports):
        entry = node(root, str(index))
        entry["rect"] = [float(value) for value in (root.rect or (0.0, 0.0, 1.0, 1.0))]
        entry["z"] = int(root.z)
        roots.append(entry)
    return {"roots": roots}


def _on_page(rect: Sequence[Any]) -> Rect:
    """Return a rect nudged onto the page, which rounding in a viewer can push a hair off it."""
    x, y, width, height = (float(value) for value in rect)
    width, height = min(max(width, 1e-6), 1.0), min(max(height, 1e-6), 1.0)
    return (min(max(x, 0.0), 1.0 - width), min(max(y, 0.0), 1.0 - height), width, height)


def layout_from_wire(wire: Mapping[str, Any], leaves: Mapping[str, Viewport]) -> Tuple[Viewport, ...]:
    """Return the viewport tree `wire` describes, each leaf taken by name from `leaves` and given that name as its id.

    A leaf `leaves` doesn't have is left out, and a split left holding one view becomes that view.
    """
    def build(node: Mapping[str, Any]) -> Optional[Viewport]:
        padding = node.get("padding") or 0
        if "leaf" in node:
            leaf = leaves.get(str(node["leaf"]))
            if leaf is None:
                return None
            return replace(leaf, id=str(node["leaf"]), padding=padding, rect=None, z=0)
        split = node.get("split") or {}
        portions = []
        for portion in split.get("portions") or []:
            child = build(portion.get("node") or {})
            if child is None:
                continue
            size = Length(portion["length"]) if "length" in portion else Share(portion.get("share") or 1)
            portions.append(Portion(viewport=child, size=size))
        if not portions:
            return None
        if len(portions) == 1:
            return portions[0].viewport
        return Viewport(padding=padding, subdivision=Subdivision(
            direction=SplitDirection(split.get("direction", "columns")),
            portions=portions, gap=split.get("gap") or 0))

    roots = []
    for node in wire.get("roots") or []:
        built = build(node)
        if built is not None:
            roots.append(replace(built, rect=_on_page(node.get("rect") or (0, 0, 1, 1)), z=int(node.get("z") or 0)))
    return tuple(roots)


def wire_leaf_nodes(wire: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """Return every leaf node in a layout's JSON, in order."""
    found: List[Mapping[str, Any]] = []

    def walk(node: Mapping[str, Any]) -> None:
        if "leaf" in node:
            found.append(node)
        for portion in (node.get("split") or {}).get("portions") or []:
            walk(portion.get("node") or {})

    for root in wire.get("roots") or []:
        walk(root)
    return found
