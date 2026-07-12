const { AssemblyTimeline } = require('../webview/assembly-timeline');

const {
  normalizeAssemblyPayload,
  computeAssemblyOffsets,
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

  test('missing suborder defaults to 0', () => {
    const payload = normalizeAssemblyPayload({
      steps: [{ order: 2, movements: [movement('beam#0', [0, 0, 1], 4)] }],
    });

    expect(payload.steps[0].suborder).toBe(0);
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

describe('timeline marks', () => {
  const steps = [
    { order: 1, suborder: 0, movements: [] },
    { order: 1, suborder: 1, movements: [] },
    { order: 3, suborder: 0, movements: [] },
  ];

  test('marks include assembled start and one mark per step with suborder labels', () => {
    const marks = getTimelineMarks(steps, null);

    expect(marks).toEqual([
      { value: 0, label: 'assembled', kind: 'start' },
      { value: 1, label: '1', kind: 'order' },
      { value: 2, label: '1.1', kind: 'order' },
      { value: 3, label: '3', kind: 'order' },
    ]);
    expect(getScrubMax(steps, null)).toBe(3);
  });

  test('failure adds an ✕ mark past the last solved step', () => {
    const failure = { order: 4, suborder: 0, message: 'stuck', diagnostics: [] };
    const marks = getTimelineMarks(steps, failure);

    expect(marks[marks.length - 1]).toEqual({ value: 4, label: '✕', kind: 'failure' });
    expect(getScrubMax(steps, failure)).toBe(4);
  });
});
