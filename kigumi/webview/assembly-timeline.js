(function (globalScope) {
    // Framework-agnostic domain logic for the assembly preview timeline.
    //
    // Payload shape (produced by runner.py serialize_layers -> "assembly"):
    //   { steps: [{ order, suborder, substep, movements: [{ kumikiEphemeralId, memberKey,
    //                                                       direction: [x, y, z],  // unit
    //                                                       distance,  // base freed_after amount
    //                                                       dragged,
    //                                                       rotation: { axisPosition, axisDirection,
    //                                                                   angle } }] }],  // optional, radians
    //     warnings: [string],
    //     failure: { order, suborder, message, diagnostics: [string] } | null }
    //
    // A step is one animated motion. (order, suborder) is the AUTHORED
    // ordering (the suborder sequences motion within a joint — a peg pops
    // before the tenon slides); substep (1-based) sequences the additional
    // motions the SOLVER discovered within one ordering. Substep 1 gets a
    // labeled timeline mark; substeps > 1 get small unlabeled ticks.
    //
    // Scrub semantics: a scrub value of k means "the first k steps are fully
    // applied"; the fractional part linearly interpolates the next step.
    // Displacements accumulate per memberKey across steps (a member can be
    // dragged in one step and extracted in another) and are scaled by the
    // configurable disassembly multiplier.

    function isFiniteNumber(value) {
        return typeof value === 'number' && Number.isFinite(value);
    }

    function isVector3(value) {
        return Array.isArray(value) && value.length === 3 && value.every(isFiniteNumber);
    }

    function normalizeRotation(raw) {
        if (!raw || typeof raw !== 'object') {
            return null;
        }
        if (!isVector3(raw.axisPosition) || !isVector3(raw.axisDirection) || !isFiniteNumber(raw.angle)) {
            return null;
        }
        return {
            axisPosition: [...raw.axisPosition],
            axisDirection: [...raw.axisDirection],
            angle: raw.angle,
        };
    }

    function normalizeMovement(raw) {
        if (!raw || typeof raw !== 'object') {
            return null;
        }
        const direction = raw.direction;
        if (typeof raw.memberKey !== 'string' || raw.memberKey.length === 0) {
            return null;
        }
        if (!Array.isArray(direction) || direction.length !== 3 || !direction.every(isFiniteNumber)) {
            return null;
        }
        if (!isFiniteNumber(raw.distance) || raw.distance < 0) {
            return null;
        }
        return {
            kumikiEphemeralId: isFiniteNumber(raw.kumikiEphemeralId) ? raw.kumikiEphemeralId : null,
            memberKey: raw.memberKey,
            direction: [direction[0], direction[1], direction[2]],
            distance: raw.distance,
            dragged: Boolean(raw.dragged),
            rotation: normalizeRotation(raw.rotation),
        };
    }

    function normalizeFailure(raw) {
        if (!raw || typeof raw !== 'object' || typeof raw.message !== 'string') {
            return null;
        }
        return {
            order: isFiniteNumber(raw.order) ? raw.order : null,
            suborder: isFiniteNumber(raw.suborder) ? raw.suborder : 0,
            message: raw.message,
            diagnostics: Array.isArray(raw.diagnostics)
                ? raw.diagnostics.filter((entry) => typeof entry === 'string')
                : [],
        };
    }

    // Returns { steps, warnings, failure } or null when the payload is absent
    // or unusable (the timeline hides). A payload with no steps but a failure
    // or warnings is kept so the failure/warning UI can render.
    function normalizeAssemblyPayload(raw) {
        if (!raw || typeof raw !== 'object') {
            return null;
        }
        const steps = [];
        if (Array.isArray(raw.steps)) {
            for (const rawStep of raw.steps) {
                if (!rawStep || typeof rawStep !== 'object' || !isFiniteNumber(rawStep.order)) {
                    continue;
                }
                const movements = Array.isArray(rawStep.movements)
                    ? rawStep.movements.map(normalizeMovement).filter((movement) => movement !== null)
                    : [];
                steps.push({
                    order: rawStep.order,
                    suborder: isFiniteNumber(rawStep.suborder) ? rawStep.suborder : 0,
                    substep: isFiniteNumber(rawStep.substep) && rawStep.substep >= 1
                        ? Math.floor(rawStep.substep)
                        : 1,
                    movements,
                });
            }
        }
        const warnings = Array.isArray(raw.warnings)
            ? raw.warnings.filter((entry) => typeof entry === 'string')
            : [];
        const failure = normalizeFailure(raw.failure);
        if (steps.length === 0 && warnings.length === 0 && failure === null) {
            return null;
        }
        return { steps, warnings, failure };
    }

    // Map<memberKey, [dx, dy, dz]> for the given scrub position.
    function computeAssemblyOffsets(steps, scrubValue, multiplier) {
        const offsets = new Map();
        if (!Array.isArray(steps) || steps.length === 0) {
            return offsets;
        }
        const scale = isFiniteNumber(multiplier) && multiplier > 0 ? multiplier : 1;
        const clamped = Math.min(Math.max(isFiniteNumber(scrubValue) ? scrubValue : 0, 0), steps.length);
        for (let index = 0; index < steps.length; index += 1) {
            const fraction = Math.min(Math.max(clamped - index, 0), 1);
            if (fraction <= 0) {
                break;
            }
            for (const movement of steps[index].movements) {
                const amount = movement.distance * scale * fraction;
                const existing = offsets.get(movement.memberKey) || [0, 0, 0];
                offsets.set(movement.memberKey, [
                    existing[0] + movement.direction[0] * amount,
                    existing[1] + movement.direction[1] * amount,
                    existing[2] + movement.direction[2] * amount,
                ]);
            }
        }
        return offsets;
    }

    function multiplyQuaternions(a, b) {
        return [
            a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1],
            a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
            a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3],
            a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2],
        ];
    }

    function rotateVector(q, v) {
        const [x, y, z, w] = q;
        const tx = 2 * (y * v[2] - z * v[1]);
        const ty = 2 * (z * v[0] - x * v[2]);
        const tz = 2 * (x * v[1] - y * v[0]);
        return [
            v[0] + w * tx + (y * tz - z * ty),
            v[1] + w * ty + (z * tx - x * tz),
            v[2] + w * tz + (x * ty - y * tx),
        ];
    }

    // Map<memberKey, { quaternion: [x, y, z, w], shift: [x, y, z] }> for the
    // given scrub position: a point p of the member sits at
    // rotate(quaternion, p) + shift, before the member's offset is added.
    // Angles are not scaled by the disassembly multiplier.
    function computeAssemblyRotations(steps, scrubValue) {
        const rotations = new Map();
        if (!Array.isArray(steps) || steps.length === 0) {
            return rotations;
        }
        const clamped = Math.min(Math.max(isFiniteNumber(scrubValue) ? scrubValue : 0, 0), steps.length);
        for (let index = 0; index < steps.length; index += 1) {
            const fraction = Math.min(Math.max(clamped - index, 0), 1);
            if (fraction <= 0) {
                break;
            }
            for (const movement of steps[index].movements) {
                const rotation = movement.rotation;
                if (!rotation) {
                    continue;
                }
                const axis = rotation.axisDirection;
                const length = Math.hypot(axis[0], axis[1], axis[2]);
                if (length === 0) {
                    continue;
                }
                const half = (rotation.angle * fraction) / 2;
                const s = Math.sin(half) / length;
                const q = [axis[0] * s, axis[1] * s, axis[2] * s, Math.cos(half)];
                const pivot = rotation.axisPosition;
                const existing = rotations.get(movement.memberKey)
                    || { quaternion: [0, 0, 0, 1], shift: [0, 0, 0] };
                const turned = rotateVector(q, [
                    existing.shift[0] - pivot[0],
                    existing.shift[1] - pivot[1],
                    existing.shift[2] - pivot[2],
                ]);
                rotations.set(movement.memberKey, {
                    quaternion: multiplyQuaternions(q, existing.quaternion),
                    shift: [turned[0] + pivot[0], turned[1] + pivot[1], turned[2] + pivot[2]],
                });
            }
        }
        return rotations;
    }

    // Human-readable label for one step: "2" or "2.1" when a suborder is present.
    function getStepLabel(step) {
        const suborder = isFiniteNumber(step.suborder) ? step.suborder : 0;
        return suborder === 0 ? String(step.order) : `${step.order}.${suborder}`;
    }

    // Interior marks for the timeline track. Scrub value k = "first k steps
    // applied", so step i gets its mark at value i + 1. A step's FIRST substep
    // gets a labeled 'order' mark; later substeps of the same ordering get
    // small unlabeled 'substep' ticks.
    //
    // The end STATES are not marks: the viewer renders 'assembled' /
    // 'disassembled' as labels beside the slider, and on failure the right
    // label becomes the '✕' (the scrub range ends where disassembly first
    // fails, so the slider's end IS the failure point).
    function getTimelineMarks(steps) {
        const marks = [];
        const stepList = Array.isArray(steps) ? steps : [];
        for (let index = 0; index < stepList.length; index += 1) {
            const step = stepList[index];
            const substep = isFiniteNumber(step.substep) && step.substep >= 1 ? step.substep : 1;
            if (substep === 1) {
                marks.push({ value: index + 1, label: getStepLabel(step), kind: 'order' });
            } else {
                marks.push({ value: index + 1, label: '', kind: 'substep' });
            }
        }
        return marks;
    }

    // The slider range spans the solved steps plus one extra slot for the
    // failure mark so it is visibly "past the end".
    function getScrubMax(steps, failure) {
        const stepCount = Array.isArray(steps) ? steps.length : 0;
        return failure ? stepCount + 1 : stepCount;
    }

    const AssemblyTimeline = {
        normalizeAssemblyPayload,
        computeAssemblyOffsets,
        computeAssemblyRotations,
        getStepLabel,
        getTimelineMarks,
        getScrubMax,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { AssemblyTimeline };
    }
    globalScope.AssemblyTimeline = AssemblyTimeline;
})(typeof window !== 'undefined' ? window : globalThis);
