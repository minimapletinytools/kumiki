// The lines only a drawing's views draw over its timbers.
//
// Each perfect face the rough stock has no face for (ptw.*), dotted, and each centerplane, dotted
// in its own colour -- both planes the runner sends cropped to the cut timber (perfectFaces and
// centerplanes on a member's mesh), so a perfect face ends at a shoulder and a tenon, being the
// timber's own, gets none. They lie inside their timber, so each is clipped to it with the member
// id pass (member-id-buffer.js): hidden by another timber in front, never by its own faces.
//
// Hovering or selecting one of those planes lights it through the usual highlight, from the
// outline the runner sends for it (highlightEdgeSegments); nothing here.

// A dot's diameter, in pixels: the line's width.
const LINE_WIDTH_PX = 3;
// Dot to dot, in world units (metres), as LineMaterial dashes are.
const DOT = 0.0008;
const DOT_GAP = 0.004;
const PERFECT_FACE_COLOR = 0x2f6fd0;
const CENTERPLANE_COLOR = 0xd0582f;
// How square to the view a plane may be and still be drawn: seen face-on, it is not.
const FACE_ON_DOT = 1 - 1e-3;

// LineMaterial's dash test, which cuts the line into rectangles.
const SQUARE_DASH = 'if ( mod( vLineDistance + dashOffset, dashSize + gapSize ) > dashSize ) discard; // todo - FIX';
// A round dot instead, centred on each dash, as wide as the line: the distance to the nearest
// centre along the line, in pixels (vLineDistance's change per pixel), and across it.
const ROUND_DOT = `
            float dotPeriod = dashSize + gapSize;
            float dotAlong = mod( vLineDistance + dashOffset + 0.5 * dotPeriod, dotPeriod ) - 0.5 * dotPeriod;
            float dotPerPixel = max( length( vec2( dFdx( vLineDistance ), dFdy( vLineDistance ) ) ), 1e-9 );
            vec2 dotOffset = vec2( dotAlong / dotPerPixel, vUv.x * 0.5 * linewidth );
            if ( dot( dotOffset, dotOffset ) > 0.25 * linewidth * linewidth ) discard;`;

/** A dashed LineMaterial fragment shader drawing round dots rather than square dashes. */
function roundDotShader(source) {
    if (!source.includes(SQUARE_DASH)) {
        throw new Error('drawing-overlays: the line shader has no dash test to replace');
    }
    return source
        .replace('uniform float opacity;', 'uniform float opacity;\n\t\tuniform float linewidth;')
        .replace(SQUARE_DASH, ROUND_DOT);
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
        const dotted = (color) => {
            const material = new THREE.LineMaterial({
                color,
                linewidth: LINE_WIDTH_PX,
                resolution,
                dashed: true,
                dashSize: DOT,
                gapSize: DOT_GAP,
                // Inside the rough stock, so drawn through it; the id pass hides what should be.
                depthTest: false,
            });
            // This LineMaterial dashes only with the define set; `dashed` alone does nothing.
            material.defines.USE_DASH = '';
            material.fragmentShader = roundDotShader(material.fragmentShader);
            // dFdx / dFdy: built in on WebGL2, an extension on WebGL1.
            material.extensions.derivatives = true;
            return material;
        };
        // What every member's lines are copied from.
        this.materials = { perfect: dotted(PERFECT_FACE_COLOR), centerplane: dotted(CENTERPLANE_COLOR) };
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
            object.renderOrder = 11;
            object.visible = false;
            lines.push({ object, normal: new THREE.Vector3(...plane.normal), option });
        };
        for (const face of mesh.perfectFaces || []) {
            add(face, this.materials.perfect, 'showDrawingPerfectFaces');
        }
        for (const centerplane of mesh.centerplanes || []) {
            add(centerplane, this.materials.centerplane, 'showDrawingCenterplanes');
        }
        return lines;
    }

    /**
     * Show or hide every member's lines for one viewport, before it is drawn. `options` answers
     * each line's display option by name. Returns whether any is shown -- and so whether the
     * viewport needs its member id pass.
     */
    showFor(bundles, camera, { inDrawing, options }) {
        const look = camera.getWorldDirection(this._look);
        let any = false;
        for (const bundle of bundles) {
            for (const line of bundle.drawingLines || []) {
                line.object.visible = Boolean(inDrawing && options[line.option]) && drawnFacing(line.normal, look);
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

const KigumiDrawingOverlays = { DrawingOverlays, drawnFacing, anchoredLineDistances, roundDotShader, FACE_ON_DOT };

export { DrawingOverlays, drawnFacing, anchoredLineDistances, roundDotShader, FACE_ON_DOT };
