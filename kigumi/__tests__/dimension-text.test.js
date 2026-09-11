const path = require('path');
const {
    parseLength, parseAngle, formatLength, formatAngle, whyNotALength,
} = require('../webview/dimension-text');

// The same table kumiki's tests/test_rule_dimensions.py reads. Python is
// authoritative; this suite exists so the two cannot drift apart silently.
const fixture = require(path.join(__dirname, '..', 'test-fixtures', 'dimension-parsing.json'));

describe('reading a length', () => {
    test.each(fixture.length.valid.map((c) => [c.input, c.defaultUnit, c.meters]))(
        '%p in %p is %p metres',
        (input, defaultUnit, meters) => {
            expect(parseLength(input, defaultUnit)).toBeCloseTo(meters, 9);
        },
    );

    test.each(fixture.length.invalid.map((c) => [c.input, c.why]))(
        'refuses %p (%s)',
        (input) => {
            expect(() => parseLength(input)).toThrow();
        },
    );

    test('an unknown default unit is refused', () => {
        expect(() => parseLength('10', 'furlongs')).toThrow();
    });
});

describe('reading an angle', () => {
    test.each(fixture.angle.valid.map((c) => [c.input, c.defaultUnit, c.radians]))(
        '%p in %p is %p radians',
        (input, defaultUnit, radians) => {
            expect(parseAngle(input, defaultUnit)).toBeCloseTo(radians, 9);
        },
    );

    test.each(fixture.angle.invalid.map((c) => [c.input, c.why]))(
        'refuses %p (%s)',
        (input) => {
            expect(() => parseAngle(input)).toThrow();
        },
    );
});

describe('writing a measurement down', () => {
    test.each(fixture.formatLength.map((c) => [c.meters, c.unit, c.text]))(
        '%p metres in %p is %p',
        (meters, unit, text) => {
            expect(formatLength(meters, unit)).toBe(text);
        },
    );

    test.each(fixture.formatAngle.map((c) => [c.radians, c.unit, c.text]))(
        '%p radians in %p is %p',
        (radians, unit, text) => {
            expect(formatAngle(radians, unit)).toBe(text);
        },
    );

    test('a decimal length round trips through its own formatting', () => {
        for (const meters of [0.45, 1.5, 0.0254, 0.03175, 0.9144, 0]) {
            for (const unit of ['mm', 'cm', 'm']) {
                expect(parseLength(formatLength(meters, unit))).toBeCloseTo(meters, 9);
            }
        }
    });

    test('an imperial length comes back snapped to the nearest tick', () => {
        // A tape has 1/32 marks on it, so inches are lossy by up to half a tick.
        const halfATick = 0.0254 / 64;
        for (const meters of [0.45, 1.5, 0.0254, 0.03175, 0.9144, 0]) {
            const written = parseLength(formatLength(meters, '"'));
            expect(Math.abs(written - meters)).toBeLessThanOrEqual(halfATick);
        }
        expect(formatLength(0.45, '"')).toBe('17 23/32"');
    });
});

describe('telling someone why their box is wrong', () => {
    test('says nothing when the text reads as a measurement', () => {
        expect(whyNotALength('450mm')).toBeNull();
        expect(whyNotALength('1 1/4"')).toBeNull();
    });

    test('gives a reason when it does not', () => {
        expect(whyNotALength('abc')).toMatch(/not a measurement/);
        expect(whyNotALength('10furlongs')).toMatch(/not a unit I know/);
        expect(whyNotALength("2'6")).toMatch(/leaves the unit off/);
    });

    test('a formula is not a measurement — the grammar is closed', () => {
        expect(whyNotALength('width*2')).not.toBeNull();
        expect(whyNotALength('10 + 5mm')).not.toBeNull();
    });
});
