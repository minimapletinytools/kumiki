(function (globalScope) {
    'use strict';
    // The controls that exist to move or describe a camera: the orientation
    // cube in the corner, and the orb at the point the camera orbits.
    //
    // A scene declares which of them it wants -- the 3D view asks for all of
    // them, a drawing for none -- so they are gathered here rather than woven
    // through the viewer, where turning them off would mean finding every
    // piece again.
    //
    // THREE arrives as an argument: this is a classic script, loaded before the
    // module that imports it.

    // The cube's faces in BoxGeometry's material order: +X, -X, +Y, -Y, +Z, -Z.
    // The compass line follows kumiki's own convention (see rule.py): +X points
    // east and +Y points north, which puts north on the BACK of the cube.
    const GIZMO_FACES = Object.freeze([
        { lines: ['right', 'east', '+x'], background: '#c9d6ea' },
        { lines: ['left', 'west', '-x'], background: '#bfcee4' },
        { lines: ['back', 'north', '+y'], background: '#d6deee' },
        { lines: ['front', 'south', '-y'], background: '#c4d2e8' },
        { lines: ['top', '+z'], background: '#bccbe2' },
        { lines: ['bottom', '-z'], background: '#b6c6df' },
    ]);

    const FACE_TEXTURE_PX = 256;
    const FACE_BORDER_INSET_PX = 16;
    const FACE_BORDER_WIDTH_PX = 10;
    const FACE_TEXT_GAP_PX = 8;
    const FACE_LINE_HEIGHT = 1.12;

    // Where the orbit gizmo's axis labels sit and what they look like. The
    // colours are its rings': each ring turns about one axis, so the label on
    // that axis reads as the ring's own.
    const ORBIT_AXIS_LABELS = Object.freeze([
        { text: '+x', direction: [1, 0, 0], color: '#ff8fa3' },
        { text: '+y', direction: [0, 1, 0], color: '#7fc8f8' },
        { text: '+z', direction: [0, 0, 1], color: '#95d5b2' },
    ]);
    // Just clear of the rings (radius 1.85 + tube 0.12), in the gizmo's units.
    const ORBIT_LABEL_DISTANCE = 2.5;
    const ORBIT_LABEL_SCALE = 1.2;
    const ORBIT_LABEL_TEXTURE_PX = 128;
    const ORBIT_RING_CONFIGS = Object.freeze([
        { color: 0xff8fa3, rotation: [0, Math.PI / 2, 0] },
        { color: 0x7fc8f8, rotation: [Math.PI / 2, 0, 0] },
        { color: 0x95d5b2, rotation: [0, 0, 0] },
    ]);

    /** How much room a cube face has for text, inside its frame. */
    function faceTextExtent() {
        const inset = FACE_BORDER_INSET_PX + FACE_BORDER_WIDTH_PX / 2 + FACE_TEXT_GAP_PX;
        return FACE_TEXTURE_PX - inset * 2;
    }

    /**
     * The largest size every face can share without touching its frame.
     *
     * Measured rather than hardcoded, so it stays right whichever font the
     * webview resolves, and one size for all six faces rather than the biggest
     * each could take alone -- 'top' would otherwise tower over the three-line
     * faces and the cube would read as sloppy.
     */
    function fitFaceFontSize(context, faces) {
        const REFERENCE_PX = 100;
        const available = faceTextExtent();
        let size = Infinity;
        for (const face of faces) {
            context.font = `600 ${REFERENCE_PX}px Segoe UI`;
            const widest = Math.max(...face.lines.map((line) => context.measureText(line).width));
            const byWidth = widest > 0 ? REFERENCE_PX * (available / widest) : REFERENCE_PX;
            const byHeight = available / (face.lines.length * FACE_LINE_HEIGHT);
            size = Math.min(size, byWidth, byHeight);
        }
        return Math.max(1, Math.floor(size));
    }

    /** Which axis a picked cube face points along, as a unit direction. */
    function faceNormalToAxis(normal) {
        const ax = Math.abs(normal.x);
        const ay = Math.abs(normal.y);
        const az = Math.abs(normal.z);
        if (ax >= ay && ax >= az) {
            return { x: Math.sign(normal.x), y: 0, z: 0 };
        }
        if (ay >= ax && ay >= az) {
            return { x: 0, y: Math.sign(normal.y), z: 0 };
        }
        return { x: 0, y: 0, z: Math.sign(normal.z) };
    }

    /** The orientation cube: its own tiny scene, drawn into its own canvas. */
    class CameraCubeGizmo {
        constructor({ THREE, canvas }) {
            this.THREE = THREE;
            this.canvas = canvas;
            this.raycaster = new THREE.Raycaster();
            this.pointer = new THREE.Vector2();

            this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
            this.renderer.setClearColor(0x000000, 0);

            this.scene = new THREE.Scene();
            this.camera = new THREE.PerspectiveCamera(35, 1, 0.1, 20);

            this.scene.add(new THREE.AmbientLight(0xffffff, 0.82));
            const light = new THREE.DirectionalLight(0xffffff, 0.65);
            light.position.set(2, 2, 3);
            this.scene.add(light);

            const fontSizePx = fitFaceFontSize(
                document.createElement('canvas').getContext('2d'), GIZMO_FACES,
            );
            const materials = GIZMO_FACES.map(
                (face) => this.createFaceMaterial(face.lines, face.background, fontSizePx),
            );
            this.cube = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), materials);
            this.scene.add(this.cube);
            this.resize();
        }

        createFaceMaterial(lines, backgroundColor, fontSizePx) {
            const THREE = this.THREE;
            const canvas = document.createElement('canvas');
            canvas.width = FACE_TEXTURE_PX;
            canvas.height = FACE_TEXTURE_PX;
            const context = canvas.getContext('2d');

            context.fillStyle = backgroundColor;
            context.fillRect(0, 0, canvas.width, canvas.height);

            context.strokeStyle = 'rgba(93, 104, 130, 0.35)';
            context.lineWidth = FACE_BORDER_WIDTH_PX;
            context.strokeRect(
                FACE_BORDER_INSET_PX,
                FACE_BORDER_INSET_PX,
                canvas.width - FACE_BORDER_INSET_PX * 2,
                canvas.height - FACE_BORDER_INSET_PX * 2,
            );

            context.fillStyle = '#39496e';
            context.textAlign = 'center';
            context.textBaseline = 'middle';
            context.font = `600 ${fontSizePx}px Segoe UI`;

            // Centred as a block, so one line sits in the middle and several
            // straddle it.
            const lineHeight = fontSizePx * FACE_LINE_HEIGHT;
            const firstY = canvas.height / 2 - ((lines.length - 1) * lineHeight) / 2;
            lines.forEach((line, index) => {
                context.fillText(line, canvas.width / 2, firstY + index * lineHeight);
            });

            const texture = new THREE.CanvasTexture(canvas);
            texture.needsUpdate = true;
            return new THREE.MeshStandardMaterial({ color: 0xffffff, map: texture });
        }

        resize() {
            const width = Math.max(1, this.canvas.clientWidth);
            const height = Math.max(1, this.canvas.clientHeight);
            this.renderer.setPixelRatio(globalScope.devicePixelRatio || 1);
            this.renderer.setSize(width, height, false);
            this.camera.aspect = width / height;
            this.camera.updateProjectionMatrix();
        }

        /** Point the cube the way the real camera looks, and draw it. */
        render(cameraPosition, orbitCenter) {
            const dx = cameraPosition.x - orbitCenter.x;
            const dy = cameraPosition.y - orbitCenter.y;
            const dz = cameraPosition.z - orbitCenter.z;
            const length = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
            this.camera.position.set((dx / length) * 2.8, (dy / length) * 2.8, (dz / length) * 2.8);
            this.camera.up.set(0, 0, 1);
            this.camera.lookAt(0, 0, 0);
            this.renderer.render(this.scene, this.camera);
        }

        /** The axis of the face at a point on the cube's canvas, or null. */
        axisAtPoint(localX, localY) {
            const width = this.canvas.clientWidth || 1;
            const height = this.canvas.clientHeight || 1;
            this.pointer.x = (localX / width) * 2 - 1;
            this.pointer.y = -((localY / height) * 2 - 1);
            this.raycaster.setFromCamera(this.pointer, this.camera);
            const hits = this.raycaster.intersectObject(this.cube, false);
            if (!hits.length || !hits[0].face) {
                return null;
            }
            return faceNormalToAxis(hits[0].face.normal);
        }

        dispose() {
            this.renderer.dispose();
        }
    }

    /** The orb and rings marking the point the camera orbits about. */
    class OrbitCenterGizmo {
        constructor({ THREE }) {
            this.THREE = THREE;
            const group = new THREE.Group();

            group.add(new THREE.Mesh(
                new THREE.SphereGeometry(1, 20, 20),
                new THREE.MeshBasicMaterial({ color: 0xffd8a8, transparent: true, opacity: 0.96 }),
            ));

            for (const config of ORBIT_RING_CONFIGS) {
                const ring = new THREE.Mesh(
                    new THREE.TorusGeometry(1.85, 0.12, 12, 48),
                    new THREE.MeshBasicMaterial({ color: config.color, transparent: true, opacity: 0.52 }),
                );
                ring.rotation.set(config.rotation[0], config.rotation[1], config.rotation[2]);
                group.add(ring);
            }

            for (const axis of ORBIT_AXIS_LABELS) {
                const label = this.makeAxisLabel(axis.text, axis.color);
                label.position.set(
                    axis.direction[0] * ORBIT_LABEL_DISTANCE,
                    axis.direction[1] * ORBIT_LABEL_DISTANCE,
                    axis.direction[2] * ORBIT_LABEL_DISTANCE,
                );
                group.add(label);
            }

            this.object3d = group;
        }

        /**
         * One axis label.
         *
         * A sprite rather than a mesh: it turns to face the camera on its own,
         * so a label stays readable from wherever the frame is being viewed.
         * Depth tested like everything else, so a label behind a timber stays
         * behind it rather than floating over the frame.
         */
        makeAxisLabel(text, color) {
            const THREE = this.THREE;
            const canvas = document.createElement('canvas');
            canvas.width = ORBIT_LABEL_TEXTURE_PX;
            canvas.height = ORBIT_LABEL_TEXTURE_PX;
            const context = canvas.getContext('2d');

            context.textAlign = 'center';
            context.textBaseline = 'middle';
            context.font = `700 ${Math.round(canvas.height * 0.6)}px Segoe UI`;
            // An outline first, so the label holds up against timber or sky alike.
            context.lineWidth = Math.round(canvas.height * 0.14);
            context.strokeStyle = 'rgba(30, 36, 52, 0.85)';
            context.strokeText(text, canvas.width / 2, canvas.height / 2);
            context.fillStyle = color;
            context.fillText(text, canvas.width / 2, canvas.height / 2);

            const material = new THREE.SpriteMaterial({
                map: new THREE.CanvasTexture(canvas),
                transparent: true,
                depthTest: true,
            });
            const sprite = new THREE.Sprite(material);
            sprite.scale.setScalar(ORBIT_LABEL_SCALE);
            return sprite;
        }

        /** Sit at the orbit centre, sized so it stays legible at any distance. */
        update({ center, orbitDist, visible }) {
            this.object3d.visible = Boolean(visible);
            this.object3d.position.set(center.x, center.y, center.z);
            this.object3d.scale.setScalar(Math.max(0.02, orbitDist * 0.00875));
        }

        dispose() {
            this.object3d.traverse((child) => {
                if (child.geometry) {
                    child.geometry.dispose();
                }
                if (child.material && typeof child.material.dispose === 'function') {
                    // A material does not dispose its own textures, and each
                    // axis label carries a canvas one.
                    if (child.material.map && typeof child.material.map.dispose === 'function') {
                        child.material.map.dispose();
                    }
                    child.material.dispose();
                }
            });
        }
    }

    const KigumiCameraControls = {
        CameraCubeGizmo,
        OrbitCenterGizmo,
        GIZMO_FACES,
        faceTextExtent,
        fitFaceFontSize,
        faceNormalToAxis,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiCameraControls;
    }
    globalScope.KigumiCameraControls = KigumiCameraControls;
})(typeof window !== 'undefined' ? window : globalThis);
