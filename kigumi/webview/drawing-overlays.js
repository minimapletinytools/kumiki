// The lines only a drawing's views draw over its timbers.
//
// Each perfect face the rough stock has no face for (ptw.*), dashed, and each centerplane, dashed
// in its own colour -- both planes the runner sends cropped to the cut timber (perfectFaces and
// centerplanes on a member's mesh), so a perfect face ends at a shoulder and a tenon, being the
// timber's own, gets none. They lie inside their timber, so each is clipped to it with the member
// id pass (member-id-buffer.js): hidden by another timber in front, never by its own faces.
//
// And each reference face's outline, solid in the face's own tint, so a reference face seen
// edge-on still shows which edges are its (with the reference edges' option), in a deeper shade.
//
// Hovering or selecting one of those planes lights it through the usual highlight, from the
// outline the runner sends for it (highlightEdgeSegments); nothing here.

// The line's width, in pixels.
const LINE_WIDTH_PX = 3;
// A dash and the gap after it, in line widths: on screen, so the dashing looks the same at any zoom.
const DASH = 4;
const GAP = 2;
const PERFECT_FACE_COLOR = 0x2f6fd0;
const CENTERPLANE_COLOR = 0xd0582f;
// How square to the view a plane may be and still be drawn: seen face-on, it is not.
const FACE_ON_DOT = 1 - 1e-3;

// LineMaterial's dash test, which cuts the line into rectangles.
const SQUARE_DASH = 'if ( mod( vLineDistance + dashOffset, dashSize + gapSize ) > dashSize ) discard; // todo - FIX';
// Dashes with round ends instead, measured in the pixels drawn both ways: along the line from
// vLineDistance's change per pixel, across it from vUv.x's (-1 to 1 edge to edge). A width taken
// from linewidth stretched each dash across the line wherever a drawing's sheet is zoomed.
const dashFragment = (dash, gap) => `
            float dashRadius = 1.0 / max( length( vec2( dFdx( vUv.x ), dFdy( vUv.x ) ) ), 1e-9 );
            float dashPerPixel = max( length( vec2( dFdx( vLineDistance ), dFdy( vLineDistance ) ) ), 1e-9 );
            float dashPeriod = ${(2 * (dash + gap)).toFixed(2)} * dashRadius;
            float dashAlong = mod( ( vLineDistance + dashOffset ) / dashPerPixel + 0.5 * dashPeriod, dashPeriod ) - 0.5 * dashPeriod;
            float dashBeyond = max( abs( dashAlong ) - ${(dash - 1).toFixed(2)} * dashRadius, 0.0 );
            vec2 dashOffset2 = vec2( dashBeyond, vUv.x * dashRadius );
            if ( dot( dashOffset2, dashOffset2 ) > dashRadius * dashRadius ) discard;`;

/** A dashed LineMaterial fragment shader drawing round-ended dashes measured on screen. */
function roundDashShader(source, dash = DASH, gap = GAP) {
    if (!source.includes(SQUARE_DASH)) {
        throw new Error('drawing-overlays: the line shader has no dash test to replace');
    }
    return source.replace(SQUARE_DASH, dashFragment(dash, gap));
}

/**
 * Where each segment's dots start and end, as LineSegments2 reads them (instanceDistanceStart,
 * instanceDistanceEnd): a point's distance along its line from the world's origin, the line's
 * direction taken one fixed way round. So every segment on one line dots in step whatever its
 * ends or depth -- a plane's front and back edges, which a drawing's view draws on top of each
 * other, show one row of dots rather than two out of step. (computeLineDistances counted from
 * each object's first segment, adding up along the rest.)
 *
 * @param {ArrayLike<number>} positions x, y, z of each segment's start then end
 * @returns {Float32Array} start and end distance per segment
 */
function anchoredLineDistances(positions) {
    const count = Math.floor(positions.length / 6);
    const distances = new Float32Array(2 * count);
    for (let i = 0; i < count; i++) {
        const at = 6 * i;
        let dx = positions[at + 3] - positions[at];
        let dy = positions[at + 4] - positions[at + 1];
        let dz = positions[at + 5] - positions[at + 2];
        const length = Math.hypot(dx, dy, dz);
        if (length > 0) {
            // One way round: the largest component positive.
            const largest = [dx, dy, dz].reduce((a, b) => (Math.abs(b) > Math.abs(a) ? b : a));
            const sign = largest < 0 ? -1 : 1;
            dx = (sign * dx) / length;
            dy = (sign * dy) / length;
            dz = (sign * dz) / length;
        }
        for (let end = 0; end < 2; end++) {
            const p = at + 3 * end;
            distances[2 * i + end] = positions[p] * dx + positions[p + 1] * dy + positions[p + 2] * dz;
        }
    }
    return distances;
}

/**
 * A reference face's tint deepened enough to read as a line: the same hue, a middle lightness.
 * The tints themselves are pastels for filling a face, and as lines they all but vanish.
 *
 * @param {string} hex '#rrggbb'
 * @returns {string} '#rrggbb'
 */
function outlineShade(hex) {
    const [r, g, b] = [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16) / 255);
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const chroma = max - min;
    let hue = 0;
    if (chroma > 0) {
        hue = max === r ? ((g - b) / chroma) % 6 : max === g ? (b - r) / chroma + 2 : (r - g) / chroma + 4;
    }
    hue = (hue * 60 + 360) % 360;
    const saturation = 0.55, lightness = 0.6;
    const c = (1 - Math.abs(2 * lightness - 1)) * saturation;
    const x = c * (1 - Math.abs(((hue / 60) % 2) - 1));
    const m = lightness - c / 2;
    const [r1, g1, b1] = hue < 60 ? [c, x, 0] : hue < 120 ? [x, c, 0] : hue < 180 ? [0, c, x]
        : hue < 240 ? [0, x, c] : hue < 300 ? [x, 0, c] : [c, 0, x];
    return '#' + [r1, g1, b1].map((v) => Math.round((v + m) * 255).toString(16).padStart(2, '0')).join('');
}

/**
 * Whether a plane's outline is drawn, looking along `look`: never seen face-on, where it would
 * only retrace the faces around it. Seen edge-on it is a line; in a view turned off square, the
 * planes draw as a wireframe of the perfect timber within. (Edge-on only, they all vanished at the
 * first touch of a drag, which turns a drawing's camera.)
 */
function drawnFacing(normal, look) {
    return Math.abs(normal.dot(look)) < FACE_ON_DOT;
}

class DrawingOverlays {
    /**
     * @param {object} options
     * @param {object} options.THREE
     * @param {object|null} options.memberIds a MemberIdBuffer, to clip each member's lines by
     * @param {object} options.resolution the renderer's resolution now (LineMaterial needs it)
     */
    constructor({ THREE, memberIds, resolution }) {
        this.THREE = THREE;
        this.memberIds = memberIds;
        const dashed = (color, dash = DASH, gap = GAP) => {
            const material = new THREE.LineMaterial({
                color,
                linewidth: LINE_WIDTH_PX,
                resolution,
                dashed: true,
                // Inside the rough stock, so drawn through it; the id pass hides what should be.
                depthTest: false,
            });
            // This LineMaterial dashes only with the define set; `dashed` alone does nothing.
            material.defines.USE_DASH = '';
            material.fragmentShader = roundDashShader(material.fragmentShader, dash, gap);
            // dFdx / dFdy: built in on WebGL2, an extension on WebGL1.
            material.extensions.derivatives = true;
            return material;
        };
        // What every member's lines are copied from.
        this.materials = { perfect: dashed(PERFECT_FACE_COLOR), centerplane: dashed(CENTERPLANE_COLOR) };
        const xray = dashed(0x554b60, 6, 3);
        xray.linewidth = 2.1;
        xray.transparent = true;
        xray.depthWrite = false;
        this.materials.xray = xray;
        // Coloured per face, the reference face's tint (referenceOutlinesFor).
        this.materials.reference = new THREE.LineMaterial({ linewidth: LINE_WIDTH_PX, resolution, depthTest: false });
        this._look = new THREE.Vector3();
    }

    /**
     * A member's lines, from its mesh payload: [{ object, normal, option }], `option` naming the
     * display option that shows them. Parent each `object` under the member's edges, so it
     * follows the member's visibility and offset.
     */
    linesFor(mesh, memberKey) {
        const THREE = this.THREE;
        const lines = [];
        const add = (plane, shared, option) => {
            const geometry = new THREE.LineSegmentsGeometry();
            geometry.setPositions(plane.positions);
            const object = new THREE.LineSegments2(geometry, this._memberMaterial(shared, memberKey));
            const distances = new THREE.InstancedInterleavedBuffer(anchoredLineDistances(plane.positions), 2, 1);
            geometry.setAttribute('instanceDistanceStart', new THREE.InterleavedBufferAttribute(distances, 1, 0));
            geometry.setAttribute('instanceDistanceEnd', new THREE.InterleavedBufferAttribute(distances, 1, 1));
            object.renderOrder = option === 'drawingXray' ? 9 : 11;
            object.visible = false;
            lines.push({ object, normal: new THREE.Vector3(...plane.normal), option, memberKey,
                measuredAs: plane.feature ? memberKey + '|' + plane.feature : null });
        };
        for (const face of mesh.perfectFaces || []) {
            add(face, this.materials.perfect, 'showDrawingPerfectFaces');
        }
        for (const centerplane of mesh.centerplanes || []) {
            add(centerplane, this.materials.centerplane, 'showDrawingCenterplanes');
        }
        for (const outline of mesh.xrayLines || []) {
            add(outline, this.materials.xray, 'drawingXray');
        }
        return lines;
    }

    /**
     * The outline of each of a member's reference faces, as lines like linesFor's: the edges of
     * the triangles lying on the face's plane that only one of them has. `vertices` and `indices`
     * are the member's mesh, in the world; `planes` its referenceFacePlanes.
     */
    referenceOutlinesFor(vertices, indices, planes, memberKey) {
        const THREE = this.THREE;
        const lines = [];
        const key = (vertex) => [0, 1, 2].map((axis) => vertices[3 * vertex + axis].toFixed(6)).join(',');
        for (const { normal, offset, color } of planes || []) {
            const onFace = (vertex) => Math.abs(vertices[3 * vertex] * normal[0] + vertices[3 * vertex + 1] * normal[1]
                + vertices[3 * vertex + 2] * normal[2] - offset) < 1e-7;
            const edges = new Map();
            for (let i = 0; i < indices.length; i += 3) {
                const corners = [indices[i], indices[i + 1], indices[i + 2]];
                if (!corners.every(onFace)) continue;
                for (let side = 0; side < 3; side++) {
                    const ends = [corners[side], corners[(side + 1) % 3]];
                    const id = ends.map(key).sort().join('|');
                    const seen = edges.get(id);
                    edges.set(id, seen ? { ends, count: seen.count + 1 } : { ends, count: 1 });
                }
            }
            const positions = [];
            for (const { ends, count } of edges.values()) {
                if (count !== 1) continue;
                for (const vertex of ends) positions.push(vertices[3 * vertex], vertices[3 * vertex + 1], vertices[3 * vertex + 2]);
            }
            if (!positions.length) continue;
            const geometry = new THREE.LineSegmentsGeometry();
            geometry.setPositions(positions);
            const material = this._memberMaterial(this.materials.reference, memberKey);
            material.uniforms.diffuse.value = new THREE.Color(outlineShade(color));
            const object = new THREE.LineSegments2(geometry, material);
            object.renderOrder = 11;
            object.visible = false;
            lines.push({ object, normal: new THREE.Vector3(...normal), option: 'highlightReferenceEdges', memberKey,
                measuredAs: null, anyFacing: true });
        }
        return lines;
    }

    /**
     * Show or hide every member's lines for one viewport, before it is drawn. `options` answers
     * each line's display option by name: 'off', 'on', or 'measured' to show only the lines whose
     * `memberKey|feature` is in `measured`, what the viewport's dimensions go to. Returns whether any
     * is shown -- and so whether the viewport needs its member id pass.
     */
    showFor(bundles, camera, { inDrawing, options, xrayMembers, measured }) {
        const look = camera.getWorldDirection(this._look);
        let any = false;
        const wanted = (line) => {
            const mode = options[line.option];
            return mode === 'on' || mode === true || (mode === 'measured' && Boolean(measured?.has(line.measuredAs)));
        };
        for (const bundle of bundles) {
            for (const line of bundle.drawingLines || []) {
                line.object.visible = inDrawing && (line.option === 'drawingXray'
                    ? Boolean(camera.isOrthographicCamera && xrayMembers?.has(line.memberKey)
                        && line.normal.dot(look) < -1 + 1e-8)
                    : wanted(line) && (line.anyFacing || drawnFacing(line.normal, look)));
                any = any || line.object.visible;
            }
        }
        return any;
    }

    /** Keep the lines' pixel width in step with the canvas: every member's copy shares this. */
    setResolution(resolution) {
        for (const material of Object.values(this.materials)) {
            material.resolution = resolution;
        }
    }

    /**
     * A member's own copy of a shared material, clipped to it. Its resolution is the shared one,
     * so setResolution reaches every copy.
     */
    _memberMaterial(shared, memberKey) {
        const material = shared.clone();
        material.uniforms.resolution = shared.uniforms.resolution;
        return this.memberIds ? this.memberIds.clipLineMaterial(material, memberKey) : material;
    }
}

const KigumiDrawingOverlays = { DrawingOverlays, drawnFacing, anchoredLineDistances, roundDashShader, FACE_ON_DOT };

export { DrawingOverlays, drawnFacing, anchoredLineDistances, roundDashShader, outlineShade, FACE_ON_DOT };
