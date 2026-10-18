const { MemberIdBuffer, idToRgb, rgbToId, clipShader } = require('../webview/member-id-buffer');

// Just enough of THREE for the parts that do not draw.
const THREE = { Vector4: class { constructor(...v) { this.v = v; } set(...v) { this.v = v; } } };

describe('member ids', () => {
    test.each([1, 255, 256, 65535, 65536, 1234567])('%i comes back from its colour', (id) => {
        expect(rgbToId(...idToRgb(id))).toBe(id);
    });

    test('each member keeps its id, and ids count from 1 (0 is background)', () => {
        const buffer = new MemberIdBuffer({ THREE, renderer: {} });
        expect(buffer.idFor('a')).toBe(1);
        expect(buffer.idFor('b')).toBe(2);
        expect(buffer.idFor('a')).toBe(1);
    });
});

describe('clipping a line to its member', () => {
    const shader = 'uniform float opacity;\nvoid main() {\n#include <clipping_planes_fragment>\ngl_FragColor = vec4(1.0);\n}';

    test('the test goes in after the line shader clips, its declarations before main', () => {
        const clipped = clipShader(shader);
        expect(clipped.indexOf('uniform sampler2D memberIdMap')).toBeLessThan(clipped.indexOf('void main()'));
        expect(clipped.indexOf('ownMemberId) < 0.5')).toBeGreaterThan(clipped.indexOf('#include <clipping_planes_fragment>'));
    });

    test('a shader with nowhere to put it is refused, not silently left unclipped', () => {
        expect(() => clipShader('void main() {}')).toThrow(/clipping hook/);
    });

    test('every clipped material shares the one id map, and knows its own member', () => {
        const buffer = new MemberIdBuffer({ THREE, renderer: {} });
        const material = (key) => buffer.clipLineMaterial(
            { uniforms: {}, defines: { USE_DASH: '' }, fragmentShader: shader }, key);
        const one = material('a');
        const other = material('b');

        expect(one.uniforms.memberIdMap).toBe(other.uniforms.memberIdMap);
        expect([one.uniforms.ownMemberId.value, other.uniforms.ownMemberId.value]).toEqual([1, 2]);
        expect(one.defines).toEqual({ USE_DASH: '', USE_MEMBER_ID: '' });
    });
});
