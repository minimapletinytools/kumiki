import { placement, configuration, agentPrompt } from './stl-placement-model.js';

/** Own an isolated placement canvas, transform panel, and their entire event/resource lifetime. */
export class STLPlacementEditor {
    constructor({ parent, data, style, material, background, send, close }) {
        this.data = data;
        this.value = placement(data.placement);
        this.style = style;
        this.send = send;
        this.onClose = close;
        this.mode = 'translation';
        this.material = material;
        this.inputs = [];
        this.abort = new window.AbortController();
        this.root = document.createElement('div');
        this.root.dataset.stlPlacementEditor = '';
        this.root.setAttribute('role', 'dialog');
        this.root.setAttribute('aria-label', 'Place STL');
        this.root.className = 'stl-placement';
        this.root.style.background = background;
        this.stage = document.createElement('div');
        this.stage.className = 'stl-placement-stage';
        this.sidebar = document.createElement('div');
        this.sidebar.className = 'stl-placement-sidebar';
        this.root.append(this.sidebar, this.stage);
        this.suspended = [...parent.children].map(element => [element, element.inert]);
        for (const [element] of this.suspended) element.inert = true;
        parent.append(this.root);
        for (const event of ['mousedown', 'mousemove', 'mouseup', 'pointerdown', 'pointermove', 'pointerup', 'wheel', 'keydown', 'keyup', 'click', 'contextmenu']) {
            this.root.addEventListener(event, e => e.stopPropagation(), { signal: this.abort.signal });
        }
        this.buildPanel();
        this.buildScene();
        this.root.addEventListener('keydown', e => { if (e.key === 'Escape') this.onClose(); }, { signal: this.abort.signal });
        this.resize = new ResizeObserver(() => this.render());
        this.resize.observe(this.stage);
        this.update();
        this.root.tabIndex = -1;
        this.root.focus();
    }

    text(tag, content, parent = this.sidebar) {
        const node = document.createElement(tag);
        node.textContent = content;
        parent.append(node);
        return node;
    }

    button(text, action, parent = this.sidebar) {
        const b = this.text('button', text, parent);
        b.type = 'button';
        b.className = 'ip-action ip-measure';
        b.addEventListener('click', action, { signal: this.abort.signal });
        return b;
    }

    buildPanel() {
        this.text('small', 'SELECTED TIMBER');
        this.text('h3', this.data.name);
        this.text('p', 'STL placement · isolated mode');
        this.text('p', 'Only this STL can be edited. Right-drag to orbit; scroll to zoom. Escape cancels.');
        this.text('h3', 'Transform');
        const modes = this.text('div', 'Gizmo: ');
        this.modeButtons = [];
        for (const [name, label] of [['translation', 'Move'], ['rotation', 'Rotate'], ['scale', 'Scale']]) {
            const button = this.button(label, () => { this.mode = name; this.rebuildGizmo(); this.update(); }, modes);
            this.modeButtons.push({ name, button });
        }
        this.text('p', 'Scale: drag an axis box for one axis, or the center box for all three.');
        for (const [key, label, step] of [['translation', 'Translation (m)', .001], ['rotation', 'Rotation (degrees)', 1], ['scale', 'Scale', .01]]) {
            this.text('h4', label);
            const row = this.text('div', ''); row.className = 'stl-placement-fields';
            for (let axis = 0; axis < 3; axis++) {
                const labelNode = this.text('label', 'XYZ'[axis], row);
                const input = document.createElement('input'); input.type = 'number'; input.step = String(step);
                input.setAttribute('aria-label', `${label} ${'XYZ'[axis]}`);
                input.className = 'stl-placement-input';
                input.onchange = () => {
                    const next = placement(this.value); next[key][axis] = Number(input.value);
                    try { this.value = placement(next); this.update(); this.status.textContent = ''; }
                    catch (error) { this.status.textContent = error.message; this.update(); }
                };
                labelNode.append(input); this.inputs.push({ key, axis, input });
            }
        }
        this.text('h4', 'Quarter turns');
        for (let axis = 0; axis < 3; axis++) for (const sign of [-1, 1]) {
            this.button(`${'XYZ'[axis]} ${sign > 0 ? '+' : '−'}90°`, () => { this.rotate(this.value.rotation, new THREE.Vector3().setComponent(axis, 1), sign * Math.PI / 2); this.update(); });
        }
        this.button('Fit to reference', () => {
            const box = new THREE.Box3().setFromBufferAttribute(this.geometry.attributes.position);
            const size = box.getSize(new THREE.Vector3());
            const factor = Math.min(...this.data.size.map((v, i) => v / size.getComponent(i)));
            this.value = placement({ scale: [factor, factor, factor], translation: [
                -(box.min.x + box.max.x) * factor / 2,
                -(box.min.y + box.max.y) * factor / 2, -box.min.z * factor] }); this.update();
        });
        this.button('Reset', () => { this.value = placement(this.data.placement); this.update(); });
        this.text('hr', '');
        this.saveButton = this.button('Update configuration', () => {
            this.saveButton.disabled = true; this.status.textContent = 'Updating source…';
            this.send({ type: 'updateSTLPlacement', memberKey: this.data.memberKey, placement: this.value });
        });
        this.button('Cancel', () => this.onClose());
        this.status = this.text('p', ''); this.status.setAttribute('role', 'alert');
        this.button('Copy configuration', () => this.send({ type: 'copySTLPlacement', text: configuration(this.value) }));
        this.button('Copy prompt for agent', () => this.send({ type: 'copySTLPlacement', text: agentPrompt(this.data.name, this.value) }));
        this.text('hr', ''); this.text('small', 'TREE · unavailable during placement');
        this.text('p', this.data.name);
    }

    buildScene() {
        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.setClearColor(0, 0);
        this.renderer.domElement.style.cssText = 'display:block;width:100%;height:100%;touch-action:none';
        this.stage.append(this.renderer.domElement);
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(45, 1, .001, 1000);
        this.radius = Math.max(...this.data.size) * 2.5;
        this.yaw = .8; this.pitch = .35;
        this.target = new THREE.Vector3(0, 0, this.data.size[2] / 2);
        this.scene.add(new THREE.HemisphereLight(0xffffff, 0x555555, 1.5));
        this.geometry = new THREE.BufferGeometry();
        this.geometry.setAttribute('position', new THREE.Float32BufferAttribute(this.data.vertices.flat(), 3));
        this.geometry.setIndex(this.data.faces.flat()); this.geometry.computeVertexNormals();
        this.mesh = new THREE.Mesh(this.geometry, new THREE.MeshStandardMaterial(this.material));
        this.scene.add(this.mesh);
        const reference = new THREE.BoxGeometry(...this.data.size);
        this.reference = new THREE.LineSegments(new THREE.EdgesGeometry(reference), new THREE.LineBasicMaterial({ color: this.style.reference }));
        reference.dispose(); this.reference.position.z = this.data.size[2] / 2; this.scene.add(this.reference);
        this.gizmo = new THREE.Group(); this.scene.add(this.gizmo);
        this.gizmoSize = Math.max(...this.data.size) * .25;
        this.rebuildGizmo();
        const canvas = this.renderer.domElement;
        canvas.addEventListener('contextmenu', e => e.preventDefault(), { signal: this.abort.signal });
        canvas.addEventListener('pointerdown', e => this.pointerDown(e), { signal: this.abort.signal });
        canvas.addEventListener('pointermove', e => this.pointerMove(e), { signal: this.abort.signal });
        canvas.addEventListener('pointerup', () => { this.drag = null; }, { signal: this.abort.signal });
        canvas.addEventListener('pointercancel', () => { this.drag = null; }, { signal: this.abort.signal });
        canvas.addEventListener('wheel', e => { e.preventDefault(); this.radius *= Math.exp(e.deltaY * .001); this.radius = Math.max(.01, Math.min(1000, this.radius)); this.render(); }, { passive: false, signal: this.abort.signal });
    }

    disposeObjects(root) {
        root.traverse(object => { object.geometry?.dispose(); if (Array.isArray(object.material)) object.material.forEach(m => m.dispose()); else object.material?.dispose(); });
    }

    rebuildGizmo() {
        this.disposeObjects(this.gizmo); this.gizmo.clear();
        const length = this.gizmoSize;
        if (this.mode === 'scale') {
            const center = new THREE.Mesh(new THREE.BoxGeometry(length * .16, length * .16, length * .16),
                new THREE.MeshBasicMaterial({ color: this.style.uniformScale, depthTest: false }));
            center.userData.uniformScale = true; center.renderOrder = 102;
            this.gizmo.add(center);
        }
        for (let axis = 0; axis < 3; axis++) {
            const direction = new THREE.Vector3().setComponent(axis, 1);
            const material = new THREE.MeshBasicMaterial({ color: this.style.axes[axis], depthTest: false, transparent: true, opacity: .9 });
            let handle;
            if (this.mode === 'rotation') {
                handle = new THREE.Mesh(new THREE.TorusGeometry(length, length * .025, 6, 64), material);
                handle.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), direction);
            } else {
                const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), direction.clone().multiplyScalar(length)]), new THREE.LineBasicMaterial({ color: this.style.axes[axis], depthTest: false }));
                line.renderOrder = 100; this.gizmo.add(line);
                handle = new THREE.Mesh(this.mode === 'scale' ? new THREE.BoxGeometry(length * .12, length * .12, length * .12) : new THREE.ConeGeometry(length * .07, length * .2, 12), material);
                handle.position.copy(direction.multiplyScalar(length));
                handle.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), new THREE.Vector3().setComponent(axis, 1));
            }
            handle.userData.axis = axis; handle.renderOrder = 101; this.gizmo.add(handle);
        }
    }

    ray(event) {
        const rect = this.renderer.domElement.getBoundingClientRect();
        const ray = new THREE.Raycaster();
        ray.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1), this.camera);
        return ray;
    }

    pointerDown(event) {
        if (event.button === 2) this.drag = { orbit: true, x: event.clientX, y: event.clientY, yaw: this.yaw, pitch: this.pitch };
        else if (event.button === 0) {
            const hit = this.ray(event).intersectObjects(this.gizmo.children).find(h => Number.isInteger(h.object.userData.axis) || h.object.userData.uniformScale);
            if (!hit) return;
            if (hit.object.userData.uniformScale) {
                this.drag = { uniformScale: true, x: event.clientX, y: event.clientY, value: placement(this.value) };
                this.renderer.domElement.setPointerCapture(event.pointerId);
                return;
            }
            const axis = hit.object.userData.axis;
            const origin = this.gizmo.position.clone();
            const direction = new THREE.Vector3().setComponent(axis, 1).applyQuaternion(this.gizmo.quaternion);
            const a = origin.clone().project(this.camera), b = origin.clone().add(direction).project(this.camera);
            const rect = this.renderer.domElement.getBoundingClientRect();
            this.drag = { axis, x: event.clientX, y: event.clientY, value: placement(this.value),
                screen: new THREE.Vector2((b.x - a.x) * rect.width / 2, -(b.y - a.y) * rect.height / 2),
                plane: new THREE.Plane().setFromNormalAndCoplanarPoint(direction, origin), origin, direction };
            this.drag.start = this.ray(event).ray.intersectPlane(this.drag.plane, new THREE.Vector3());
        }
        if (this.drag) this.renderer.domElement.setPointerCapture(event.pointerId);
    }

    pointerMove(event) {
        const drag = this.drag; if (!drag) return;
        const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
        if (drag.orbit) { this.yaw = drag.yaw - dx * .01; this.pitch = Math.max(-1.5, Math.min(1.5, drag.pitch + dy * .01)); this.render(); return; }
        this.value = placement(drag.value);
        if (drag.uniformScale) {
            const factor = Math.exp((dx - dy) * .01);
            this.value.scale = drag.value.scale.map(v => v * factor);
            this.update(); return;
        }
        const amount = (dx * drag.screen.x + dy * drag.screen.y) / Math.max(1, drag.screen.lengthSq());
        if (this.mode === 'translation') this.value.translation[drag.axis] += amount;
        if (this.mode === 'scale') {
            const factor = Math.max(.001, 1 + amount / this.gizmoSize);
            this.value.scale[drag.axis] *= factor;
        }
        if (this.mode === 'rotation' && drag.start) {
            const point = this.ray(event).ray.intersectPlane(drag.plane, new THREE.Vector3());
            if (point) {
                const a = drag.start.clone().sub(drag.origin).normalize(), b = point.sub(drag.origin).normalize();
                this.rotate(drag.value.rotation, drag.direction, Math.atan2(drag.direction.dot(a.clone().cross(b)), a.dot(b)));
            }
        }
        this.update();
    }

    rotate(angles, axis, radians) {
        const original = new THREE.Quaternion().setFromEuler(new THREE.Euler(...angles.map(v => v * Math.PI / 180), 'XYZ'));
        const rotated = new THREE.Quaternion().setFromAxisAngle(axis, radians).multiply(original);
        const euler = new THREE.Euler().setFromQuaternion(rotated, 'XYZ');
        this.value.rotation = [euler.x, euler.y, euler.z].map(v => v * 180 / Math.PI);
    }

    update() {
        for (const { name, button } of this.modeButtons) button.setAttribute('aria-pressed', String(this.mode === name));
        for (const { key, axis, input } of this.inputs) input.value = String(Number(this.value[key][axis].toFixed(6)));
        this.mesh.position.fromArray(this.value.translation);
        this.mesh.rotation.set(...this.value.rotation.map(v => v * Math.PI / 180), 'XYZ');
        this.mesh.scale.fromArray(this.value.scale);
        this.gizmo.position.copy(this.mesh.position);
        this.gizmo.quaternion.copy(this.mode === 'scale' ? this.mesh.quaternion : new THREE.Quaternion());
        this.render();
    }

    render() {
        const width = this.stage.clientWidth, height = this.stage.clientHeight;
        if (!width || !height) return;
        this.renderer.setSize(width, height, false);
        this.camera.aspect = width / height; this.camera.updateProjectionMatrix();
        this.camera.up.set(0, 0, 1);
        this.camera.position.copy(this.target).add(new THREE.Vector3(Math.cos(this.yaw) * Math.cos(this.pitch), Math.sin(this.yaw) * Math.cos(this.pitch), Math.sin(this.pitch)).multiplyScalar(this.radius));
        this.camera.lookAt(this.target); this.renderer.render(this.scene, this.camera);
    }

    failed(error) {
        this.saveButton.disabled = false;
        this.status.textContent = `Could not update the source: ${error} You can edit it manually or ask the agent. Copy the configuration or prompt below.`;
    }

    dispose() {
        this.abort.abort(); this.resize.disconnect(); this.disposeObjects(this.scene); this.renderer.dispose(); this.root.remove();
        for (const [element, inert] of this.suspended) element.inert = inert;
    }
}
