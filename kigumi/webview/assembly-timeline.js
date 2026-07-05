(function (globalScope) {
    // Framework-agnostic domain logic for the assembly preview timeline.
    //
    // Payload shape (produced by runner.py serialize_layers -> "assembly"):
    //   { steps: [{ order, suborder, movements: [{ kumikiId, memberKey,
    //                                              direction: [x, y, z],  // unit
    //                                              distance,  // base freed_after amount
    //                                              dragged }] }],
    //     warnings: [string],
    //     failure: { order, suborder, message, diagnostics: [string] } | null }
    //
    // A step is one (order, suborder) extraction: the suborder sequences
    // motion WITHIN a joint (a peg pops before the tenon slides).
    //
    // Scrub semantics: a scrub value of k means "the first k steps are fully
    // applied"; the fractional part linearly interpolates the next step.
    // Displacements accumulate per memberKey across steps (a member can be
    // dragged in one step and extracted in another) and are scaled by the
    // configurable disassembly multiplier.

    function isFiniteNumber(value) {
        return typeof value === 'number' && Number.isFinite(value);
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
            kumikiId: isFiniteNumber(raw.kumikiId) ? raw.kumikiId : null,
            memberKey: raw.memberKey,
            direction: [direction[0], direction[1], direction[2]],
            distance: raw.distance,
            dragged: Boolean(raw.dragged),
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

    // Human-readable label for one step: "2" or "2.1" when a suborder is present.
    function getStepLabel(step) {
        const suborder = isFiniteNumber(step.suborder) ? step.suborder : 0;
        return suborder === 0 ? String(step.order) : `${step.order}.${suborder}`;
    }

    // Marks for the timeline track. Scrub value k = "first k steps applied",
    // so step i gets its mark at value i + 1; value 0 is the assembled state.
    // When a failure is present an extra '✕' mark sits past the last solved step.
    function getTimelineMarks(steps, failure) {
        const marks = [{ value: 0, label: 'assembled', kind: 'start' }];
        const stepList = Array.isArray(steps) ? steps : [];
        for (let index = 0; index < stepList.length; index += 1) {
            marks.push({ value: index + 1, label: getStepLabel(stepList[index]), kind: 'order' });
        }
        if (failure) {
            marks.push({ value: stepList.length + 1, label: '✕', kind: 'failure' });
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
        getStepLabel,
        getTimelineMarks,
        getScrubMax,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { AssemblyTimeline };
    }
    globalScope.AssemblyTimeline = AssemblyTimeline;
})(typeof window !== 'undefined' ? window : globalThis);
