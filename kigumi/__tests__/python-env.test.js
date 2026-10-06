const { isLocalDevKigumiVersion, kumikiCompatiblePipSpec } = require('../python-env');

describe('kumikiCompatiblePipSpec', () => {
    test('a release pins kumiki to its own major.minor', () => {
        expect(kumikiCompatiblePipSpec('0.8.0')).toBe('kumiki~=0.8.0');
        expect(kumikiCompatiblePipSpec('0.8.3')).toBe('kumiki~=0.8.0');
    });

    test('a local dev build takes the latest kumiki', () => {
        // install.sh stamps local builds 999.0.0, which no released kumiki matches.
        expect(kumikiCompatiblePipSpec('999.0.0')).toBe('kumiki');
        expect(kumikiCompatiblePipSpec('0.999.0')).toBe('kumiki');
    });
});

describe('isLocalDevKigumiVersion', () => {
    test('999 in the major or minor marks a local build', () => {
        expect(isLocalDevKigumiVersion('999.0.0')).toBe(true);
        expect(isLocalDevKigumiVersion('0.999.0')).toBe(true);
        expect(isLocalDevKigumiVersion('0.9999.0')).toBe(true);
    });

    test('releases are not', () => {
        expect(isLocalDevKigumiVersion('0.8.0')).toBe(false);
        expect(isLocalDevKigumiVersion('1.2.3')).toBe(false);
    });
});
