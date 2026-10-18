(function (globalScope) {
    'use strict';
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

    const LINE_WIDTH_PX = 2;
    // In world units (metres), as LineMaterial dashes are: a dot is a dash shorter than the line is wide.
    const DOT = 0.0008;
    const DOT_GAP = 0.004;
    const PERFECT_FACE_COLOR = 0x2f6fd0;
    const CENTERPLANE_COLOR = 0xd0582f;
    // How square to the view a plane may be and still be drawn: seen face-on, it is not.
    const FACE_ON_DOT = 1 - 1e-3;

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
                object.computeLineDistances();
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

    const KigumiDrawingOverlays = { DrawingOverlays, drawnFacing, FACE_ON_DOT };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiDrawingOverlays;
    }
    globalScope.KigumiDrawingOverlays = KigumiDrawingOverlays;
})(typeof window !== 'undefined' ? window : globalThis);
