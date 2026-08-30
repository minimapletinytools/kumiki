const { formatLength, memberLengthMeters, DEFAULT_UNIT_SYSTEM } = require('../webview/units.js');

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
