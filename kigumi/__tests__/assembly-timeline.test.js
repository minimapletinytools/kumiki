const { AssemblyTimeline } = require('../webview/assembly-timeline');

const {
  normalizeAssemblyPayload,
  computeAssemblyOffsets,
  computeAssemblyRotations,
  getTimelineMarks,
  getScrubMax,
} = AssemblyTimeline;

function movement(memberKey, direction, distance, extra = {}) {
  return { kumikiEphemeralId: 1, memberKey, direction, distance, dragged: false, ...extra };
}

describe('normalizeAssemblyPayload', () => {
  test('null and garbage payloads normalize to null', () => {
    expect(normalizeAssemblyPayload(null)).toBeNull();
    expect(normalizeAssemblyPayload(undefined)).toBeNull();
    expect(normalizeAssemblyPayload('nope')).toBeNull();
    expect(normalizeAssemblyPayload({})).toBeNull();
    expect(normalizeAssemblyPayload({ steps: [], warnings: [], failure: null })).toBeNull();
  });

  test('valid payload passes through', () => {
    const payload = normalizeAssemblyPayload({
      steps: [{ order: 1, suborder: 1, movements: [movement('beam#0', [0, 0, 1], 4)] }],
      warnings: ['careful'],
      failure: null,
    });

    expect(payload.steps).toHaveLength(1);
    expect(payload.steps[0].order).toBe(1);
    expect(payload.steps[0].suborder).toBe(1);
    expect(payload.steps[0].movements[0].memberKey).toBe('beam#0');
    expect(payload.warnings).toEqual(['careful']);
    expect(payload.failure).toBeNull();
  });

  test('missing suborder defaults to 0 and missing substep defaults to 1', () => {
    const payload = normalizeAssemblyPayload({
      steps: [{ order: 2, movements: [movement('beam#0', [0, 0, 1], 4)] }],
    });

    expect(payload.steps[0].suborder).toBe(0);
    expect(payload.steps[0].substep).toBe(1);
  });

  test('substep passes through', () => {
    const payload = normalizeAssemblyPayload({
      steps: [{ order: 2, suborder: 0, substep: 3, movements: [movement('beam#0', [0, 0, 1], 4)] }],
    });

    expect(payload.steps[0].substep).toBe(3);
  });

  test('invalid movements are dropped', () => {
    const payload = normalizeAssemblyPayload({
      steps: [{
        order: 1,
        movements: [
          movement('good#0', [1, 0, 0], 2),
          movement('bad-direction#0', [1, 0], 2),
          movement('bad-distance#0', [1, 0, 0], Number.NaN),
          { direction: [1, 0, 0], distance: 1 }, // no memberKey
        ],
      }],
    });

    expect(payload.steps[0].movements).toHaveLength(1);
    expect(payload.steps[0].movements[0].memberKey).toBe('good#0');
  });

  test('a pending placeholder never normalizes into renderable data', () => {
    // While the runner is still solving, the layers payload carries
    // {pending: true}; that must never be mistaken for a solved payload.
    expect(normalizeAssemblyPayload({ pending: true })).toBeNull();
  });

  test('failure-only payload is kept for the error UI', () => {
    const payload = normalizeAssemblyPayload({
      steps: [],
      warnings: [],
      failure: { order: 2, suborder: 1, message: 'stuck', diagnostics: ['a --> b'] },
    });

    expect(payload.steps).toEqual([]);
    expect(payload.failure).toEqual({ order: 2, suborder: 1, message: 'stuck', diagnostics: ['a --> b'] });
  });
});

describe('computeAssemblyOffsets', () => {
  const steps = [
    { order: 1, movements: [movement('beam#0', [0, 0, 1], 4), movement('brace#0', [0, 0, 1], 4, { dragged: true })] },
    { order: 2, movements: [movement('beam#0', [1, 0, 0], 2), movement('post#0', [0, 1, 0], 6)] },
  ];

  test('scrub 0 produces no offsets', () => {
    expect(computeAssemblyOffsets(steps, 0, 1.5).size).toBe(0);
  });

  test('fractional scrub interpolates the active step', () => {
    const offsets = computeAssemblyOffsets(steps, 0.5, 1);

    expect(offsets.get('beam#0')).toEqual([0, 0, 2]);
    expect(offsets.get('brace#0')).toEqual([0, 0, 2]);
    expect(offsets.has('post#0')).toBe(false);
  });

  test('offsets accumulate across steps for the same member', () => {
    const offsets = computeAssemblyOffsets(steps, 2, 1);

    expect(offsets.get('beam#0')).toEqual([2, 0, 4]);
    expect(offsets.get('post#0')).toEqual([0, 6, 0]);
  });

  test('multiplier scales all offsets', () => {
    const offsets = computeAssemblyOffsets(steps, 2, 1.5);

    expect(offsets.get('beam#0')).toEqual([3, 0, 6]);
  });

  test('scrub clamps past the end', () => {
    const clamped = computeAssemblyOffsets(steps, 99, 1);
    const exact = computeAssemblyOffsets(steps, 2, 1);

    expect(clamped).toEqual(exact);
  });

  test('empty steps produce no offsets', () => {
    expect(computeAssemblyOffsets([], 1, 1.5).size).toBe(0);
    expect(computeAssemblyOffsets(null, 1, 1.5).size).toBe(0);
  });
});

describe('computeAssemblyRotations', () => {
  const quarterTurn = { axisPosition: [0, -1, 1], axisDirection: [1, 0, 0], angle: Math.PI / 2 };
  const steps = [
    { order: 1, movements: [movement('x#0', [1, 0, 0], 0, { rotation: quarterTurn })] },
    { order: 1, movements: [movement('y#0', [1, 0, 0], 2)] },
  ];
  const place = (pose, point) => {
    const [x, y, z, w] = pose.quaternion;
    const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
    const t = cross([x, y, z], point).map((c) => 2 * c);
    const u = cross([x, y, z], t);
    return point.map((c, i) => c + w * t[i] + u[i] + pose.shift[i]);
  };
  const expectClose = (actual, expected) => actual.forEach((c, i) => expect(c).toBeCloseTo(expected[i]));

  test('normalization keeps a valid rotation and drops a malformed one', () => {
    const payload = normalizeAssemblyPayload({
      steps: [{ order: 1, movements: [
        movement('x#0', [1, 0, 0], 0, { rotation: quarterTurn }),
        movement('y#0', [1, 0, 0], 0, { rotation: { angle: 1 } }),
      ] }],
    });

    expect(payload.steps[0].movements[0].rotation).toEqual(quarterTurn);
    expect(payload.steps[0].movements[1].rotation).toBeNull();
  });

  test('a full step turns the member about the pivot line', () => {
    const pose = computeAssemblyRotations(steps, 1).get('x#0');

    expectClose(place(pose, [5, -1, 1]), [5, -1, 1]);
    expectClose(place(pose, [0, 0, 0]), [0, 0, 2]);
  });

  test('fractional scrub interpolates the angle', () => {
    const pose = computeAssemblyRotations(steps, 0.5).get('x#0');

    expect(pose.quaternion[3]).toBeCloseTo(Math.cos(Math.PI / 8));
  });

  test('members without a rotation are absent', () => {
    expect(computeAssemblyRotations(steps, 2).has('y#0')).toBe(false);
    expect(computeAssemblyRotations(steps, 0).size).toBe(0);
    expect(computeAssemblyRotations(null, 1).size).toBe(0);
  });
});

describe('timeline marks', () => {
  const steps = [
    { order: 1, suborder: 0, substep: 1, movements: [] },
    { order: 1, suborder: 1, substep: 1, movements: [] },
    { order: 3, suborder: 0, substep: 1, movements: [] },
  ];

  test('one interior mark per step with suborder labels (end states are the viewer labels)', () => {
    const marks = getTimelineMarks(steps);

    expect(marks).toEqual([
      { value: 1, label: '1', kind: 'order' },
      { value: 2, label: '1.1', kind: 'order' },
      { value: 3, label: '3', kind: 'order' },
    ]);
    expect(getScrubMax(steps, null)).toBe(3);
  });

  test('solver substeps beyond the first render as unlabeled ticks', () => {
    const substepSteps = [
      { order: 1, suborder: 0, substep: 1, movements: [] },
      { order: 1, suborder: 0, substep: 2, movements: [] },
      { order: 1, suborder: 0, substep: 3, movements: [] },
      { order: 2, suborder: 0, substep: 1, movements: [] },
    ];
    const marks = getTimelineMarks(substepSteps);

    expect(marks).toEqual([
      { value: 1, label: '1', kind: 'order' },
      { value: 2, label: '', kind: 'substep' },
      { value: 3, label: '', kind: 'substep' },
      { value: 4, label: '2', kind: 'order' },
    ]);
  });

  test('no marks when there are no steps', () => {
    expect(getTimelineMarks([])).toEqual([]);
    expect(getTimelineMarks(null)).toEqual([]);
  });

  test('failure extends the scrub range one past the last solved step', () => {
    // The failure point is the end of the scrub range; the viewer renders the
    // ✕ as the right-hand end label there, not as an interior mark.
    const failure = { order: 4, suborder: 0, message: 'stuck', diagnostics: [] };

    expect(getTimelineMarks(steps)).toHaveLength(3);
    expect(getScrubMax(steps, failure)).toBe(4);
  });
});
