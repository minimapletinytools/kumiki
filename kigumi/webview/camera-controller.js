(function (globalScope) {
    // CameraController owns all orbit-camera state and pure math: position/up
    // computation, drag rotation, animation, zoom scaling, and (de)serialization.
    // It deliberately knows nothing about the DOM, the THREE scene graph, or the
    // viewer-app — the host is responsible for passing pointer deltas in and for
    // calling applyToCamera() to write the result onto a THREE.PerspectiveCamera.

    const DEFAULT_INITIAL_THETA = -Math.PI / 5;
    const DEFAULT_INITIAL_PHI = Math.PI / 3;
    const DEFAULT_INITIAL_DISTANCE = 10;
    const DEFAULT_ORBIT_SPEED = 0.008;
    const PHI_EPSILON = 0.05;
    const CAMERA_MODE_STANDARD = 'standard';
    const CAMERA_MODE_FREE = 'free';

    function defaultNow() {
        if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
            return performance.now();
        }
        return Date.now();
    }

    class CameraController {
        constructor(options = {}) {
            const THREE = options.THREE;
            if (!THREE) {
                throw new Error('CameraController requires a THREE module via options.THREE');
            }
            this.THREE = THREE;

            const angles = options.initialAngles || { theta: DEFAULT_INITIAL_THETA, phi: DEFAULT_INITIAL_PHI };
            const center = options.center || { x: 0, y: 0, z: 0 };
            const upInit = options.defaultUp || { x: 0, y: 0, z: 1 };

            this.cx = Number(center.x) || 0;
            this.cy = Number(center.y) || 0;
            this.cz = Number(center.z) || 0;
            this.orbitDist = options.initialDistance != null
                ? Number(options.initialDistance)
                : DEFAULT_INITIAL_DISTANCE;

            this.cameraOffsetDir = new THREE.Vector3();
            this.setOffsetDirFromAngles(angles.theta, angles.phi);

            this.cameraUpVector = new THREE.Vector3(upInit.x, upInit.y, upInit.z);
            if (this.cameraUpVector.lengthSq() === 0) {
                this.cameraUpVector.set(0, 0, 1);
            } else {
                this.cameraUpVector.normalize();
            }

            this.dragOrbitUpAxis = null;
            this.dragOrbitRightAxis = null;
            this.cameraAnimation = null;
            this._nowFn = typeof options.now === 'function' ? options.now : defaultNow;
            this.cameraMode = options.cameraMode === CAMERA_MODE_FREE
                ? CAMERA_MODE_FREE
                : CAMERA_MODE_STANDARD;
        }

        setCameraMode(mode, options = {}) {
            const shouldSnapUp = options.snapUp !== false;
            this.cameraMode = mode === CAMERA_MODE_FREE
                ? CAMERA_MODE_FREE
                : CAMERA_MODE_STANDARD;
            if (this.cameraMode === CAMERA_MODE_STANDARD && shouldSnapUp) {
                this.cameraUpVector.set(0, 0, 1);
            }
        }

        getCameraMode() {
            return this.cameraMode;
        }

        clampPhi(value) {
            return Math.max(PHI_EPSILON, Math.min(Math.PI - PHI_EPSILON, value));
        }

        setOffsetDirFromAngles(theta, phi) {
            this.cameraOffsetDir.set(
                Math.sin(phi) * Math.cos(theta),
                Math.sin(phi) * Math.sin(theta),
                Math.cos(phi),
            );
        }

        getOffsetAngles() {
            const d = this.cameraOffsetDir;
            const theta = Math.atan2(d.y, d.x);
            const phi = Math.acos(Math.max(-1, Math.min(1, d.z)));
            return { theta, phi };
        }

        getCenter() {
            return new this.THREE.Vector3(this.cx, this.cy, this.cz);
        }

        setCenter(x, y, z) {
            this.cx = x;
            this.cy = y;
            this.cz = z;
        }

        translateCenter(dx, dy, dz) {
            this.cx += dx;
            this.cy += dy;
            this.cz += dz;
        }

        captureOrbitDragFrame() {
            const THREE = this.THREE;
            // Capture the screen-up axis (camera's up projected into world space) and
            // the screen-right axis at the start of a drag. These remain fixed for the
            // entire drag so the orbit pivots around the screen-Y axis as it was at
            // drag start.
            const up = this.cameraUpVector.clone();
            if (up.lengthSq() === 0) {
                up.set(0, 0, 1);
            }
            up.normalize();
            // Forward = from camera to center = -offsetDir
            const fwd = this.cameraOffsetDir.clone().multiplyScalar(-1);
            let right = new THREE.Vector3().crossVectors(fwd, up);
            if (right.lengthSq() < 1e-12) {
                // Up is parallel to view direction; pick an arbitrary perpendicular.
                const fallback = Math.abs(up.x) < 0.9
                    ? new THREE.Vector3(1, 0, 0)
                    : new THREE.Vector3(0, 1, 0);
                right = new THREE.Vector3().crossVectors(fwd, fallback);
            }
            right.normalize();
            this.dragOrbitUpAxis = up;
            this.dragOrbitRightAxis = right;
        }

        clearOrbitDragFrame() {
            this.dragOrbitUpAxis = null;
            this.dragOrbitRightAxis = null;
        }

        applyOrbitDelta(dx, dy, speed = DEFAULT_ORBIT_SPEED) {
            if (this.cameraMode === CAMERA_MODE_STANDARD) {
                const { theta, phi } = this.getOffsetAngles();
                const nextTheta = theta - dx * speed;
                const nextPhi = this.clampPhi(phi + dy * speed);
                this.setOffsetDirFromAngles(nextTheta, nextPhi);
                this.cameraUpVector.set(0, 0, 1);
                return;
            }

            if (!this.dragOrbitUpAxis || !this.dragOrbitRightAxis) {
                this.captureOrbitDragFrame();
            }
            const THREE = this.THREE;
            const yawQ = new THREE.Quaternion().setFromAxisAngle(this.dragOrbitUpAxis, -dx * speed);
            const pitchQ = new THREE.Quaternion().setFromAxisAngle(this.dragOrbitRightAxis, -dy * speed);
            const rot = yawQ.multiply(pitchQ);
            this.cameraOffsetDir.applyQuaternion(rot).normalize();
            this.cameraUpVector.applyQuaternion(rot).normalize();
        }

        getAdaptiveZoomFactor(isZoomingOut) {
            const baseZoomFactor = isZoomingOut ? 0.8 : 1.2;
            if (this.orbitDist <= 0) {
                return baseZoomFactor;
            }
            const distanceScale = Math.max(0.8, Math.log(this.orbitDist + 1) / 3);
            return Math.pow(baseZoomFactor, distanceScale * 2);
        }

        getCameraSnapForDirection(direction) {
            const offsetDir = { x: direction.x, y: direction.y, z: direction.z };
            if (direction.z > 0) {
                return { offsetDir, upVector: { x: 0, y: 1, z: 0 } };
            }
            if (direction.z < 0) {
                return { offsetDir, upVector: { x: 0, y: -1, z: 0 } };
            }
            return { offsetDir, upVector: { x: 0, y: 0, z: 1 } };
        }

        applyToCamera(threeCamera) {
            if (!threeCamera) {
                return;
            }
            threeCamera.position.set(
                this.cx + this.cameraOffsetDir.x * this.orbitDist,
                this.cy + this.cameraOffsetDir.y * this.orbitDist,
                this.cz + this.cameraOffsetDir.z * this.orbitDist,
            );
            threeCamera.up.copy(this.cameraUpVector);
            threeCamera.lookAt(this.cx, this.cy, this.cz);
        }

        animateTo(options = {}) {
            const THREE = this.THREE;
            const offsetDir = options.offsetDir;
            if (!offsetDir) {
                return;
            }
            const targetDir = new THREE.Vector3(offsetDir.x, offsetDir.y, offsetDir.z);
            if (targetDir.lengthSq() === 0) {
                return;
            }
            targetDir.normalize();

            const upVector = options.upVector;
            const targetUp = upVector
                ? new THREE.Vector3(upVector.x, upVector.y, upVector.z)
                : this.cameraUpVector.clone();
            if (targetUp.lengthSq() === 0) {
                targetUp.copy(this.cameraUpVector);
            } else {
                targetUp.normalize();
            }

            const targetDist = options.distance != null ? Number(options.distance) : this.orbitDist;
            const center = options.center || { x: this.cx, y: this.cy, z: this.cz };
            const durationMs = options.durationMs != null ? Number(options.durationMs) : 260;
            const startedAt = options.now != null ? Number(options.now) : this._nowFn();

            this.cameraAnimation = {
                startedAt,
                durationMs,
                startDir: this.cameraOffsetDir.clone(),
                targetDir,
                startUp: this.cameraUpVector.clone(),
                targetUp,
                startDist: this.orbitDist,
                deltaDist: targetDist - this.orbitDist,
                startCx: this.cx,
                startCy: this.cy,
                startCz: this.cz,
                deltaCx: center.x - this.cx,
                deltaCy: center.y - this.cy,
                deltaCz: center.z - this.cz,
            };
        }

        hasAnimation() {
            return Boolean(this.cameraAnimation);
        }

        cancelAnimation() {
            this.cameraAnimation = null;
        }

        stepAnimation(now) {
            if (!this.cameraAnimation) {
                return false;
            }
            const currentNow = now != null ? Number(now) : this._nowFn();
            const a = this.cameraAnimation;
            const elapsed = currentNow - a.startedAt;
            const t = Math.max(0, Math.min(1, a.durationMs > 0 ? elapsed / a.durationMs : 1));
            const eased = 1 - Math.pow(1 - t, 3);

            this._slerpVec(this.cameraOffsetDir, a.startDir, a.targetDir, eased);
            this._slerpVec(this.cameraUpVector, a.startUp, a.targetUp, eased);
            this.orbitDist = Math.max(0.01, a.startDist + a.deltaDist * eased);
            this.cx = a.startCx + a.deltaCx * eased;
            this.cy = a.startCy + a.deltaCy * eased;
            this.cz = a.startCz + a.deltaCz * eased;

            if (t >= 1) {
                this.cameraAnimation = null;
                return false;
            }
            return true;
        }

        _slerpVec(out, a, b, t) {
            const dot = Math.max(-1, Math.min(1, a.dot(b)));
            if (dot > 0.9995 || dot < -0.9995) {
                out.set(
                    a.x + (b.x - a.x) * t,
                    a.y + (b.y - a.y) * t,
                    a.z + (b.z - a.z) * t,
                );
                if (out.lengthSq() === 0) {
                    out.copy(b);
                } else {
                    out.normalize();
                }
                return out;
            }
            const omega = Math.acos(dot);
            const sinO = Math.sin(omega);
            const wA = Math.sin((1 - t) * omega) / sinO;
            const wB = Math.sin(t * omega) / sinO;
            out.set(
                a.x * wA + b.x * wB,
                a.y * wA + b.y * wB,
                a.z * wA + b.z * wB,
            );
            return out;
        }

        buildStatePayload() {
            const { theta, phi } = this.getOffsetAngles();
            return {
                mode: this.cameraMode,
                orbitCenter: { x: this.cx, y: this.cy, z: this.cz },
                orbit: { theta, phi, distance: this.orbitDist },
                up: {
                    x: this.cameraUpVector.x,
                    y: this.cameraUpVector.y,
                    z: this.cameraUpVector.z,
                },
            };
        }

        applyStatePayload(state) {
            if (!state || typeof state !== 'object') {
                return;
            }
            this.setCameraMode(state.mode);
            const orbitCenter = (state.orbitCenter && typeof state.orbitCenter === 'object') ? state.orbitCenter : {};
            const orbit = (state.orbit && typeof state.orbit === 'object') ? state.orbit : {};
            const up = (state.up && typeof state.up === 'object') ? state.up : {};

            const nextCx = Number(orbitCenter.x);
            const nextCy = Number(orbitCenter.y);
            const nextCz = Number(orbitCenter.z);
            if (Number.isFinite(nextCx) && Number.isFinite(nextCy) && Number.isFinite(nextCz)) {
                this.cx = nextCx;
                this.cy = nextCy;
                this.cz = nextCz;
            }

            const nextTheta = Number(orbit.theta);
            const nextPhi = Number(orbit.phi);
            const nextDist = Number(orbit.distance);
            if (Number.isFinite(nextTheta) || Number.isFinite(nextPhi)) {
                const current = this.getOffsetAngles();
                const useTheta = Number.isFinite(nextTheta) ? nextTheta : current.theta;
                const usePhi = Number.isFinite(nextPhi) ? this.clampPhi(nextPhi) : current.phi;
                this.setOffsetDirFromAngles(useTheta, usePhi);
            }
            if (Number.isFinite(nextDist) && nextDist > 0.01) {
                this.orbitDist = nextDist;
            }

            const upX = Number(up.x);
            const upY = Number(up.y);
            const upZ = Number(up.z);
            if (Number.isFinite(upX) && Number.isFinite(upY) && Number.isFinite(upZ)) {
                const vector = new this.THREE.Vector3(upX, upY, upZ);
                if (vector.lengthSq() > 0) {
                    vector.normalize();
                    this.cameraUpVector.copy(vector);
                }
            }

            this.cameraAnimation = null;
        }
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { CameraController };
    }
    globalScope.CameraController = CameraController;
})(typeof window !== 'undefined' ? window : globalThis);
