const { FEATURE_FLAGS, applyFeatureFlagsToLayersPayload } = require('../webview/feature-flags');

describe('FEATURE_FLAGS', () => {
  test('assemblyPreview ships enabled (solver v2)', () => {
    expect(FEATURE_FLAGS.assemblyPreview).toBe(true);
  });

  test('the flag registry is frozen (package-time, not runtime-mutable)', () => {
    expect(Object.isFrozen(FEATURE_FLAGS)).toBe(true);
  });
});

describe('applyFeatureFlagsToLayersPayload', () => {
  test('keeps the assembly field while assemblyPreview is enabled', () => {
    const payload = { frameName: 'f', timbers: [], joints: [], assembly: { steps: [] } };

    const result = applyFeatureFlagsToLayersPayload(payload);

    expect(result).toHaveProperty('assembly');
    expect(result.frameName).toBe('f');
  });

  test('strips the assembly field when the user setting is off', () => {
    const payload = { frameName: 'f', timbers: [], joints: [], assembly: { pending: true } };

    const result = applyFeatureFlagsToLayersPayload(payload, { assemblyPreviewSetting: false });

    expect(result).not.toHaveProperty('assembly');
    expect(result.frameName).toBe('f');
  });

  test('keeps the assembly field when the user setting is on', () => {
    const payload = { frameName: 'f', timbers: [], joints: [], assembly: { pending: true } };

    const result = applyFeatureFlagsToLayersPayload(payload, { assemblyPreviewSetting: true });

    expect(result).toHaveProperty('assembly');
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
