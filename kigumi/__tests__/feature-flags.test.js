const { FEATURE_FLAGS, applyFeatureFlagsToLayersPayload } = require('../webview/feature-flags');

describe('FEATURE_FLAGS', () => {
  test('assemblyPreview ships disabled while the feature is under development', () => {
    expect(FEATURE_FLAGS.assemblyPreview).toBe(false);
  });

  test('the flag registry is frozen (package-time, not runtime-mutable)', () => {
    expect(Object.isFrozen(FEATURE_FLAGS)).toBe(true);
  });
});

describe('applyFeatureFlagsToLayersPayload', () => {
  test('strips the assembly field while assemblyPreview is disabled', () => {
    const payload = { frameName: 'f', timbers: [], joints: [], assembly: { steps: [] } };

    const result = applyFeatureFlagsToLayersPayload(payload);

    expect(result).not.toHaveProperty('assembly');
    expect(result.frameName).toBe('f');
  });

  test('leaves payloads without an assembly field untouched', () => {
    const payload = { frameName: 'f', timbers: [] };

    expect(applyFeatureFlagsToLayersPayload(payload)).toEqual(payload);
  });

  test('passes through null/non-object payloads unchanged', () => {
    expect(applyFeatureFlagsToLayersPayload(null)).toBeNull();
    expect(applyFeatureFlagsToLayersPayload(undefined)).toBeUndefined();
  });
});
