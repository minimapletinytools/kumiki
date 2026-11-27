/**
 * A drawing's viewport tree, as the runner sends it (kumiki.drawings.layout.layout_to_wire), and
 * the edits the sheet makes to it. Every edit returns a new tree; the viewer sends the whole of it
 * back (set_drawing_layout).
 *
 * A node is a leaf `{ leaf: name }` or a split `{ split: { direction, gap, portions: [{ share | length, node }] } }`,
 * with an optional `padding`; a root also has `rect` ([x, y, w, h], fractions of the page from the
 * top left) and `z`. A view by itself at a root floats; one inside a split is in a grid.
 */

const MIN_SIZE = 0.03;

const clone = (value) => JSON.parse(JSON.stringify(value));

/** Every leaf's name, in order. */
function leafNames(layout) {
    const names = [];
    const walk = (node) => {
        if (node.leaf !== undefined) names.push(node.leaf);
        for (const portion of (node.split && node.split.portions) || []) walk(portion.node);
    };
    for (const root of (layout && layout.roots) || []) walk(root);
    return names;
}

/** The node at `path` ([root, portion, portion, ...]). */
function nodeAt(layout, path) {
    let node = layout.roots[path[0]];
    for (const index of path.slice(1)) node = node.split.portions[index].node;
    return node;
}

/** Where the leaf `name` is: its path, or null. */
function findLeaf(layout, name) {
    let found = null;
    const walk = (node, path) => {
        if (found) return;
        if (node.leaf === name) {
            found = path;
            return;
        }
        ((node.split && node.split.portions) || []).forEach((portion, index) => walk(portion.node, [...path, index]));
    };
    ((layout && layout.roots) || []).forEach((root, index) => walk(root, [index]));
    return found;
}

/** Whether `name` floats: a root by itself, rather than a cell of a grid. */
function isFloating(layout, name) {
    const path = findLeaf(layout, name);
    return Boolean(path && path.length === 1);
}

function inset(rect, padding, page) {
    if (!padding) return rect;
    const [x, y, width, height] = rect;
    const across = padding / page.width;
    const up = padding / page.height;
    return [x + across, y + up, Math.max(0, width - 2 * across), Math.max(0, height - 2 * up)];
}

/** Each portion's rect in `rect`: lengths first, shares divide the rest (layout._divide). */
function divide(split, rect, page) {
    const [x, y, width, height] = rect;
    const columns = split.direction === 'columns';
    const pageExtent = columns ? page.width : page.height;
    const span = columns ? width : height;
    const portions = split.portions || [];
    const gap = (split.gap || 0) / pageExtent;
    const free = span - gap * Math.max(0, portions.length - 1);
    const lengths = portions.map((portion) => (portion.length !== undefined ? portion.length / pageExtent : null));
    const leftOver = Math.max(0, free - lengths.reduce((sum, one) => sum + (one || 0), 0));
    const shares = portions.reduce((sum, portion) => sum + (portion.length !== undefined ? 0 : (portion.share || 1)), 0);
    let offset = columns ? x : y;
    return portions.map((portion, index) => {
        const extent = lengths[index] !== null
            ? lengths[index]
            : (shares ? leftOver * (portion.share || 1) / shares : 0);
        const cell = columns ? [offset, y, extent, height] : [x, offset, width, extent];
        offset += extent + gap;
        return cell;
    });
}

/** Every node's cell, roots first: { path, node, rect (before its padding), inner (after) }. */
function layoutCells(layout, page) {
    const cells = [];
    const place = (node, rect, path) => {
        const inner = inset(rect, node.padding || 0, page);
        cells.push({ path, node, rect, inner });
        if (node.split) {
            divide(node.split, inner, page).forEach((child, index) => place(node.split.portions[index].node, child, [...path, index]));
        }
    };
    ((layout && layout.roots) || []).forEach((root, index) => place(root, root.rect || [0, 0, 1, 1], [index]));
    return cells;
}

/** Each leaf's rect on the page, by name (layout.resolve_viewports). */
function resolveLayout(layout, page) {
    const rects = new Map();
    for (const cell of layoutCells(layout, page)) {
        if (cell.node.leaf !== undefined) rects.set(cell.node.leaf, cell.inner);
    }
    return rects;
}

/**
 * The lines between a grid's cells, which drag to share the space differently: the split's path,
 * the portion before the line, which way it runs, and where it is.
 */
function dividers(layout, page) {
    const found = [];
    for (const cell of layoutCells(layout, page)) {
        if (!cell.node.split) continue;
        const columns = cell.node.split.direction === 'columns';
        const rects = divide(cell.node.split, cell.inner, page);
        for (let index = 0; index + 1 < rects.length; index += 1) {
            const before = rects[index];
            const after = rects[index + 1];
            const at = columns ? (before[0] + before[2] + after[0]) / 2 : (before[1] + before[3] + after[1]) / 2;
            found.push({
                path: cell.path,
                index,
                direction: cell.node.split.direction,
                line: columns ? [at, cell.inner[1], at, cell.inner[1] + cell.inner[3]]
                    : [cell.inner[0], at, cell.inner[0] + cell.inner[2], at],
            });
        }
    }
    return found;
}

/** Put `replacement` where the node at `path` is, keeping a root's place on the page. */
function replaceAt(layout, path, replacement) {
    if (path.length === 1) {
        const root = layout.roots[path[0]];
        layout.roots[path[0]] = { ...replacement, rect: root.rect, z: root.z };
        return;
    }
    nodeAt(layout, path.slice(0, -1)).split.portions[path[path.length - 1]].node = replacement;
}

/** Without its root's place on the page: what moves when a leaf moves. */
function bare(node) {
    const { rect: _rect, z: _z, ...rest } = node;
    return rest;
}

/** The tree without the leaf `name`. A split left with one portion becomes it. */
function removeLeaf(layout, name) {
    const next = clone(layout);
    const path = findLeaf(next, name);
    if (!path) return next;
    if (path.length === 1) {
        next.roots.splice(path[0], 1);
        return next;
    }
    const parentPath = path.slice(0, -1);
    const parent = nodeAt(next, parentPath);
    parent.split.portions.splice(path[path.length - 1], 1);
    if (parent.split.portions.length === 1) {
        replaceAt(next, parentPath, parent.split.portions[0].node);
    }
    return next;
}

function topZ(layout) {
    return Math.max(0, ...layout.roots.map((root) => root.z || 0));
}

/** The tree with `name` taken out of wherever it is and floated at `rect`, in front. */
function floatLeaf(layout, name, rect) {
    const path = findLeaf(layout, name);
    if (!path) return clone(layout);
    const node = bare(clone(nodeAt(layout, path)));
    const next = removeLeaf(layout, name);
    next.roots.push({ ...node, rect: clampRect(rect), z: topZ(next) + 1 });
    return next;
}

/** A rect kept on the page and no smaller than a handle can grab. */
function clampRect(rect) {
    const width = Math.min(1, Math.max(MIN_SIZE, rect[2]));
    const height = Math.min(1, Math.max(MIN_SIZE, rect[3]));
    return [Math.min(Math.max(0, rect[0]), 1 - width), Math.min(Math.max(0, rect[1]), 1 - height), width, height];
}

/** Move or resize a floating view. */
function setFloatingRect(layout, name, rect) {
    const next = clone(layout);
    const path = findLeaf(next, name);
    if (path && path.length === 1) next.roots[path[0]].rect = clampRect(rect);
    return next;
}

/**
 * Put `node` beside the leaf `target`, on `side` ('left', 'right', 'top', 'bottom'): into
 * target's own split when that runs the same way, else a new split of the two in target's cell.
 */
function placeBeside(layout, node, target, side) {
    const path = findLeaf(layout, target);
    return path ? placeBesidePath(layout, node, path, side) : clone(layout);
}

/** placeBeside, beside the node at `path`, leaf or split. */
function placeBesidePath(layout, node, path, side) {
    const next = clone(layout);
    const direction = side === 'left' || side === 'right' ? 'columns' : 'rows';
    const before = side === 'left' || side === 'top';
    const parent = path.length > 1 ? nodeAt(next, path.slice(0, -1)) : null;
    if (parent && parent.split.direction === direction) {
        const index = path[path.length - 1];
        const portion = parent.split.portions[index];
        const half = portion.length !== undefined ? { length: portion.length / 2 } : { share: (portion.share || 1) / 2 };
        parent.split.portions[index] = { ...half, node: portion.node };
        parent.split.portions.splice(before ? index : index + 1, 0, { ...half, node });
        return next;
    }
    const targetNode = bare(nodeAt(next, path));
    const pair = before ? [node, targetNode] : [targetNode, node];
    replaceAt(next, path, { split: { direction, gap: 0, portions: pair.map((one) => ({ share: 1, node: one })) } });
    return next;
}

const directionOf = (side) => (side === 'left' || side === 'right' ? 'columns' : 'rows');

/**
 * Put `node` into the split at `splitPath`, before its portion `index` (its length: at the end), as
 * big as its others are on average: they give up the room.
 */
function insertInto(layout, node, splitPath, index) {
    const next = clone(layout);
    const portions = nodeAt(next, splitPath).split.portions;
    const lengths = portions.filter((portion) => portion.length !== undefined);
    const size = lengths.length === portions.length
        ? { length: lengths.reduce((sum, portion) => sum + portion.length, 0) / lengths.length }
        : { share: portions.filter((portion) => portion.length === undefined)
            .reduce((sum, portion) => sum + (portion.share || 1), 0) / (portions.length - lengths.length) };
    portions.splice(index, 0, { ...size, node });
    return next;
}

/** Split the node at `path` in two with `node` on `side`, halves alike. */
function wrapPath(layout, node, path, side) {
    const next = clone(layout);
    const before = side === 'left' || side === 'top';
    const targetNode = bare(nodeAt(next, path));
    const pair = before ? [node, targetNode] : [targetNode, node];
    replaceAt(next, path, { split: { direction: directionOf(side), gap: 0, portions: pair.map((one) => ({ share: 1, node: one })) } });
    return next;
}

/** Which root is the sheet's grid: the first that isn't a view floating over it. */
function gridRoot(layout) {
    const index = layout.roots.findIndex((root) => root.leaf === undefined || !root.rect
        || root.rect.every((value, at) => Math.abs(value - [0, 0, 1, 1][at]) < 1e-9));
    return index < 0 ? 0 : index;
}

/** `node` as a new row or column along the sheet's `side`, across the whole grid. */
function besideSheet(layout, node, side) {
    const root = [gridRoot(layout)];
    const grid = layout.roots[root[0]];
    if (grid && grid.split && grid.split.direction === directionOf(side)) {
        const before = side === 'left' || side === 'top';
        return insertInto(layout, node, root, before ? 0 : grid.split.portions.length);
    }
    return grid ? wrapPath(layout, node, root, side) : clone(layout);
}

/**
 * The tree with the leaf `name` moved to wherever `place(layout, node)` puts a node in the tree as
 * it stands: placed first and taken out of its old place after, so `place` can name paths in it.
 */
function moveLeaf(layout, name, place) {
    const path = findLeaf(layout, name);
    if (!path) return clone(layout);
    const node = bare(clone(nodeAt(layout, path)));
    const probe = '\u0000moving';
    const moved = removeLeaf(place(layout, { leaf: probe }), name);
    const at = findLeaf(moved, probe);
    if (!at) return clone(layout);
    replaceAt(moved, at, node);
    return moved;
}

/** The tree with `name` moved into `target`'s cell, which it splits on `side`. */
function dockLeaf(layout, name, target, side) {
    if (name === target || !findLeaf(layout, target)) return clone(layout);
    return moveLeaf(layout, name, (tree, node) => wrapPath(tree, node, findLeaf(tree, target), side));
}

/** The tree with `name` moved into the split at `splitPath`, before portion `index` (dividers). */
function insertLeaf(layout, name, splitPath, index) {
    return moveLeaf(layout, name, (tree, node) => insertInto(tree, node, splitPath, index));
}

/** The tree with `name` moved to a new row or column along the sheet's `side`. */
function edgeLeaf(layout, name, side) {
    return moveLeaf(layout, name, (tree, node) => besideSheet(tree, node, side));
}

/** A name for a copy of `name` that no view has: "Front 2", "Front 3", ... */
function copyName(layout, name) {
    const taken = new Set(leafNames(layout));
    for (let count = 2; ; count += 1) {
        const candidate = `${name} ${count}`;
        if (!taken.has(candidate)) return candidate;
    }
}

/** Split `name`'s cell in two ('columns' or 'rows'), the new half a copy of it. Returns { layout, made }. */
function splitLeaf(layout, name, direction) {
    const path = findLeaf(layout, name);
    if (!path) return { layout: clone(layout), made: null };
    const original = nodeAt(layout, path).copyOf || name;
    const made = copyName(layout, original);
    const copy = { leaf: made, copyOf: original };
    return { layout: placeBeside(layout, copy, name, direction === 'columns' ? 'right' : 'bottom'), made };
}

/**
 * Move the line between portions `index` and `index + 1` of the split at `path` to `at` (a page
 * fraction along the split). Shares are rescaled between the two; a length becomes its new length.
 */
function moveDivider(layout, path, index, at, page) {
    const next = clone(layout);
    const cell = layoutCells(next, page).find((one) => one.path.join('.') === path.join('.'));
    if (!cell || !cell.node.split) return next;
    const split = cell.node.split;
    const columns = split.direction === 'columns';
    const rects = divide(split, cell.inner, page);
    const start = columns ? rects[index][0] : rects[index][1];
    const sizeOf = (rect) => (columns ? rect[2] : rect[3]);
    const total = sizeOf(rects[index]) + sizeOf(rects[index + 1]);
    if (!(total > 0)) return next;
    const first = Math.min(total - MIN_SIZE, Math.max(MIN_SIZE, at - start));
    const sizes = [first, total - first];
    const pageExtent = columns ? page.width : page.height;
    const pair = [split.portions[index], split.portions[index + 1]];
    if (pair.every((portion) => portion.length === undefined)) {
        const shares = (pair[0].share || 1) + (pair[1].share || 1);
        pair[0].share = shares * sizes[0] / total;
        pair[1].share = shares - pair[0].share;
    } else {
        pair.forEach((portion, which) => {
            if (portion.length !== undefined) portion.length = sizes[which] * pageExtent;
        });
    }
    const node = nodeAt(next, cell.path);
    node.split.portions[index] = pair[0];
    node.split.portions[index + 1] = pair[1];
    return next;
}

/** Bring a floating view to the front (`toFront`) or send it behind the rest. */
function restack(layout, name, toFront) {
    const next = clone(layout);
    const path = findLeaf(next, name);
    if (!path) return next;
    const zs = next.roots.map((root) => root.z || 0);
    next.roots[path[0]].z = toFront ? Math.max(...zs) + 1 : Math.min(...zs) - 1;
    return next;
}

/** The camera the layout gives `name` ({look, up, target?, extent?, projection?}), or null. */
function leafCamera(layout, name) {
    const path = findLeaf(layout, name);
    return (path && nodeAt(layout, path).camera) || null;
}

/** The tree with `name` given `camera`, or none with null. */
function setLeafCamera(layout, name, camera) {
    const next = clone(layout);
    const path = findLeaf(next, name);
    if (!path) return next;
    const node = nodeAt(next, path);
    if (camera) node.camera = clone(camera);
    else delete node.camera;
    return next;
}

/** The views whose rect differs between `before` and `after`, by name. */
function movedLeaves(before, after, page) {
    const was = resolveLayout(before, page);
    const moved = [];
    for (const [name, rect] of resolveLayout(after, page)) {
        const old = was.get(name);
        if (!old || old.some((value, index) => Math.abs(value - rect[index]) > 1e-9)) moved.push(name);
    }
    return moved;
}

export {
    leafNames, findLeaf, isFloating, layoutCells, resolveLayout, dividers, removeLeaf, floatLeaf,
    setFloatingRect, dockLeaf, splitLeaf, moveDivider, restack, clampRect, copyName,
    leafCamera, setLeafCamera, movedLeaves, insertLeaf, edgeLeaf,
};
