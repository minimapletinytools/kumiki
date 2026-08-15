const { GeometryMode } = require('../webview/geometry-mode');

const { VALID_MODES, DEFAULT_MODE, selectMeshBuffers, meshBuffersDifferBetweenModes } = GeometryMode;

function baseMesh(extra = {}) {
    return {
        vertices: [0, 0, 0, 1, 1, 1],
        indices: [0, 1, 2],
        ...extra,
    };
}

describe('GeometryMode.VALID_MODES / DEFAULT_MODE', () => {
    test('contains the four known modes', () => {
        expect([...VALID_MODES].sort()).toEqual(
            ['actual', 'perfectBoxNoJoints', 'perfectTimberWithin', 'roughBoxNoJoints'].sort()
        );
    });

    test('default mode is actual', () => {
        expect(DEFAULT_MODE).toBe('actual');
    });
});

describe('selectMeshBuffers', () => {
    test('null/undefined mesh falls back to empty arrays', () => {
        expect(selectMeshBuffers(null, 'timber', 'actual')).toEqual({ vertices: [], indices: [] });
        expect(selectMeshBuffers(undefined, 'timber', 'perfectTimberWithin')).toEqual({ vertices: [], indices: [] });
    });

    test('accessory always falls back to actual geometry regardless of mode', () => {
        const mesh = baseMesh({
            hasActualGeometryDifferentFromPerfect: true,
            perfectTimberWithinVertices: [9, 9, 9],
            perfectTimberWithinIndices: [0],
            perfectBoxNoJointsVertices: [8, 8, 8],
            perfectBoxNoJointsIndices: [0],
        });
        for (const mode of VALID_MODES) {
            const result = selectMeshBuffers(mesh, 'accessory', mode);
            expect(result.vertices).toBe(mesh.vertices);
            expect(result.indices).toBe(mesh.indices);
        }
    });

    test('unknown geometry mode falls back to actual geometry', () => {
        const mesh = baseMesh();
        const result = selectMeshBuffers(mesh, 'timber', 'notARealMode');
        expect(result.vertices).toBe(mesh.vertices);
        expect(result.indices).toBe(mesh.indices);
    });

    test('actual mode always uses base vertices/indices', () => {
        const mesh = baseMesh({
            hasActualGeometryDifferentFromPerfect: true,
            perfectTimberWithinVertices: [9, 9, 9],
            perfectTimberWithinIndices: [0],
        });
        const result = selectMeshBuffers(mesh, 'timber', 'actual');
        expect(result.vertices).toBe(mesh.vertices);
        expect(result.indices).toBe(mesh.indices);
    });

    describe('perfectTimberWithin', () => {
        test('respects the flag and array presence together', () => {
            const mesh = baseMesh({
                hasActualGeometryDifferentFromPerfect: true,
                perfectTimberWithinVertices: [9, 9, 9],
                perfectTimberWithinIndices: [0],
            });
            const result = selectMeshBuffers(mesh, 'timber', 'perfectTimberWithin');
            expect(result.vertices).toBe(mesh.perfectTimberWithinVertices);
            expect(result.indices).toBe(mesh.perfectTimberWithinIndices);
        });

        test('falls back when the flag is false even if arrays are present', () => {
            const mesh = baseMesh({
                hasActualGeometryDifferentFromPerfect: false,
                perfectTimberWithinVertices: [9, 9, 9],
                perfectTimberWithinIndices: [0],
            });
            const result = selectMeshBuffers(mesh, 'timber', 'perfectTimberWithin');
            expect(result.vertices).toBe(mesh.vertices);
            expect(result.indices).toBe(mesh.indices);
        });

        test('falls back when arrays are absent even if the flag is true', () => {
            const mesh = baseMesh({ hasActualGeometryDifferentFromPerfect: true });
            const result = selectMeshBuffers(mesh, 'timber', 'perfectTimberWithin');
            expect(result.vertices).toBe(mesh.vertices);
            expect(result.indices).toBe(mesh.indices);
        });
    });

    describe('perfectBoxNoJoints / roughBoxNoJoints', () => {
        test('use their own arrays when present, with no flag required', () => {
            const mesh = baseMesh({
                perfectBoxNoJointsVertices: [1, 2, 3],
                perfectBoxNoJointsIndices: [0],
                roughBoxNoJointsVertices: [4, 5, 6],
                roughBoxNoJointsIndices: [0],
            });
            const perfectResult = selectMeshBuffers(mesh, 'timber', 'perfectBoxNoJoints');
            expect(perfectResult.vertices).toBe(mesh.perfectBoxNoJointsVertices);
            expect(perfectResult.indices).toBe(mesh.perfectBoxNoJointsIndices);

            const roughResult = selectMeshBuffers(mesh, 'timber', 'roughBoxNoJoints');
            expect(roughResult.vertices).toBe(mesh.roughBoxNoJointsVertices);
            expect(roughResult.indices).toBe(mesh.roughBoxNoJointsIndices);
        });

        test('fall back cleanly when their arrays are absent', () => {
            const mesh = baseMesh();
            expect(selectMeshBuffers(mesh, 'timber', 'perfectBoxNoJoints')).toEqual({
                vertices: mesh.vertices,
                indices: mesh.indices,
            });
            expect(selectMeshBuffers(mesh, 'timber', 'roughBoxNoJoints')).toEqual({
                vertices: mesh.vertices,
                indices: mesh.indices,
            });
        });
    });
});

describe('meshBuffersDifferBetweenModes', () => {
    test('same mode is always false', () => {
        const mesh = baseMesh({
            perfectBoxNoJointsVertices: [1],
            perfectBoxNoJointsIndices: [0],
        });
        for (const mode of VALID_MODES) {
            expect(meshBuffersDifferBetweenModes(mesh, 'timber', mode, mode)).toBe(false);
        }
    });

    test('accessory is always false, regardless of mode pair', () => {
        const mesh = baseMesh({
            hasActualGeometryDifferentFromPerfect: true,
            perfectTimberWithinVertices: [9],
            perfectTimberWithinIndices: [0],
            perfectBoxNoJointsVertices: [1],
            perfectBoxNoJointsIndices: [0],
        });
        expect(meshBuffersDifferBetweenModes(mesh, 'accessory', 'actual', 'perfectTimberWithin')).toBe(false);
        expect(meshBuffersDifferBetweenModes(mesh, 'accessory', 'perfectBoxNoJoints', 'roughBoxNoJoints')).toBe(false);
    });

    test('a mesh with only base data never differs between any mode pair', () => {
        const mesh = baseMesh();
        expect(meshBuffersDifferBetweenModes(mesh, 'timber', 'actual', 'perfectTimberWithin')).toBe(false);
        expect(meshBuffersDifferBetweenModes(mesh, 'timber', 'actual', 'perfectBoxNoJoints')).toBe(false);
        expect(meshBuffersDifferBetweenModes(mesh, 'timber', 'perfectBoxNoJoints', 'roughBoxNoJoints')).toBe(false);
    });

    test('true between actual and perfectTimberWithin when the alternate mesh is present', () => {
        const mesh = baseMesh({
            hasActualGeometryDifferentFromPerfect: true,
            perfectTimberWithinVertices: [9, 9, 9],
            perfectTimberWithinIndices: [0],
        });
        expect(meshBuffersDifferBetweenModes(mesh, 'timber', 'actual', 'perfectTimberWithin')).toBe(true);
    });

    test('true between actual and either no-joints box mode when present', () => {
        const mesh = baseMesh({
            perfectBoxNoJointsVertices: [1, 2, 3],
            perfectBoxNoJointsIndices: [0],
            roughBoxNoJointsVertices: [4, 5, 6],
            roughBoxNoJointsIndices: [0],
        });
        expect(meshBuffersDifferBetweenModes(mesh, 'timber', 'actual', 'perfectBoxNoJoints')).toBe(true);
        expect(meshBuffersDifferBetweenModes(mesh, 'timber', 'actual', 'roughBoxNoJoints')).toBe(true);
    });

    test('true between the two no-joints box modes when both are present', () => {
        const mesh = baseMesh({
            perfectBoxNoJointsVertices: [1, 2, 3],
            perfectBoxNoJointsIndices: [0],
            roughBoxNoJointsVertices: [4, 5, 6],
            roughBoxNoJointsIndices: [0],
        });
        expect(meshBuffersDifferBetweenModes(mesh, 'timber', 'perfectBoxNoJoints', 'roughBoxNoJoints')).toBe(true);
    });
});
