/**
 * Where a frame's timbers are, for an agent: each timber's world bounding box, which others it
 * touches, and whether the frame holds together or falls into separate groups (timbers that touch
 * nothing joining them to the rest). Read from a view's frame data (runner.py serialize_frame).
 */

/** Two boxes this close or closer touch, in metres. */
const TOUCHING = 0.001;

/** A serialised sympy value as a number: "0.2", "1/5", "-3/2"; NaN for anything else (sqrt(2)/2). */
function numberOf(value) {
    if (typeof value === 'number') return value;
    const text = String(value).trim();
    const fraction = /^(-?[\d.]+)\/([\d.]+)$/.exec(text);
    return fraction ? Number(fraction[1]) / Number(fraction[2]) : Number(text);
}

/** A timber's world bounding box, { min, max }, or null if its numbers can't be read. */
function boxOf(timber) {
    const vector = (values) => (Array.isArray(values) ? values.map(numberOf) : [NaN, NaN, NaN]);
    const [p, l, w, h] = ['bottom_position', 'length_direction', 'width_direction', 'height_direction'].map((key) => vector(timber[key]));
    const [length, width, height] = ['length', 'width', 'height'].map((key) => numberOf(timber[key]));
    if (![...p, ...l, ...w, ...h, length, width, height].every(Number.isFinite)) return null;
    const min = [Infinity, Infinity, Infinity];
    const max = [-Infinity, -Infinity, -Infinity];
    for (const a of [0, length]) {
        for (const b of [-width / 2, width / 2]) {
            for (const c of [-height / 2, height / 2]) {
                for (let i = 0; i < 3; i++) {
                    const value = p[i] + a * l[i] + b * w[i] + c * h[i];
                    min[i] = Math.min(min[i], value);
                    max[i] = Math.max(max[i], value);
                }
            }
        }
    }
    return { min, max };
}

const touches = (a, b) => [0, 1, 2].every((i) => a.min[i] <= b.max[i] + TOUCHING && b.min[i] <= a.max[i] + TOUCHING);
const rounded = (values) => values.map((value) => Math.round(value * 10000) / 10000);

/**
 * The frame described: { name, timbers: [{ name, size, min, max, touches }], groups, note }. Boxes
 * are axis-aligned, so for a timber at an angle they are larger than the timber.
 */
function describeFrame(frame) {
    const timbers = (frame && Array.isArray(frame.timbers) ? frame.timbers : []).map((timber) => ({ timber, box: boxOf(timber) }));
    const described = timbers.map(({ timber, box }, i) => ({
        name: timber.name,
        size: { length: numberOf(timber.length), width: numberOf(timber.width), height: numberOf(timber.height) },
        ...(box ? { min: rounded(box.min), max: rounded(box.max) } : { box: 'unknown: its position or size is not a plain number' }),
        touches: box ? timbers.filter((other, j) => j !== i && other.box && touches(box, other.box)).map((other) => other.timber.name) : [],
    }));

    // Timbers that touch, transitively, as groups: more than one means parts float free of each other.
    const group = timbers.map((_, i) => i);
    const root = (i) => (group[i] === i ? i : (group[i] = root(group[i])));
    timbers.forEach(({ box }, i) => timbers.forEach((other, j) => {
        if (j > i && box && other.box && touches(box, other.box)) group[root(i)] = root(j);
    }));
    const groups = [...new Set(timbers.map((_, i) => root(i)))]
        .map((r) => timbers.filter((_, i) => root(i) === r).map(({ timber }) => timber.name));

    return {
        name: (frame && frame.name) || null,
        units: 'metres, world space (Z up)',
        timbers: described,
        groups,
        note: groups.length > 1
            ? `The timbers fall into ${groups.length} groups that don't touch each other: a joint between groups cuts into air.`
            : 'Every timber touches the rest of the frame.',
    };
}

module.exports = { describeFrame, numberOf, boxOf };
