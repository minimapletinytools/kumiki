(function (globalScope) {
    'use strict';
    // Lengths arrive from the runner in metres. These turn one into what the
    // viewer shows, in whichever system it is set to.
    const UNIT_SYSTEMS = ['metric', 'imperial'];
    const DEFAULT_UNIT_SYSTEM = 'metric';
    const MM_PER_M = 1000;
    const M_PER_INCH = 0.0254;

    // Room is tight wherever these are shown -- a member list column, a line in
    // the selection pane -- so they are as short as they can be while still
    // saying what they say: no decimals on a millimetre, one on an inch, and no
    // space between the number and its unit.
    const MM_DECIMALS = 0;
    const INCH_DECIMALS = 1;

    /** 4.0 -> 4, 3.5 -> 3.5. Whole inches are the common case in a frame. */
    function trimTrailingZeros(text) {
        return text.includes('.') ? text.replace(/0+$/, '').replace(/\.$/, '') : text;
    }

    /** A length in metres, written for *units*. Em dash when there is no number. */
    function formatLength(meters, units) {
        // null and '' both convert to 0, which would print as a confident
        // measurement of zero where the honest answer is that there is none.
        if (meters === null || meters === undefined || meters === '') {
            return '—';
        }
        const value = Number(meters);
        if (!Number.isFinite(value)) {
            return '—';
        }
        if (units === 'imperial') {
            return trimTrailingZeros((value / M_PER_INCH).toFixed(INCH_DECIMALS)) + '"';
        }
        return (value * MM_PER_M).toFixed(MM_DECIMALS) + 'mm';
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
        formatLength,
        memberLengthMeters,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiUnits;
    }
    globalScope.KigumiUnits = KigumiUnits;
})(typeof window !== 'undefined' ? window : globalThis);
