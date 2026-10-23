/**
 * The camera: the gizmo and light dial dragged, animation, focus, pan and zoom, camera mode and projection.
 *
 * A mixin of the viewer (viewer-app.js): its methods run as the viewer's.
 */

import { DRAWING_BETA_ENABLED, accumulateBounds, boundsFromAccumulator, createBoundsAccumulator } from './viewer-shared.js';

export const CameraMixin = (Base) => class extends Base {
    onGizmoPointerMove(event) {
        if (!this.gizmoDragging) {
            return;
        }
        const dx = event.clientX - this.gizmoLastX;
        const dy = event.clientY - this.gizmoLastY;
        if (Math.abs(dx) + Math.abs(dy) > 1) {
            this.gizmoMoved = true;
        }
        this.orbitActiveViewport(dx, dy);
        this.gizmoLastX = event.clientX;
        this.gizmoLastY = event.clientY;
        this.cameraController.cancelAnimation();
        this.updateCamera();
    }

    onGizmoPointerUp(event) {
        if (!this.gizmoDragging) {
            return;
        }
        this.gizmoDragging = false;
        if (this.gizmoMoved) {
            return;
        }
        const canvas = this.renderRoot.querySelector('#gizmo-cube-c');
        const rect = canvas.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        this.snapCameraFromGizmoFace(x, y);
    }

    onLightDialPointerMove(event) {
        if (!this.lightDialDragging) {
            return;
        }
        this.applyLightDialFromPointer(event);
    }

    onLightDialPointerUp() {
        this.lightDialDragging = false;
    }

    clampPhi(value) {
        return this.cameraController.clampPhi(value);
    }

    animateCameraTo(targetOffsetDir, targetOrbitDist, durationMs = 260, targetUpVector = null, targetCenter = null) {
        this.cameraController.animateTo({
            offsetDir: targetOffsetDir,
            distance: targetOrbitDist,
            durationMs,
            upVector: targetUpVector,
            center: targetCenter,
        });
    }

    stepCameraAnimation() {
        if (!this.cameraController.hasAnimation()) {
            return;
        }
        this.cameraController.stepAnimation();
        this.updateCamera();
    }

    getSelectionBounds() {
        const selected = this.selectionManager.getSelectedTimbers();
        if (!selected.length) {
            return this.getSceneBounds();
        }

        const acc = createBoundsAccumulator();
        for (const key of selected) {
            const bundle = this.sceneManager.get(key);
            if (!bundle || !bundle.mesh || !bundle.mesh.geometry) {
                continue;
            }
            accumulateBounds(acc, bundle.mesh.geometry.getAttribute('position').array);
        }

        if (!acc.hasAny) {
            return this.getSceneBounds();
        }

        return boundsFromAccumulator(acc);
    }

    setCameraMode(mode) {
        // A locked viewport is free-mode by construction (see applySpecCamera):
        // standard mode would snap its up back to world Z and flip the view.
        const active = this.activeViewport;
        if (active && active.spec.locked) {
            return;
        }
        const currentMode = this.cameraController.getCameraMode();
        const nextMode = mode === 'free' ? 'free' : 'standard';
        const shouldAnimateToStandard = currentMode === 'free' && nextMode === 'standard';

        this.cameraController.cancelAnimation();
        this.cameraController.setCameraMode(nextMode, { snapUp: !shouldAnimateToStandard });

        if (shouldAnimateToStandard) {
            const center = this.cameraController.getCenter();
            const offset = this.cameraController.cameraOffsetDir;
            this.cameraController.animateTo({
                offsetDir: { x: offset.x, y: offset.y, z: offset.z },
                upVector: { x: 0, y: 0, z: 1 },
                distance: this.cameraController.orbitDist,
                center: { x: center.x, y: center.y, z: center.z },
                durationMs: 220,
            });
        }

        this.cameraController.clearOrbitDragFrame();
        this.requestUpdate();
        this.updateCamera();
    }

    focusSelection() {
        // Not on a sheet. Focusing is a zoom and a pan of one viewport's
        // camera, and a drawing's cameras are what python declared -- an
        // elevation that has been refocused is no longer at the scale the
        // drawing says it is. The gizmo's focus button is hidden in a drawing
        // but the f key is not, so the guard belongs here rather than there.
        if (this.activePage) {
            return;
        }
        const bounds = this.getSelectionBounds();
        this.lastBounds = bounds;
        this.focusedCx = (bounds.minX + bounds.maxX) / 2;
        this.focusedCy = (bounds.minY + bounds.maxY) / 2;
        this.focusedCz = (bounds.minZ + bounds.maxZ) / 2;
        const dx = bounds.maxX - bounds.minX;
        const dy = bounds.maxY - bounds.minY;
        const dz = bounds.maxZ - bounds.minZ;
        const radius = Math.sqrt(dx * dx + dy * dy + dz * dz) / 2 || 5;
        // Always use the perspective camera's FOV, even in orthographic mode: orbitDist
        // drives the orthographic frustum size too (see updateOrthographicFrustum), so this
        // keeps "fit to bounds" framing consistent across both projections.
        const fovRad = this.perspectiveCamera.fov * Math.PI / 180;
        const targetDist = radius / Math.sin(fovRad / 2) * 1.3;
        this.animateCameraTo(
            { x: 0, y: -1, z: 0 },
            targetDist,
            280,
            { x: 0, y: 0, z: 1 },
            { x: this.focusedCx, y: this.focusedCy, z: this.focusedCz },
        );
        this.updateLightFromAngles();
    }

    getCameraCenterVector(target = null) {
        const out = target || new THREE.Vector3();
        return out.set(this.cameraController.cx, this.cameraController.cy, this.cameraController.cz);
    }

    projectPointerToFocalPlane(clientX, clientY, planeCenter = null) {
        if (!this.camera) {
            return null;
        }
        const canvas = this.renderRoot.querySelector('#c');
        if (!canvas) {
            return null;
        }
        const rect = canvas.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) {
            return null;
        }

        this.navigationPointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
        this.navigationPointer.y = -(((clientY - rect.top) / rect.height) * 2 - 1);
        this.navigationRaycaster.setFromCamera(this.navigationPointer, this.camera);

        const focalCenter = planeCenter || this.getCameraCenterVector(this.tempOrbitCenter);
        const viewDirection = this.camera.getWorldDirection(this.tempViewDirection).normalize();
        this.focalPlane.setFromNormalAndCoplanarPoint(viewDirection, focalCenter);
        const hit = this.navigationRaycaster.ray.intersectPlane(this.focalPlane, this.tempPlaneHit);
        return hit ? hit.clone() : null;
    }

    panCameraInViewPlane(fromClientX, fromClientY, toClientX, toClientY) {
        const planeCenter = this.getCameraCenterVector(this.tempOrbitCenter);
        const fromPoint = this.projectPointerToFocalPlane(fromClientX, fromClientY, planeCenter);
        const toPoint = this.projectPointerToFocalPlane(toClientX, toClientY, planeCenter);
        if (!fromPoint || !toPoint) {
            return;
        }
        const delta = fromPoint.sub(toPoint);
        this.cameraController.cx += delta.x;
        this.cameraController.cy += delta.y;
        this.cameraController.cz += delta.z;
    }

    getAdaptiveZoomFactor(isZoomingOut) {
        return this.cameraController.getAdaptiveZoomFactor(isZoomingOut);
    }

    zoomTowardPointer(clientX, clientY, zoomFactor) {
        const oldDist = Math.max(0.01, this.cameraController.orbitDist);
        const nextDist = Math.max(0.01, oldDist * zoomFactor);
        const planeCenter = this.getCameraCenterVector(this.tempOrbitCenter);
        const focalPoint = this.projectPointerToFocalPlane(clientX, clientY, planeCenter);
        let targetCenter = { x: this.cameraController.cx, y: this.cameraController.cy, z: this.cameraController.cz };

        if (focalPoint) {
            const ratio = nextDist / oldDist;
            targetCenter = {
                x: this.cameraController.cx + (focalPoint.x - planeCenter.x) * (1 - ratio),
                y: this.cameraController.cy + (focalPoint.y - planeCenter.y) * (1 - ratio),
                z: this.cameraController.cz + (focalPoint.z - planeCenter.z) * (1 - ratio),
            };
        }

        this.animateCameraTo(
            { x: this.cameraController.cameraOffsetDir.x, y: this.cameraController.cameraOffsetDir.y, z: this.cameraController.cameraOffsetDir.z },
            nextDist,
            140,
            { x: this.cameraController.cameraUpVector.x, y: this.cameraController.cameraUpVector.y, z: this.cameraController.cameraUpVector.z },
            targetCenter,
        );
    }

    updateReflectionTransforms() {
        const reflectionOffsetZ = this.groundZ * 2 - 0.001;
        for (const [memberKey, bundle] of this.sceneManager.entries()) {
            if (!bundle.reflection) {
                continue;
            }
            // The reflection is mirrored (scale.z = -1), so an assembly offset
            // of +dz on the solid mesh moves the reflection by -dz.
            const offset = this._assemblyOffsetsByKey.get(memberKey) || [0, 0, 0];
            const rotation = this._assemblyRotationsByKey.get(memberKey);
            const shift = rotation ? rotation.shift : [0, 0, 0];
            const q = rotation ? rotation.quaternion : [0, 0, 0, 1];
            bundle.reflection.position.set(
                offset[0] + shift[0], offset[1] + shift[1], reflectionOffsetZ - offset[2] - shift[2]);
            // The member's rotation, mirrored in z.
            bundle.reflection.quaternion.set(-q[0], -q[1], q[2], q[3]);
            bundle.reflection.scale.set(1, 1, -1);
            // Where it goes, not whether it shows. applyRenderMode owns that.
        }
    }

    updateCamera() {
        // Every viewport, not just the active one: the others are on screen at
        // the same time and would otherwise never be positioned.
        for (const viewport of this.viewports) {
            if (viewport.isOrthographic) {
                this.updateViewportOrthographicFrustum(viewport);
            }
            viewport.cameraController.applyToCamera(viewport.camera);
        }
        this.updateOrbitCenterGizmo();
    }

    // Sizes the orthographic frustum from the current orbitDist and the perspective
    // camera's FOV, so switching projections (or zooming while orthographic) keeps the
    // same apparent framing a perspective camera would show at that distance -- called
    // from updateCamera() before every use rather than only on resize/toggle, since
    // orbitDist changes continuously during zoom/animation.
    updateOrthographicFrustum() {
        for (const viewport of this.viewports) {
            this.updateViewportOrthographicFrustum(viewport);
        }
    }

    /**
     * Size one viewport's orthographic frustum from its own orbit distance and
     * the perspective FOV, so switching projections -- or zooming while
     * orthographic -- keeps the framing a perspective camera would show.
     *
     * The aspect is the viewport's, not the canvas's: an elevation occupying a
     * quarter of the width is a different shape from the window around it.
     */
    updateViewportOrthographicFrustum(viewport) {
        const fovRad = viewport.perspectiveCamera.fov * Math.PI / 180;
        const halfHeight = Math.max(0.001, viewport.cameraController.orbitDist) * Math.tan(fovRad / 2);
        const halfWidth = halfHeight * this.viewportAspect(viewport);
        const camera = viewport.orthographicCamera;
        camera.left = -halfWidth;
        camera.right = halfWidth;
        camera.top = halfHeight;
        camera.bottom = -halfHeight;
        camera.updateProjectionMatrix();
    }

    /**
     * Whether drawing mode is offered at all (kigumi.viewer.drawingBeta).
     *
     * Read by everything that is a way in: the draw button, the drawings
     * section of the layers panel, and the drawing options. Off, the viewer
     * never leaves the 3D scene.
     */
    get drawingBetaEnabled() {
        return DRAWING_BETA_ENABLED;
    }
};
