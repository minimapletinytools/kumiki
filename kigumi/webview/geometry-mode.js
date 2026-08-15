(function (globalScope) {
    'use strict';
    // GeometryMode owns the mapping from a viewer geometryMode identifier to the
    // vertex/index arrays a mesh payload carries for it. Accessories and unknown
    // modes always fall back to the base actual-geometry arrays. Every helper
    // here is pure and DOM-free so it can be unit tested directly via require().

    const VALID_MODES = new Set(['actual', 'perfectTimberWithin', 'perfectBoxNoJoints', 'roughBoxNoJoints']);
    const DEFAULT_MODE = 'actual';

    // Non-'actual' modes each read from a distinct pair of optional payload
    // fields. 'perfectTimberWithin' additionally requires the runner-computed
    // hasActualGeometryDifferentFromPerfect flag (it's only sent for
    // non-rectangular timbers); the two no-joints box modes have no such flag --
    // presence of both arrays is the signal, since the runner builds them
    // unconditionally for every timber.
    const MODE_FIELDS = {
        perfectTimberWithin: {
            verticesKey: 'perfectTimberWithinVertices',
            indicesKey: 'perfectTimberWithinIndices',
            requiresFlag: 'hasActualGeometryDifferentFromPerfect',
        },
        perfectBoxNoJoints: {
            verticesKey: 'perfectBoxNoJointsVertices',
            indicesKey: 'perfectBoxNoJointsIndices',
        },
        roughBoxNoJoints: {
            verticesKey: 'roughBoxNoJointsVertices',
            indicesKey: 'roughBoxNoJointsIndices',
        },
    };

    // Always returns the SAME array references stored on `mesh` (never copies),
    // so callers can compare by reference to detect an actual mesh swap.
    function selectMeshBuffers(mesh, memberType, geometryMode) {
        const fallback = {
            vertices: (mesh && mesh.vertices) || [],
            indices: (mesh && mesh.indices) || [],
        };
        if (!mesh || memberType !== 'timber') {
            return fallback;
        }
        const fields = MODE_FIELDS[geometryMode];
        if (!fields) {
            return fallback;
        }
        if (fields.requiresFlag && !mesh[fields.requiresFlag]) {
            return fallback;
        }
        if (!Array.isArray(mesh[fields.verticesKey]) || !Array.isArray(mesh[fields.indicesKey])) {
            return fallback;
        }
        return { vertices: mesh[fields.verticesKey], indices: mesh[fields.indicesKey] };
    }

    // True when swapping from modeA to modeB would actually change which
    // vertex/index arrays get rendered for this mesh (by reference, matching
    // selectMeshBuffers' no-copy guarantee) -- e.g. to decide whether stale
    // CSG/feature sub-selections need to be dropped.
    function meshBuffersDifferBetweenModes(mesh, memberType, modeA, modeB) {
        if (modeA === modeB) {
            return false;
        }
        const a = selectMeshBuffers(mesh, memberType, modeA);
        const b = selectMeshBuffers(mesh, memberType, modeB);
        return a.vertices !== b.vertices || a.indices !== b.indices;
    }

    const GeometryMode = {
        VALID_MODES,
        DEFAULT_MODE,
        selectMeshBuffers,
        meshBuffersDifferBetweenModes,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { GeometryMode };
    }
    globalScope.GeometryMode = GeometryMode;
})(typeof window !== 'undefined' ? window : globalThis);
