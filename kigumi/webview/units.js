(function (globalScope) {
    'use strict';
    // Lengths arrive from the runner in metres. These turn one into what the
    // viewer shows, in whichever system it is set to.
    const dimensionText = (typeof require === 'function' && typeof module !== 'undefined')
        ? require('./dimension-text')
        : globalScope.KigumiDimensionText;

    const UNIT_SYSTEMS = ['metric', 'imperial', 'shaku'];
    const DEFAULT_UNIT_SYSTEM = 'metric';
    const MM_PER_M = 1000;
    const M_PER_INCH = 0.0254;
    const M_PER_SHAKU = 10 / 33;

    // What each system can be read to. A number is decimal places; "1/16" is
    // the tick a tape reads to, which only inches have.
    const DECIMALS = ['0', '1', '2', '3', '4'];
    const INCH_FRACTIONS = ['1/8', '1/16', '1/32', '1/64', '1/128'];
    const PRECISIONS = {
        metric: DECIMALS.slice(0, 4),
        imperial: [...DECIMALS, ...INCH_FRACTIONS],
        shaku: DECIMALS.slice(0, 4),
    };

    // Room is tight wherever these are shown -- a member list column, a line in
    // the selection pane -- so the defaults are as short as they can be while
    // still saying what they say: no decimals on a millimetre, one on an inch.
    // A shaku is a third of a metre, so it needs its three to say anything.
    const DEFAULT_PRECISIONS = { metric: '0', imperial: '1', shaku: '3' };

    const SCALE = { metric: 1 / MM_PER_M, imperial: M_PER_INCH, shaku: M_PER_SHAKU };
    // No space between the number and its unit, for the same reason.
    const SUFFIX = { metric: 'mm', imperial: '"', shaku: '尺' };

    /** 4.0 -> 4, 3.5 -> 3.5. Whole inches are the common case in a frame. */
    function trimTrailingZeros(text) {
        return text.includes('.') ? text.replace(/0+$/, '').replace(/\.$/, '') : text;
    }

    function unitSystemOrDefault(units) {
        return UNIT_SYSTEMS.includes(units) ? units : DEFAULT_UNIT_SYSTEM;
    }

    /** *precision* if *units* can be read to it, else that system's default. */
    function precisionOrDefault(units, precision) {
        const system = unitSystemOrDefault(units);
        return PRECISIONS[system].includes(precision) ? precision : DEFAULT_PRECISIONS[system];
    }

    /**
     * A length in metres, written for *units* to *precision* (one of
     * PRECISIONS[units]). Em dash when there is no number.
     */
    function formatLength(meters, units, precision) {
        // null and '' both convert to 0, which would print as a confident
        // measurement of zero where the honest answer is that there is none.
        if (meters === null || meters === undefined || meters === '') {
            return '—';
        }
        const value = Number(meters);
        if (!Number.isFinite(value)) {
            return '—';
        }
        const system = unitSystemOrDefault(units);
        const scaled = value / SCALE[system];
        const readTo = precisionOrDefault(system, precision);
        if (readTo.includes('/')) {
            return dimensionText.formatFraction(scaled, Number(readTo.split('/')[1])) + SUFFIX[system];
        }
        // -0.04 to one place is "-0.0", which trims to a "-0" nobody measured.
        const text = trimTrailingZeros(scaled.toFixed(Number(readTo)));
        return (text === '-0' ? '0' : text) + SUFFIX[system];
    }

    /**
     * How long a member is, preferring what it measures once its end cuts are
     * made. A timber with an end joint is never cut to length first, so its
     * stock length says little about the piece that comes out; cut_length is
     * absent only on an older runner, where the stock length is all there is.
     */
    function memberLengthMeters(mesh) {
        if (!mesh) {
            return null;
        }
        if (Number.isFinite(Number(mesh.cut_length))) {
            return Number(mesh.cut_length);
        }
        if (Number.isFinite(Number(mesh.prism_length))) {
            return Number(mesh.prism_length);
        }
        return null;
    }

    const KigumiUnits = {
        UNIT_SYSTEMS,
        DEFAULT_UNIT_SYSTEM,
        PRECISIONS,
        DEFAULT_PRECISIONS,
        precisionOrDefault,
        formatLength,
        memberLengthMeters,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiUnits;
    }
    globalScope.KigumiUnits = KigumiUnits;
})(typeof window !== 'undefined' ? window : globalThis);
