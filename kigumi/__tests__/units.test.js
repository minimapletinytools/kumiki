const {
    formatLength, memberLengthMeters, precisionOrDefault, DEFAULT_UNIT_SYSTEM, PRECISIONS,
} = require('../webview/units.js');

describe('formatLength', () => {
    test('metric reads in whole millimetres, tight against the unit', () => {
        expect(formatLength(1.2192, 'metric')).toBe('1219mm');
    });

    test('imperial reads in inches', () => {
        expect(formatLength(1.2192, 'imperial')).toBe('48"');
    });

    test('a whole number of inches keeps no decimals', () => {
        // 4" x 4" reads better than 4.00" x 4.00" on a member.
        expect(formatLength(0.1016, 'imperial')).toBe('4"');
    });

    test('a fractional inch keeps only the digits it needs', () => {
        expect(formatLength(0.0889, 'imperial')).toBe('3.5"');
    });

    test('inches round to one decimal rather than growing the column', () => {
        expect(formatLength(0.08890 + 0.0001, 'imperial')).toBe('3.5"');
    });

    test('an unknown system falls back to metric', () => {
        expect(formatLength(0.1016, 'furlongs')).toBe(formatLength(0.1016, DEFAULT_UNIT_SYSTEM));
    });

    test('a missing length is an em dash rather than NaN', () => {
        expect(formatLength(undefined, 'imperial')).toBe('—');
        expect(formatLength(null, 'metric')).toBe('—');
        expect(formatLength('not a length', 'metric')).toBe('—');
    });
});

describe('formatLength to a chosen precision', () => {
    test('millimetres go to three places', () => {
        expect(PRECISIONS.metric).toEqual(['0', '1', '2', '3']);
        expect(formatLength(0.0889123, 'metric', '0')).toBe('89mm');
        expect(formatLength(0.0889123, 'metric', '1')).toBe('88.9mm');
        expect(formatLength(0.0889123, 'metric', '3')).toBe('88.912mm');
    });

    test('inches go to four places, or to a tick on the tape', () => {
        expect(PRECISIONS.imperial).toEqual(
            ['0', '1', '2', '3', '4', '1/8', '1/16', '1/32', '1/64', '1/128']);
        const meters = 3.4567 * 0.0254;
        expect(formatLength(meters, 'imperial', '0')).toBe('3"');
        expect(formatLength(meters, 'imperial', '4')).toBe('3.4567"');
        expect(formatLength(meters, 'imperial', '1/8')).toBe('3 1/2"');
        expect(formatLength(meters, 'imperial', '1/16')).toBe('3 7/16"');
        expect(formatLength(meters, 'imperial', '1/128')).toBe('3 29/64"');
    });

    test('a fraction reduces, and rolls over into the next inch', () => {
        expect(formatLength(0.5 * 0.0254, 'imperial', '1/64')).toBe('1/2"');
        expect(formatLength(3.99 * 0.0254, 'imperial', '1/8')).toBe('4"');
    });

    test('shaku go to three places', () => {
        expect(PRECISIONS.shaku).toEqual(['0', '1', '2', '3']);
        // 3.03m is ten shaku; 4" is a third of one.
        expect(formatLength(3.03030303, 'shaku', '3')).toBe('10尺');
        expect(formatLength(0.1016, 'shaku', '3')).toBe('0.335尺');
        expect(formatLength(0.1016, 'shaku', '1')).toBe('0.3尺');
        expect(formatLength(0.1016, 'shaku')).toBe('0.335尺');
    });

    test('trailing zeros are dropped whatever the precision', () => {
        expect(formatLength(0.1016, 'imperial', '4')).toBe('4"');
        expect(formatLength(0.5, 'metric', '3')).toBe('500mm');
    });

    test('something that rounds to nothing is not a negative nothing', () => {
        expect(formatLength(-0.00001, 'metric', '1')).toBe('0mm');
    });

    test('a precision the units cannot be read to falls back to their default', () => {
        // Millimetres have no sixteenths; this is what is left over when the
        // units change under a precision chosen for inches.
        expect(formatLength(0.0889, 'metric', '1/16')).toBe('89mm');
        expect(precisionOrDefault('metric', '1/16')).toBe('0');
        expect(precisionOrDefault('imperial', '1/16')).toBe('1/16');
    });
});

describe('memberLengthMeters', () => {
    test('the finished length wins over the stock it was cut from', () => {
        // A timber with an end joint is never cut to length first, so these
        // differ for most of a frame.
        expect(memberLengthMeters({ cut_length: 0.6223, prism_length: 1.2192 })).toBe(0.6223);
    });

    test('stock length is the fallback when a runner sends no cut length', () => {
        expect(memberLengthMeters({ prism_length: 1.2192 })).toBe(1.2192);
    });

    test('a member with neither has no length to report', () => {
        expect(memberLengthMeters({})).toBeNull();
        expect(memberLengthMeters(null)).toBeNull();
    });
});
