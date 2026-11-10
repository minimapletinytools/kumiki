/**
 * The agent evals' tasks: each a project's starting files, what the user asks (one turn per prompt),
 * the file it should leave building, and checks on how it came out: check(report, project), where
 * `report` is build_frame.py's and `project` has read(file), the last turn's `reply`, and `tools`, the
 * tool calls the whole task took. Each task's last check is a budget of tool calls: one that gets
 * there slowly fails.
 */

const fs = require('fs');
const path = require('path');

const STRUCTURES = path.join(__dirname, '..', '..', '..', 'patterns', 'structures');
const STARTER = fs.readFileSync(path.join(STRUCTURES, 'my_cute_frame.py'), 'utf8');
const TINY_HOUSE = fs.readFileSync(path.join(STRUCTURES, 'tinyhouse120.py'), 'utf8');

/** `text` with `before` replaced by `after`, which must be there. */
function changed(text, before, after) {
    if (!text.includes(before)) throw new Error(`The starter frame no longer has: ${before}`);
    return text.replace(before, after);
}

const builds = (report) => [report.ok, report.ok ? 'it builds' : `it fails: ${report.error}`];
const holdsTogether = (report) => [report.ok && report.groups.length === 1,
    report.ok ? `${report.groups.length} group${report.groups.length === 1 ? '' : 's'} of touching timbers` : 'no frame'];
const timbers = (count) => (report) => [report.ok && report.timbers.length === count, `${report.ok ? report.timbers.length : 0} timbers, ${count} wanted`];
const unchanged = (file, content) => (_report, project) => [project.read(file) === content, `${file} ${project.read(file) === content ? 'unchanged' : 'changed'}`];
const atMostTools = (count) => (_report, project) => [project.tools <= count, `${project.tools} tool calls, at most ${count}`];
const mentions = (file, pattern, said) => (_report, project) => [pattern.test(project.read(file)), said];
/** Timbers whose bottom is on the ground (z = 0). */
const onGround = (report) => (report.ok ? report.timbers.filter((t) => Math.abs(t.min[2]) < 0.005).length : 0);
/** Lines of `file` that differ from `original`, compared line by line. */
const linesChanged = (file, original, most) => (_report, project) => {
    const now = project.read(file).split('\n');
    const was = original.split('\n');
    const changedLines = Math.abs(now.length - was.length) + was.filter((line, i) => now[i] !== line).length;
    return [changedLines <= most, `${changedLines} line${changedLines === 1 ? '' : 's'} changed, at most ${most}`];
};
const span = (report, axis) => Math.max(...report.timbers.map((t) => t.max[axis])) - Math.min(...report.timbers.map((t) => t.min[axis]));

const BROKEN_FACE = changed(STARTER, 'front_face_on_butt_timber=TimberLongFace.FRONT', 'front_face_on_butt_timber=TimberLongFace.RIGHT');

// A drop-in dovetail turned the wrong way, deep in a big file.
const TINY_HOUSE_LINE = '                    front_face_on_butt_timber=TimberLongFace.RIGHT,\n                ),\n                receiving_timber_shoulder_inset=floor_joist_dovetail_shoulder_inset,';
const BROKEN_TINY_HOUSE = changed(TINY_HOUSE, TINY_HOUSE_LINE, TINY_HOUSE_LINE.replace('RIGHT', 'FRONT'));

const TASKS = [
    {
        name: 'fix-attribute',
        files: { 'frame.py': changed(STARTER, 'cross_length = side_spacing',
            'cross_length = right_side.bottom_position[0] - left_side.bottom_position[0]') },
        prompts: ['frame.py fails to build, can you fix it?'],
        target: 'frame.py',
        checks: [builds, timbers(4), holdsTogether, atMostTools(12)],
    },
    {
        name: 'fix-face',
        files: { 'frame.py': BROKEN_FACE },
        prompts: ['frame.py fails to build, can you fix it?'],
        target: 'frame.py',
        checks: [builds, timbers(4), holdsTogether, atMostTools(12)],
    },
    {
        name: 'change',
        files: { 'frame.py': STARTER },
        prompts: ['In frame.py, make the frame 1 m long instead of 600 mm, and add a third cross timber across the middle, '
            + 'joined to the sides like the other two.'],
        target: 'frame.py',
        checks: [builds, timbers(5), holdsTogether,
            (report) => [report.ok && Math.abs(span(report, 1) - 1) < 0.005, report.ok ? `${span(report, 1).toFixed(3)} m long` : 'no frame'], atMostTools(20)],
    },
    {
        name: 'build-sawhorse',
        files: {},
        prompts: ['Write sawhorse.py: a sawhorse with two feet resting on the ground, a post standing on each foot, '
            + 'and a beam across the tops of the posts, all joined with mortise and tenon joints.'],
        target: 'sawhorse.py',
        checks: [builds, timbers(5), holdsTogether,
            (report) => {
                const lowest = report.ok ? Math.min(...report.timbers.map((t) => t.min[2])) : NaN;
                return [Math.abs(lowest) < 0.005, report.ok ? `lowest point at z = ${lowest.toFixed(3)} m` : 'no frame'];
            }, atMostTools(40)],
    },
    {
        name: 'question',
        files: { 'frame.py': STARTER },
        prompts: ['How many timbers does frame.py make, and how are they joined?'],
        target: 'frame.py',
        checks: [builds, unchanged('frame.py', STARTER),
            (_report, project) => [/\b(4|four)\b/i.test(project.reply), 'the reply gives the count'], atMostTools(5)],
    },
    {
        // A question about a failure: find the cause and say it, without changing the file.
        name: 'explain-error',
        files: { 'frame.py': BROKEN_FACE },
        prompts: ['Why does frame.py fail to build? Just explain, don\'t change anything.'],
        target: 'frame.py',
        checks: [unchanged('frame.py', BROKEN_FACE),
            (_report, project) => [/front_face_on_butt_timber|\bRIGHT\b/.test(project.reply), 'the reply names the face given'],
            (_report, project) => [/\b(FRONT|BACK)\b/.test(project.reply), 'the reply says which face would work'], atMostTools(12)],
    },
    {
        name: 'two-turns',
        files: { 'frame.py': STARTER },
        prompts: ['In frame.py, make the frame 1 m long instead of 600 mm.',
            'Now add a third cross timber across the middle, joined to the sides like the other two.'],
        target: 'frame.py',
        checks: [builds, timbers(5), holdsTogether,
            (report) => [report.ok && Math.abs(span(report, 1) - 1) < 0.005, report.ok ? `${span(report, 1).toFixed(3)} m long` : 'no frame'], atMostTools(20)],
    },    {
        name: 'fix-big-file',
        files: { 'tinyhouse.py': BROKEN_TINY_HOUSE },
        prompts: ['tinyhouse.py fails to build, can you fix it?'],
        target: 'tinyhouse.py',
        checks: [builds, timbers(75), holdsTogether, linesChanged('tinyhouse.py', TINY_HOUSE, 2), atMostTools(15)],
    },
    {
        name: 'build-stool',
        files: {},
        prompts: ['Write stool.py: a small stool with three legs standing on the ground and a seat on top, '
            + 'each leg joined into the seat with a mortise and tenon.'],
        target: 'stool.py',
        checks: [builds, holdsTogether, (report) => [onGround(report) === 3, `${onGround(report)} timbers on the ground, 3 wanted`],
            atMostTools(40)],
    },
    {
        name: 'build-bookshelf',
        files: {},
        prompts: ['Write bookshelf.py: a simple bookshelf, two upright sides with three shelves between them, '
            + 'each shelf joined to the sides with dovetails.'],
        target: 'bookshelf.py',
        checks: [builds, timbers(5), holdsTogether, mentions('bookshelf.py', /dovetail/i, 'it uses a dovetail joint'), atMostTools(40)],
    },
];

module.exports = { TASKS };
