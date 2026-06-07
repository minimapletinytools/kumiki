const { CameraController } = require('../webview/camera-controller');

// Minimal THREE stub implementing the surface CameraController uses.
class V3 {
    constructor(x = 0, y = 0, z = 0) {
        this.x = x;
        this.y = y;
        this.z = z;
    }
    set(x, y, z) {
        this.x = x;
        this.y = y;
        this.z = z;
        return this;
    }
    copy(v) {
        this.x = v.x;
        this.y = v.y;
        this.z = v.z;
        return this;
    }
    clone() {
        return new V3(this.x, this.y, this.z);
    }
    lengthSq() {
        return this.x * this.x + this.y * this.y + this.z * this.z;
    }
    length() {
        return Math.sqrt(this.lengthSq());
    }
    normalize() {
        const l = this.length();
        if (l > 0) {
            this.x /= l;
            this.y /= l;
            this.z /= l;
        }
        return this;
    }
    multiplyScalar(s) {
        this.x *= s;
        this.y *= s;
        this.z *= s;
        return this;
    }
    dot(v) {
        return this.x * v.x + this.y * v.y + this.z * v.z;
    }
    crossVectors(a, b) {
        const ax = a.x;
        const ay = a.y;
        const az = a.z;
        const bx = b.x;
        const by = b.y;
        const bz = b.z;
        this.x = ay * bz - az * by;
        this.y = az * bx - ax * bz;
        this.z = ax * by - ay * bx;
        return this;
    }
    applyQuaternion(q) {
        const x = this.x;
        const y = this.y;
        const z = this.z;
        const qx = q.x;
        const qy = q.y;
        const qz = q.z;
        const qw = q.w;
        // t = 2 * cross(q.xyz, v)
        const tx = 2 * (qy * z - qz * y);
        const ty = 2 * (qz * x - qx * z);
        const tz = 2 * (qx * y - qy * x);
        // v + qw * t + cross(q.xyz, t)
        this.x = x + qw * tx + (qy * tz - qz * ty);
        this.y = y + qw * ty + (qz * tx - qx * tz);
        this.z = z + qw * tz + (qx * ty - qy * tx);
        return this;
    }
}

class Quat {
    constructor(x = 0, y = 0, z = 0, w = 1) {
        this.x = x;
        this.y = y;
        this.z = z;
        this.w = w;
    }
    setFromAxisAngle(axis, angle) {
        const half = angle / 2;
        const s = Math.sin(half);
        this.x = axis.x * s;
        this.y = axis.y * s;
        this.z = axis.z * s;
        this.w = Math.cos(half);
        return this;
    }
    multiply(q) {
        const ax = this.x;
        const ay = this.y;
        const az = this.z;
        const aw = this.w;
        const bx = q.x;
        const by = q.y;
        const bz = q.z;
        const bw = q.w;
        this.x = ax * bw + aw * bx + ay * bz - az * by;
        this.y = ay * bw + aw * by + az * bx - ax * bz;
        this.z = az * bw + aw * bz + ax * by - ay * bx;
        this.w = aw * bw - ax * bx - ay * by - az * bz;
        return this;
    }
}

const THREE = { Vector3: V3, Quaternion: Quat };

function approxEqual(a, b, tol = 1e-9) {
    return Math.abs(a - b) <= tol;
}

function expectVec(v, x, y, z, tol = 1e-9) {
    expect(approxEqual(v.x, x, tol)).toBe(true);
    expect(approxEqual(v.y, y, tol)).toBe(true);
    expect(approxEqual(v.z, z, tol)).toBe(true);
}

describe('CameraController', () => {
    describe('construction', () => {
        test('throws if THREE is not provided', () => {
            expect(() => new CameraController({})).toThrow(/THREE/);
        });

        test('uses default angles, distance, center, and up when none provided', () => {
            const c = new CameraController({ THREE });
            expect(c.cx).toBe(0);
            expect(c.cy).toBe(0);
            expect(c.cz).toBe(0);
            expect(c.orbitDist).toBe(10);
            expectVec(c.cameraUpVector, 0, 0, 1);
            // Default angles: theta = -pi/5, phi = pi/3 → unit dir = (sin(p)*cos(t), sin(p)*sin(t), cos(p))
            const t = -Math.PI / 5;
            const p = Math.PI / 3;
            expectVec(c.cameraOffsetDir,
                Math.sin(p) * Math.cos(t),
                Math.sin(p) * Math.sin(t),
                Math.cos(p),
                1e-12);
            expect(c.getCameraMode()).toBe('standard');
        });

        test('accepts explicit center and distance', () => {
            const c = new CameraController({
                THREE,
                center: { x: 1, y: 2, z: 3 },
                initialDistance: 7,
                initialAngles: { theta: 0, phi: Math.PI / 2 },
            });
            expect([c.cx, c.cy, c.cz]).toEqual([1, 2, 3]);
            expect(c.orbitDist).toBe(7);
            expectVec(c.cameraOffsetDir, 1, 0, 0, 1e-12);
        });
    });

    describe('angle <-> direction round trip', () => {
        test('setOffsetDirFromAngles then getOffsetAngles returns the inputs', () => {
            const c = new CameraController({ THREE });
            const cases = [
                { theta: 0, phi: Math.PI / 2 },
                { theta: Math.PI / 4, phi: Math.PI / 3 },
                { theta: -Math.PI / 3, phi: Math.PI / 6 },
                { theta: 1.234, phi: 0.7 },
            ];
            for (const { theta, phi } of cases) {
                c.setOffsetDirFromAngles(theta, phi);
                const out = c.getOffsetAngles();
                expect(approxEqual(out.theta, theta, 1e-12)).toBe(true);
                expect(approxEqual(out.phi, phi, 1e-12)).toBe(true);
            }
        });
    });

    describe('clampPhi', () => {
        test('clamps to [0.05, pi - 0.05]', () => {
            const c = new CameraController({ THREE });
            expect(c.clampPhi(-1)).toBe(0.05);
            expect(c.clampPhi(0)).toBe(0.05);
            expect(c.clampPhi(Math.PI / 2)).toBe(Math.PI / 2);
            expect(c.clampPhi(Math.PI)).toBe(Math.PI - 0.05);
            expect(c.clampPhi(10)).toBe(Math.PI - 0.05);
        });
    });

    describe('applyToCamera', () => {
        test('writes position, up, and lookAt onto the THREE camera', () => {
            const c = new CameraController({
                THREE,
                center: { x: 0, y: 0, z: 0 },
                initialDistance: 5,
                initialAngles: { theta: 0, phi: Math.PI / 2 }, // looking from +X
            });
            const lookCalls = [];
            const fakeCam = {
                position: new V3(),
                up: new V3(),
                lookAt: (x, y, z) => { lookCalls.push([x, y, z]); },
            };
            c.applyToCamera(fakeCam);
            expectVec(fakeCam.position, 5, 0, 0, 1e-12);
            expectVec(fakeCam.up, 0, 0, 1);
            expect(lookCalls).toEqual([[0, 0, 0]]);
        });

        test('no-op when camera is null/undefined', () => {
            const c = new CameraController({ THREE });
            expect(() => c.applyToCamera(null)).not.toThrow();
            expect(() => c.applyToCamera(undefined)).not.toThrow();
        });
    });

    describe('orbit drag frame capture', () => {
        test('right axis is perpendicular to forward and to up', () => {
            const c = new CameraController({
                THREE,
                initialAngles: { theta: 0, phi: Math.PI / 2 }, // dir = +X
            });
            c.captureOrbitDragFrame();
            // up = world Z, forward = -X. right = cross(forward, up) = cross(-X, +Z) = +Y
            expectVec(c.dragOrbitUpAxis, 0, 0, 1, 1e-12);
            expectVec(c.dragOrbitRightAxis, 0, 1, 0, 1e-12);
        });

        test('uses fallback right axis when up is parallel to view direction', () => {
            // Place camera directly above center looking down: dir = +Z, up = +Z is degenerate.
            const c = new CameraController({
                THREE,
                initialAngles: { theta: 0, phi: 0 }, // dir = (0, 0, 1)
            });
            // Force up to be parallel with offsetDir (degenerate case).
            c.cameraUpVector.set(0, 0, 1);
            c.captureOrbitDragFrame();
            // Should not blow up; right axis should be a unit vector orthogonal-ish.
            expect(approxEqual(c.dragOrbitRightAxis.length(), 1, 1e-9)).toBe(true);
        });
    });

    describe('setCameraMode', () => {
        test('can switch to standard without snapping up vector immediately', () => {
            const c = new CameraController({
                THREE,
                initialAngles: { theta: 0, phi: Math.PI / 2 },
            });
            c.setCameraMode('free');
            c.captureOrbitDragFrame();
            c.applyOrbitDelta(0, 100);
            expect(Math.abs(c.cameraUpVector.x)).toBeGreaterThan(0.1);

            c.setCameraMode('standard', { snapUp: false });
            expect(c.getCameraMode()).toBe('standard');
            expect(Math.abs(c.cameraUpVector.x)).toBeGreaterThan(0.1);
        });
    });

    describe('applyOrbitDelta', () => {
        test('standard mode keeps camera up aligned to world Z', () => {
            const c = new CameraController({
                THREE,
                initialAngles: { theta: 0, phi: Math.PI / 2 },
            });
            c.setCameraMode('standard');
            c.applyOrbitDelta(0, 100);
            expectVec(c.cameraUpVector, 0, 0, 1, 1e-12);
        });

        test('free mode rotates camera up during orbit drag', () => {
            const c = new CameraController({
                THREE,
                initialAngles: { theta: 0, phi: Math.PI / 2 },
            });
            c.setCameraMode('free');
            c.captureOrbitDragFrame();
            c.applyOrbitDelta(0, 100);
            expect(Math.abs(c.cameraUpVector.x)).toBeGreaterThan(0.1);
            expect(c.cameraUpVector.z).toBeLessThan(1);
        });

        test('horizontal delta rotates camera around captured screen-up axis', () => {
            const c = new CameraController({
                THREE,
                initialAngles: { theta: 0, phi: Math.PI / 2 }, // dir = +X, up = +Z
            });
            c.setCameraMode('free');
            c.captureOrbitDragFrame();
            // dx > 0, dy = 0 → rotate offsetDir around +Z by -dx*speed (clockwise from above).
            const dx = 100;
            const speed = 0.008;
            const expectedAngle = -dx * speed; // -0.8 rad
            c.applyOrbitDelta(dx, 0);
            // After rotating +X by -0.8 around +Z: (cos(-0.8), sin(-0.8), 0)
            expectVec(c.cameraOffsetDir,
                Math.cos(expectedAngle),
                Math.sin(expectedAngle),
                0,
                1e-9);
            // Up rotates around its own axis → unchanged.
            expectVec(c.cameraUpVector, 0, 0, 1, 1e-9);
        });

        test('vertical delta rotates camera around captured screen-right axis', () => {
            const c = new CameraController({
                THREE,
                initialAngles: { theta: 0, phi: Math.PI / 2 }, // dir = +X, right = +Y, up = +Z
            });
            c.setCameraMode('free');
            c.captureOrbitDragFrame();
            const dy = 100;
            const speed = 0.008;
            const angle = -dy * speed; // -0.8
            c.applyOrbitDelta(0, dy);
            // Rotating +X by -0.8 around +Y: matrix gives (cos(-0.8), 0, +sin(0.8))
            // So +X tilts up toward +Z. (Mouse drag down → camera goes up.)
            expectVec(c.cameraOffsetDir,
                Math.cos(angle),
                0,
                Math.sin(0.8),
                1e-9);
            // Up rotates from +Z by -0.8 around +Y to (-sin(0.8), 0, cos(0.8))
            expectVec(c.cameraUpVector,
                -Math.sin(0.8),
                0,
                Math.cos(0.8),
                1e-9);
        });

        test('captures drag frame automatically if not captured first', () => {
            const c = new CameraController({
                THREE,
                initialAngles: { theta: 0, phi: Math.PI / 2 },
            });
            c.setCameraMode('free');
            // No explicit capture call.
            c.applyOrbitDelta(10, 0);
            expect(c.dragOrbitUpAxis).not.toBeNull();
            expect(c.dragOrbitRightAxis).not.toBeNull();
        });

        test('the captured drag frame stays fixed across successive deltas', () => {
            const c = new CameraController({
                THREE,
                initialAngles: { theta: 0, phi: Math.PI / 2 }, // dir = +X
            });
            c.setCameraMode('free');
            c.captureOrbitDragFrame();
            const capturedUp = c.dragOrbitUpAxis.clone();
            const capturedRight = c.dragOrbitRightAxis.clone();
            for (let i = 0; i < 10; i += 1) {
                c.applyOrbitDelta(5, 5);
            }
            expectVec(c.dragOrbitUpAxis, capturedUp.x, capturedUp.y, capturedUp.z, 1e-12);
            expectVec(c.dragOrbitRightAxis, capturedRight.x, capturedRight.y, capturedRight.z, 1e-12);
        });
    });

    describe('clearOrbitDragFrame', () => {
        test('resets the captured axes to null', () => {
            const c = new CameraController({ THREE });
            c.captureOrbitDragFrame();
            expect(c.dragOrbitUpAxis).not.toBeNull();
            c.clearOrbitDragFrame();
            expect(c.dragOrbitUpAxis).toBeNull();
            expect(c.dragOrbitRightAxis).toBeNull();
        });
    });

    describe('getAdaptiveZoomFactor', () => {
        test('returns base factor when orbitDist is non-positive', () => {
            const c = new CameraController({ THREE, initialDistance: 0 });
            expect(c.getAdaptiveZoomFactor(false)).toBe(1.2);
            expect(c.getAdaptiveZoomFactor(true)).toBe(0.8);
        });

        test('zoom-in (factor > 1) at typical distance', () => {
            const c = new CameraController({ THREE, initialDistance: 10 });
            const factor = c.getAdaptiveZoomFactor(false);
            expect(factor).toBeGreaterThan(1);
        });

        test('zoom-out (factor < 1) at typical distance', () => {
            const c = new CameraController({ THREE, initialDistance: 10 });
            const factor = c.getAdaptiveZoomFactor(true);
            expect(factor).toBeLessThan(1);
        });

        test('scales more aggressively at larger distances', () => {
            const c1 = new CameraController({ THREE, initialDistance: 5 });
            const c2 = new CameraController({ THREE, initialDistance: 500 });
            const near = c1.getAdaptiveZoomFactor(false);
            const far = c2.getAdaptiveZoomFactor(false);
            expect(far).toBeGreaterThan(near);
        });
    });

    describe('getCameraSnapForDirection', () => {
        test('top direction (+Z) uses +Y up', () => {
            const c = new CameraController({ THREE });
            const snap = c.getCameraSnapForDirection({ x: 0, y: 0, z: 1 });
            expect(snap.offsetDir).toEqual({ x: 0, y: 0, z: 1 });
            expect(snap.upVector).toEqual({ x: 0, y: 1, z: 0 });
        });

        test('bottom direction (-Z) uses -Y up', () => {
            const c = new CameraController({ THREE });
            const snap = c.getCameraSnapForDirection({ x: 0, y: 0, z: -1 });
            expect(snap.upVector).toEqual({ x: 0, y: -1, z: 0 });
        });

        test('side directions use +Z up', () => {
            const c = new CameraController({ THREE });
            expect(c.getCameraSnapForDirection({ x: 1, y: 0, z: 0 }).upVector).toEqual({ x: 0, y: 0, z: 1 });
            expect(c.getCameraSnapForDirection({ x: 0, y: 1, z: 0 }).upVector).toEqual({ x: 0, y: 0, z: 1 });
        });
    });

    describe('animation', () => {
        test('animateTo + stepAnimation interpolates direction, up, distance, and center', () => {
            let now = 0;
            const c = new CameraController({
                THREE,
                initialAngles: { theta: 0, phi: Math.PI / 2 }, // dir = +X
                initialDistance: 10,
                center: { x: 0, y: 0, z: 0 },
                now: () => now,
            });
            c.animateTo({
                offsetDir: { x: 0, y: 1, z: 0 }, // 90° around +Z from +X
                upVector: { x: 0, y: 0, z: 1 },
                distance: 20,
                center: { x: 4, y: 0, z: 0 },
                durationMs: 100,
            });
            expect(c.hasAnimation()).toBe(true);

            // Step at the very end → final state.
            now = 100;
            const stillRunning = c.stepAnimation();
            expect(stillRunning).toBe(false);
            expect(c.hasAnimation()).toBe(false);
            expectVec(c.cameraOffsetDir, 0, 1, 0, 1e-9);
            expectVec(c.cameraUpVector, 0, 0, 1, 1e-9);
            expect(approxEqual(c.orbitDist, 20)).toBe(true);
            expect(approxEqual(c.cx, 4)).toBe(true);
        });

        test('stepAnimation reports still running before duration elapses', () => {
            let now = 0;
            const c = new CameraController({
                THREE,
                now: () => now,
            });
            c.animateTo({
                offsetDir: { x: 0, y: 1, z: 0 },
                distance: 5,
                durationMs: 100,
            });
            now = 50;
            const running = c.stepAnimation();
            expect(running).toBe(true);
        });

        test('animateTo with zero-length offsetDir is a no-op', () => {
            const c = new CameraController({ THREE });
            c.animateTo({ offsetDir: { x: 0, y: 0, z: 0 } });
            expect(c.hasAnimation()).toBe(false);
        });

        test('cancelAnimation drops in-flight animation', () => {
            let now = 0;
            const c = new CameraController({ THREE, now: () => now });
            c.animateTo({ offsetDir: { x: 0, y: 1, z: 0 }, durationMs: 100 });
            expect(c.hasAnimation()).toBe(true);
            c.cancelAnimation();
            expect(c.hasAnimation()).toBe(false);
            expect(c.stepAnimation()).toBe(false);
        });

        test('stepAnimation without active animation returns false', () => {
            const c = new CameraController({ THREE });
            expect(c.stepAnimation()).toBe(false);
        });
    });

    describe('buildStatePayload / applyStatePayload', () => {
        test('round-trips orbit center, angles, distance, and up vector', () => {
            const c = new CameraController({
                THREE,
                center: { x: 1, y: 2, z: 3 },
                initialDistance: 12.5,
                initialAngles: { theta: 0.4, phi: 1.1 },
                defaultUp: { x: 0, y: 0, z: 1 },
                cameraMode: 'free',
            });
            const payload = c.buildStatePayload();
            expect(payload.mode).toBe('free');
            expect(payload.orbitCenter).toEqual({ x: 1, y: 2, z: 3 });
            expect(payload.orbit.distance).toBe(12.5);
            expect(approxEqual(payload.orbit.theta, 0.4)).toBe(true);
            expect(approxEqual(payload.orbit.phi, 1.1)).toBe(true);

            const c2 = new CameraController({ THREE });
            c2.applyStatePayload(payload);
            const round = c2.buildStatePayload();
            expect(round.orbitCenter).toEqual(payload.orbitCenter);
            expect(round.orbit.distance).toBe(payload.orbit.distance);
            expect(approxEqual(round.orbit.theta, payload.orbit.theta, 1e-12)).toBe(true);
            expect(approxEqual(round.orbit.phi, payload.orbit.phi, 1e-12)).toBe(true);
            expect(c2.getCameraMode()).toBe('free');
            expectVec(c2.cameraUpVector, 0, 0, 1, 1e-12);
        });

        test('applyStatePayload ignores invalid fields gracefully', () => {
            const c = new CameraController({ THREE });
            const before = c.buildStatePayload();
            c.applyStatePayload({});
            c.applyStatePayload(null);
            c.applyStatePayload({ orbit: { theta: 'nope', phi: NaN, distance: -1 } });
            const after = c.buildStatePayload();
            expect(after.orbitCenter).toEqual(before.orbitCenter);
            expect(after.orbit.distance).toBe(before.orbit.distance);
        });

        test('applyStatePayload clamps incoming phi', () => {
            const c = new CameraController({ THREE });
            c.applyStatePayload({ orbit: { theta: 0, phi: 100 } });
            const angles = c.getOffsetAngles();
            expect(angles.phi).toBeLessThanOrEqual(Math.PI - 0.05 + 1e-9);
            expect(angles.phi).toBeGreaterThanOrEqual(0.05 - 1e-9);
        });

        test('applyStatePayload cancels in-flight animation', () => {
            let now = 0;
            const c = new CameraController({ THREE, now: () => now });
            c.animateTo({ offsetDir: { x: 0, y: 1, z: 0 }, durationMs: 100 });
            expect(c.hasAnimation()).toBe(true);
            c.applyStatePayload({ orbitCenter: { x: 0, y: 0, z: 0 } });
            expect(c.hasAnimation()).toBe(false);
        });
    });

    describe('translateCenter / setCenter / getCenter', () => {
        test('translateCenter adds to current center', () => {
            const c = new CameraController({ THREE, center: { x: 1, y: 2, z: 3 } });
            c.translateCenter(0.5, -1, 2);
            expect([c.cx, c.cy, c.cz]).toEqual([1.5, 1, 5]);
        });

        test('setCenter overwrites the center', () => {
            const c = new CameraController({ THREE });
            c.setCenter(10, 20, 30);
            expect([c.cx, c.cy, c.cz]).toEqual([10, 20, 30]);
        });

        test('getCenter returns a fresh THREE.Vector3 holding the center', () => {
            const c = new CameraController({ THREE, center: { x: 4, y: 5, z: 6 } });
            const v = c.getCenter();
            expectVec(v, 4, 5, 6);
            // Mutating the returned vector should not affect controller state.
            v.set(0, 0, 0);
            expect([c.cx, c.cy, c.cz]).toEqual([4, 5, 6]);
        });
    });
});
