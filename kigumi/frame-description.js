/**
 * Where a frame's timbers are, for an agent: each timber's ends, the world direction each of its
 * faces looks, its box as cut, the timbers it touches and its joints, and whether the frame holds
 * together or falls into separate groups (timbers that touch nothing joining them to the rest). Read
 * from a view's frame data (runner.py serialize_frame), its meshes (a tenon reaches past the timber's
 * end) and its layers tree (the joints). formatFrameDescription writes it as YAML for the agent.
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

/** A direction as the world axis it runs along ("+X"), or as rounded numbers when it runs along none. */
function axisName(vector) {
    const v = vector.map(numberOf);
    if (!v.every(Number.isFinite)) return 'unknown';
    const axis = v.findIndex((value) => Math.abs(Math.abs(value) - 1) < 1e-6);
    if (axis >= 0 && v.every((value, i) => i === axis || Math.abs(value) < 1e-6)) return `${v[axis] > 0 ? '+' : '-'}${'XYZ'[axis]}`;
    return rounded(v);
}

/** Where each of a timber's faces looks: TOP along its length, RIGHT its width, FRONT its height (kumiki's TimberFace). */
function facesOf(timber) {
    const directions = { TOP: timber.length_direction, RIGHT: timber.width_direction, FRONT: timber.height_direction };
    const opposite = { TOP: 'BOTTOM', RIGHT: 'LEFT', FRONT: 'BACK' };
    const faces = {};
    for (const [face, direction] of Object.entries(directions)) {
        const vector = Array.isArray(direction) ? direction.map(numberOf) : [NaN, NaN, NaN];
        faces[face] = axisName(vector);
        faces[opposite[face]] = axisName(vector.map((value) => -value));
    }
    return faces;
}

/** The centres of a timber's bottom and top ends, or null if its numbers can't be read. */
function endsOf(timber) {
    const p = Array.isArray(timber.bottom_position) ? timber.bottom_position.map(numberOf) : [];
    const l = Array.isArray(timber.length_direction) ? timber.length_direction.map(numberOf) : [];
    const length = numberOf(timber.length);
    if (p.length !== 3 || l.length !== 3 || ![...p, ...l, length].every(Number.isFinite)) return null;
    return { bottom: rounded(p), top: rounded(p.map((value, i) => value + length * l[i])) };
}

/** The layers tree's joints (runner.py serialize_layers), each with the "name#n" keys of the timbers it joins. */
function jointsOf(layers) {
    const keyById = new Map((layers && Array.isArray(layers.timbers) ? layers.timbers : []).map((t) => [t.kumikiEphemeralId, t.memberKey]));
    return (layers && Array.isArray(layers.joints) ? layers.joints : []).map((joint) => ({
        name: joint.name,
        type: joint.jointType || null,
        keys: (joint.members || []).map((member) => keyById.get(member.timberKumikiEphemeralId)).filter(Boolean),
    }));
}

const touches = (a, b) => [0, 1, 2].every((i) => a.min[i] <= b.max[i] + TOUCHING && b.min[i] <= a.max[i] + TOUCHING);
const rounded = (values) => values.map((value) => Math.round(value * 10000) / 10000);

/** A mesh's world bounding box from its flat [x, y, z, ...] vertices, or null. */
function meshBox(mesh) {
    const vertices = mesh && mesh.vertices;
    if (!Array.isArray(vertices) || vertices.length < 3) return null;
    const min = [Infinity, Infinity, Infinity];
    const max = [-Infinity, -Infinity, -Infinity];
    for (let i = 0; i < vertices.length; i++) {
        min[i % 3] = Math.min(min[i % 3], vertices[i]);
        max[i % 3] = Math.max(max[i % 3], vertices[i]);
    }
    return { min, max };
}

/** The "name#n" keys runner.py gives the frame's timbers, in order. */
function memberKeys(timbers) {
    const seen = new Map();
    return timbers.map((timber) => {
        const occurrence = seen.get(timber.name) || 0;
        seen.set(timber.name, occurrence + 1);
        return `${timber.name}#${occurrence}`;
    });
}

/**
 * The frame described: { name, units, extent, timbers: [{ name, size, bottom, top, faces, min, max,
 * touches, joints }], joints, groups, note }. A timber's box is of its cut mesh when `geometry` has
 * one, else of the uncut timber; boxes are axis-aligned, so for a timber at an angle they are larger
 * than the timber. Joints come from `layers`, the view's layers tree.
 */
function describeFrame(frame, geometry = null, layers = null) {
    const listed = frame && Array.isArray(frame.timbers) ? frame.timbers : [];
    const keys = memberKeys(listed);
    const meshes = new Map((geometry && Array.isArray(geometry.meshes) ? geometry.meshes : []).map((mesh) => [mesh.memberKey, mesh]));
    const nameByKey = new Map(listed.map((timber, i) => [keys[i], timber.name]));
    const joints = jointsOf(layers).map((joint) => ({ ...joint, timbers: joint.keys.map((key) => nameByKey.get(key) || key) }));
    const timbers = listed.map((timber, i) => ({ timber, box: meshBox(meshes.get(keys[i])) || boxOf(timber) }));
    const described = timbers.map(({ timber, box }, i) => ({
        name: timber.name,
        size: { length: numberOf(timber.length), width: numberOf(timber.width), height: numberOf(timber.height) },
        ...(endsOf(timber) || {}),
        faces: facesOf(timber),
        ...(box ? { min: rounded(box.min), max: rounded(box.max) } : { box: 'unknown: its position or size is not a plain number' }),
        touches: box ? timbers.filter((other, j) => j !== i && other.box && touches(box, other.box)).map((other) => other.timber.name) : [],
        joints: joints.filter((joint) => joint.keys.includes(keys[i]))
            .map((joint) => ({ name: joint.name, type: joint.type, with: joint.timbers.filter((_, k) => joint.keys[k] !== keys[i]) })),
    }));
    const boxes = timbers.map(({ box }) => box).filter(Boolean);
    const extent = boxes.length ? { min: rounded([0, 1, 2].map((a) => Math.min(...boxes.map((b) => b.min[a])))),
        max: rounded([0, 1, 2].map((a) => Math.max(...boxes.map((b) => b.max[a])))) } : null;

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
        extent,
        timbers: described,
        joints: joints.map(({ name, type, timbers: names }) => ({ name, type, timbers: names })),
        groups,
        note: groups.length > 1
            ? `The timbers fall into ${groups.length} groups that don't touch each other: a joint between groups cuts into air.`
            : 'Every timber touches the rest of the frame.',
    };
}

/** A YAML scalar: plain where that reads back the same, else quoted. */
function scalar(value) {
    if (value === null || value === undefined) return 'null';
    if (typeof value === 'number') return String(value);
    const text = String(value);
    return /^[A-Za-z_+-][\w .+#/()-]*$/.test(text) && !/^(true|false|null|yes|no|on|off|~)$/i.test(text) && !/[ ]$/.test(text)
        && !/: /.test(text) ? text : JSON.stringify(text);
}

/** A joint as one line: its type, its name when that says more, and the timbers `key` names. */
const jointLine = (joint, key, timbers) => `{type: ${scalar(joint.type)}${joint.name && joint.name !== joint.type
    ? `, name: ${scalar(joint.name)}` : ''}, ${key}: ${list(timbers)}}`;

const list = (values) => `[${values.map(scalar).join(', ')}]`;
const point = (values) => list(values);

/**
 * `described` (describeFrame's) as YAML for the agent: per timber its size, ends, the world direction
 * each face looks, its box, what it touches and its joints; then how many joints, and the groups if it falls apart.
 */
function formatFrameDescription(described) {
    const lines = [
        `frame: ${scalar(described.name)}`,
        '# Metres, world space, Z up. faces: the world direction each face of a timber looks.',
        '# bottom/top: the centres of its two ends. box: its bounding box as cut (larger than the timber when at an angle).',
    ];
    if (described.extent) lines.push(`extent: {min: ${point(described.extent.min)}, max: ${point(described.extent.max)}}`);
    lines.push(`connected: ${described.groups.length <= 1 ? 'true' : 'false'}  # ${described.note}`);
    lines.push(`timbers:${described.timbers.length ? '' : ' []'}`);
    for (const timber of described.timbers) {
        const { length, width, height } = timber.size;
        lines.push(`  - name: ${scalar(timber.name)}`);
        lines.push(`    size: {length: ${scalar(length)}, width: ${scalar(width)}, height: ${scalar(height)}}`);
        if (timber.bottom) lines.push(`    bottom: ${point(timber.bottom)}`, `    top: ${point(timber.top)}`);
        lines.push(`    faces: {${Object.entries(timber.faces).map(([face, dir]) => `${face}: ${Array.isArray(dir) ? point(dir) : scalar(dir)}`).join(', ')}}`);
        lines.push(timber.min ? `    box: {min: ${point(timber.min)}, max: ${point(timber.max)}}` : `    box: ${scalar(timber.box)}`);
        lines.push(`    touches: ${list(timber.touches)}`);
        if (timber.joints.length) {
            lines.push('    joints:');
            for (const joint of timber.joints) lines.push(`      - ${jointLine(joint, 'with', joint.with)}`);
        }
    }
    lines.push(described.joints.length ? `joints: ${described.joints.length}`
        : 'joints: 0  # none in the frame: build it with Frame.from_joints to list them');
    if (described.groups.length > 1) {
        lines.push('groups:');
        for (const group of described.groups) lines.push(`  - ${list(group)}`);
    }
    return `${lines.join('\n')}\n`;
}

module.exports = { describeFrame, formatFrameDescription, numberOf, boxOf };
