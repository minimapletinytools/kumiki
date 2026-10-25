/**
 * The agent evals' tasks: each a project's starting files, what the user asks, the file it should
 * leave building, and checks on how that frame came out (build_frame.py's report).
 */

const fs = require('fs');
const path = require('path');

const STARTER = fs.readFileSync(path.join(__dirname, '..', '..', '..', 'patterns', 'structures', 'my_cute_frame.py'), 'utf8');

/** `text` with `before` replaced by `after`, which must be there. */
function changed(text, before, after) {
    if (!text.includes(before)) throw new Error(`The starter frame no longer has: ${before}`);
    return text.replace(before, after);
}

const builds = (report) => [report.ok, report.ok ? 'it builds' : `it fails: ${report.error}`];
const holdsTogether = (report) => [report.ok && report.groups.length === 1,
    report.ok ? `${report.groups.length} group${report.groups.length === 1 ? '' : 's'} of touching timbers` : 'no frame'];
const timbers = (count) => (report) => [report.ok && report.timbers.length === count, `${report.ok ? report.timbers.length : 0} timbers, ${count} wanted`];
const span = (report, axis) => Math.max(...report.timbers.map((t) => t.max[axis])) - Math.min(...report.timbers.map((t) => t.min[axis]));

const TASKS = [
    {
        name: 'fix-attribute',
        files: { 'frame.py': changed(STARTER, 'cross_length = side_spacing',
            'cross_length = right_side.bottom_position[0] - left_side.bottom_position[0]') },
        prompt: 'frame.py fails to build, can you fix it?',
        target: 'frame.py',
        checks: [builds, timbers(4), holdsTogether],
    },
    {
        name: 'fix-face',
        files: { 'frame.py': changed(STARTER, 'front_face_on_butt_timber=TimberLongFace.FRONT', 'front_face_on_butt_timber=TimberLongFace.RIGHT') },
        prompt: 'frame.py fails to build, can you fix it?',
        target: 'frame.py',
        checks: [builds, timbers(4), holdsTogether],
    },
    {
        name: 'change',
        files: { 'frame.py': STARTER },
        prompt: 'In frame.py, make the frame 1 m long instead of 600 mm, and add a third cross timber across the middle, '
            + 'joined to the sides like the other two.',
        target: 'frame.py',
        checks: [builds, timbers(5), holdsTogether,
            (report) => [report.ok && Math.abs(span(report, 1) - 1) < 0.005, report.ok ? `${span(report, 1).toFixed(3)} m long` : 'no frame']],
    },
    {
        name: 'build-sawhorse',
        files: {},
        prompt: 'Write sawhorse.py: a sawhorse with two feet resting on the ground, a post standing on each foot, '
            + 'and a beam across the tops of the posts, all joined with mortise and tenon joints.',
        target: 'sawhorse.py',
        checks: [builds, timbers(5), holdsTogether,
            (report) => {
                const lowest = report.ok ? Math.min(...report.timbers.map((t) => t.min[2])) : NaN;
                return [Math.abs(lowest) < 0.005, report.ok ? `lowest point at z = ${lowest.toFixed(3)} m` : 'no frame'];
            }],
    },
];

module.exports = { TASKS };
