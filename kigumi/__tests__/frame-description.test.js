const { describeFrame, numberOf } = require('../frame-description');

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
