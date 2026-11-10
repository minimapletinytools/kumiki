const { describeFrame, formatFrameDescription, numberOf } = require('../frame-description');

// As runner.py serialize_frame writes a timber: sympy values as strings.
const timber = (name, bottom, length, [width, height], lengthDir, widthDir) => {
    const cross = [lengthDir[1] * widthDir[2] - lengthDir[2] * widthDir[1], lengthDir[2] * widthDir[0] - lengthDir[0] * widthDir[2],
        lengthDir[0] * widthDir[1] - lengthDir[1] * widthDir[0]];
    return { name, bottom_position: bottom, length, width, height, length_direction: lengthDir, width_direction: widthDir, height_direction: cross };
};

test('a sawhorse whose legs miss the beam falls into two groups', () => {
    const frame = { name: 'Behemoth', timbers: [
        timber('runner', ['0', '-7/10', '1/10'], '7/5', ['1/5', '1/5'], [0, 1, 0], [1, 0, 0]),
        timber('leg', ['0', '2/5', '1/5'], '9/10', ['1/5', '1/5'], [0, 0, 1], [1, 0, 0]),
        timber('beam', ['-6/5', '0', '6/5'], '12/5', ['3/10', '3/10'], [1, 0, 0], [0, 1, 0]),
    ] };
    const described = describeFrame(frame);

    expect(described.timbers[0]).toMatchObject({ name: 'runner', min: [-0.1, -0.7, 0], max: [0.1, 0.7, 0.2], touches: ['leg'] });
    expect(described.timbers[1]).toMatchObject({ min: [-0.1, 0.3, 0.2], max: [0.1, 0.5, 1.1], touches: ['runner'] });
    expect(described.groups).toEqual([['runner', 'leg'], ['beam']]);
    expect(described.note).toContain('2 groups');
});

test('timbers that meet are one group; a position that is not a plain number is said so', () => {
    const frame = { timbers: [
        timber('sill', ['0', '0', '0'], '1', ['1/10', '1/10'], [0, 1, 0], [1, 0, 0]),
        timber('post', ['0', '1/2', '1/20'], '1', ['1/10', '1/10'], [0, 0, 1], [1, 0, 0]),
        timber('brace', ['sqrt(2)/2', '0', '0'], '1', ['1/10', '1/10'], [0, 0, 1], [1, 0, 0]),
    ] };
    const described = describeFrame(frame);
    expect(described.timbers[2].box).toMatch(/unknown/);
    expect(described.groups[0]).toEqual(['sill', 'post']);
    expect(numberOf('-3/2')).toBe(-1.5);
    expect(numberOf(0.25)).toBe(0.25);
});

test("a timber's box is its cut mesh's, so a tenon reaching past its end meets the timber it enters", () => {
    const frame = { timbers: [
        timber('foot', ['0', '-1/2', '0'], '1', ['1/10', '1/10'], [0, 1, 0], [1, 0, 0]),
        timber('post', ['0', '0', '1/10'], '1', ['1/10', '1/10'], [0, 0, 1], [1, 0, 0]),
    ] };
    // The post's mesh, with its tenon down into the foot: z from 0 (the tenon's tip) to 1.1.
    const geometry = { meshes: [{ memberKey: 'post#0', vertices: [-0.05, -0.05, 0, 0.05, 0.05, 1.1] }] };

    expect(describeFrame(frame).groups).toHaveLength(2);
    const cut = describeFrame(frame, geometry);
    expect(cut.timbers[1]).toMatchObject({ min: [-0.05, -0.05, 0], max: [0.05, 0.05, 1.1], touches: ['foot'] });
    expect(cut.groups).toEqual([['foot', 'post']]);
});

test('each face looks along a world axis, or along a vector for a timber at an angle; the ends are the centres', () => {
    const frame = { timbers: [
        timber('beam', ['0', '0', '1/20'], '1', ['1/10', '1/10'], [1, 0, 0], [0, 1, 0]),
        timber('brace', ['0', '0', '0'], '1', ['1/10', '1/10'], ['sqrt(2)/2', 0, 0.7071], [0, 1, 0]),
    ] };
    const [beam, brace] = describeFrame(frame).timbers;
    expect(beam.faces).toEqual({ TOP: '+X', BOTTOM: '-X', RIGHT: '+Y', LEFT: '-Y', FRONT: '+Z', BACK: '-Z' });
    expect(beam).toMatchObject({ bottom: [0, 0, 0.05], top: [1, 0, 0.05] });
    expect(brace.faces.RIGHT).toBe('+Y');
    expect(brace.faces.TOP).toBe('unknown');
});

test("a timber's joints come from the layers tree, by the keys of the timbers they join", () => {
    const frame = { name: 'Pair', timbers: [
        timber('post', ['0', '0', '1/10'], '1', ['1/10', '1/10'], [0, 0, 1], [1, 0, 0]),
        timber('sill', ['0', '-1/2', '1/20'], '1', ['1/10', '1/10'], [0, 1, 0], [1, 0, 0]),
    ] };
    const layers = { timbers: [{ kumikiEphemeralId: 7, memberKey: 'post#0' }, { kumikiEphemeralId: 8, memberKey: 'sill#0' }],
        joints: [{ name: 'post foot', jointType: 'mortise_and_tenon', members: [{ timberKumikiEphemeralId: 7 }, { timberKumikiEphemeralId: 8 }] }] };
    const described = describeFrame(frame, null, layers);
    expect(described.timbers[0].joints).toEqual([{ name: 'post foot', type: 'mortise_and_tenon', with: ['sill'] }]);
    expect(described.joints).toEqual([{ name: 'post foot', type: 'mortise_and_tenon', timbers: ['post', 'sill'] }]);

    const yaml = formatFrameDescription(described);
    expect(yaml).toContain('frame: Pair');
    expect(yaml).toContain('    faces: {TOP: +Z, BOTTOM: -Z, RIGHT: +X, LEFT: -X, FRONT: +Y, BACK: -Y}');
    expect(yaml).toContain('      - {type: mortise_and_tenon, name: post foot, with: [sill]}');
    expect(yaml).toContain('joints: 1');
    expect(yaml).toContain('connected: true');
});

test('a frame without joints says how to get them, and one that falls apart lists its groups', () => {
    const frame = { timbers: [
        timber('a', ['0', '0', '0'], '1', ['1/10', '1/10'], [0, 0, 1], [1, 0, 0]),
        timber('b: far', ['5', '0', '0'], '1', ['1/10', '1/10'], [0, 0, 1], [1, 0, 0]),
    ] };
    const yaml = formatFrameDescription(describeFrame(frame));
    expect(yaml).toContain('connected: false');
    expect(yaml).toContain('joints: 0  # none in the frame');
    expect(yaml).toContain('groups:\n  - [a]\n  - ["b: far"]');
});
