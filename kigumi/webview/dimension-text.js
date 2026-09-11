(function (globalScope) {
    'use strict';
    // A mirror of kumiki.rule's parse_length/parse_angle, close enough to tell
    // someone their box is wrong while they are still typing in it. Python is
    // authoritative: whatever the runner sends back on a refresh is the value,
    // and where the two disagree Python wins. The shared table in
    // kigumi/test-fixtures/dimension-parsing.json is what keeps them honest.
    const INCH = 0.0254;
    const FOOT = 0.3048;
    const SHAKU = 10 / 33;

    const LENGTH_UNITS = {
        inches: INCH, inch: INCH, in: INCH, '"': INCH, '”': INCH,
        feet: FOOT, foot: FOOT, ft: FOOT, "'": FOOT, '’': FOOT,
        mm: 0.001, cm: 0.01, m: 1, yd: 0.9144,
        shaku: SHAKU, '尺': SHAKU,
        sun: SHAKU / 10, '寸': SHAKU / 10,
        bu: SHAKU / 100, '分': SHAKU / 100,
    };

    const ANGLE_UNITS = {
        degrees: Math.PI / 180, degree: Math.PI / 180, deg: Math.PI / 180, '°': Math.PI / 180,
        radians: 1, radian: 1, rad: 1,
    };

    // A whole number, a fraction, or both — "1 1/4" and "1-1/4" being the two
    // ways the last gets written on a board.
    const NUMBER = '(?:\\d+[\\s-]\\d+\\/\\d+|\\d+\\/\\d+|\\d*\\.\\d+|\\d+\\.?)';

    function escapeForRegex(text) {
        return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    function unitsPattern(units) {
        return Object.keys(units)
            .sort((a, b) => b.length - a.length)
            .map(escapeForRegex)
            .join('|');
    }

    /** "1 1/4" -> 1.25. A fraction here is a literal, never an expression. */
    function parseNumber(text) {
        const mixed = /^(\d+)[\s-](\d+)\/(\d+)$/.exec(text);
        if (mixed) {
            if (Number(mixed[3]) === 0) {
                throw new Error('fraction has a zero denominator');
            }
            return Number(mixed[1]) + Number(mixed[2]) / Number(mixed[3]);
        }
        if (text.includes('/')) {
            const [num, den] = text.split('/');
            if (Number(den) === 0) {
                throw new Error('fraction has a zero denominator');
            }
            return Number(num) / Number(den);
        }
        return Number(text);
    }

    function parseMeasurement(text, units, defaultUnit, what) {
        if (typeof text === 'number' && Number.isFinite(text)) {
            return text * units[defaultUnit];
        }
        if (typeof text !== 'string') {
            throw new Error(`${what} must be written as text or a number`);
        }

        let cleaned = text.trim().replace(/−/g, '-');
        if (!cleaned) {
            throw new Error(`${what} is empty`);
        }
        const written = text.trim();

        let sign = 1;
        if (cleaned[0] === '-' || cleaned[0] === '+') {
            sign = cleaned[0] === '-' ? -1 : 1;
            cleaned = cleaned.slice(1).trim();
        }

        const term = new RegExp(`\\s*(${NUMBER})\\s*(${unitsPattern(units)})?\\s*`, 'iy');
        const terms = [];
        let position = 0;
        while (position < cleaned.length) {
            term.lastIndex = position;
            const match = term.exec(cleaned);
            if (!match || term.lastIndex === position) {
                const leftover = cleaned.slice(position).trim();
                if (terms.length && leftover) {
                    throw new Error(`${what} "${written}" ends in "${leftover}", which is not a unit I know`);
                }
                throw new Error(`${what} "${written}" is not a measurement I can read`);
            }
            terms.push([match[1], match[2]]);
            position = term.lastIndex;
        }

        if (!terms.length) {
            throw new Error(`${what} "${written}" has no number in it`);
        }
        if (terms.length > 1 && terms.some(([, unit]) => unit === undefined)) {
            throw new Error(`${what} "${written}" writes more than one measurement but leaves the unit off one of them`);
        }

        let total = 0;
        for (const [numberText, unitText] of terms) {
            const unit = unitText === undefined ? defaultUnit : unitText.toLowerCase();
            total += parseNumber(numberText) * units[unit];
        }
        return sign * total;
    }

    /** A length, in metres, from what someone wrote. Throws if it is not one. */
    function parseLength(text, defaultUnit = 'mm') {
        if (!Object.prototype.hasOwnProperty.call(LENGTH_UNITS, defaultUnit)) {
            throw new Error(`"${defaultUnit}" is not a length unit`);
        }
        return parseMeasurement(text, LENGTH_UNITS, defaultUnit, 'a length');
    }

    /** An angle, in radians, from what someone wrote. Throws if it is not one. */
    function parseAngle(text, defaultUnit = 'deg') {
        if (!Object.prototype.hasOwnProperty.call(ANGLE_UNITS, defaultUnit)) {
            throw new Error(`"${defaultUnit}" is not an angle unit`);
        }
        return parseMeasurement(text, ANGLE_UNITS, defaultUnit, 'an angle');
    }

    function trimZeros(text) {
        return text.includes('.') ? text.replace(/0+$/, '').replace(/\.$/, '') : text;
    }

    // Enough places to hold a hundredth of a millimetre in whatever unit is
    // being written — 2 for mm, 5 for m.
    function decimalsFor(unit) {
        return Math.max(0, Math.round(Math.log10(LENGTH_UNITS[unit] / 1e-5)));
    }

    function greatestCommonDivisor(a, b) {
        return b === 0 ? a : greatestCommonDivisor(b, a % b);
    }

    function formatFraction(value, denominator) {
        const sign = value < 0 ? '-' : '';
        const magnitude = Math.abs(value);
        let whole = Math.trunc(magnitude);
        let ticks = Math.round((magnitude - whole) * denominator);
        if (ticks === denominator) {
            whole += 1;
            ticks = 0;
        }
        if (ticks === 0) {
            return `${sign}${whole}`;
        }
        const common = greatestCommonDivisor(ticks, denominator);
        const numerator = ticks / common;
        const den = denominator / common;
        return whole ? `${sign}${whole} ${numerator}/${den}` : `${sign}${numerator}/${den}`;
    }

    const FRACTION_UNITS = new Set(['"', 'in', 'inch', 'inches', "'", 'ft', 'foot', 'feet']);

    /**
     * A length in metres, written the way it would be on a cut list. Imperial
     * snaps to the nearest 1/denominator, because that is what a tape reads —
     * so this is lossy by up to half a tick and must not be used to re-derive
     * a value that someone typed.
     */
    function formatLength(meters, unit = 'mm', denominator = 32) {
        if (!Object.prototype.hasOwnProperty.call(LENGTH_UNITS, unit)) {
            throw new Error(`"${unit}" is not a length unit`);
        }
        const value = meters / LENGTH_UNITS[unit];
        if (FRACTION_UNITS.has(unit)) {
            return formatFraction(value, denominator) + unit;
        }
        return trimZeros(value.toFixed(decimalsFor(unit))) + unit;
    }

    /** An angle in radians, written for people. */
    function formatAngle(radians, unit = 'deg') {
        if (!Object.prototype.hasOwnProperty.call(ANGLE_UNITS, unit)) {
            throw new Error(`"${unit}" is not an angle unit`);
        }
        return trimZeros((radians / ANGLE_UNITS[unit]).toFixed(4)) + unit;
    }

    /** null when *text* reads as a measurement, otherwise why it does not. */
    function whyNotALength(text, defaultUnit = 'mm') {
        try {
            parseLength(text, defaultUnit);
            return null;
        } catch (error) {
            return error.message;
        }
    }

    function whyNotAnAngle(text, defaultUnit = 'deg') {
        try {
            parseAngle(text, defaultUnit);
            return null;
        } catch (error) {
            return error.message;
        }
    }

    const KigumiDimensionText = {
        parseLength,
        parseAngle,
        formatLength,
        formatAngle,
        whyNotALength,
        whyNotAnAngle,
        LENGTH_UNITS,
        ANGLE_UNITS,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiDimensionText;
    }
    globalScope.KigumiDimensionText = KigumiDimensionText;
})(typeof window !== 'undefined' ? window : globalThis);
