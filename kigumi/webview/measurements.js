(function (globalScope) {
    'use strict';
    // Where a dimension goes on the sheet.
    //
    // A drawing is a projection, so a measurement is computed in the plane of
    // the viewport it belongs to: the separation between its two anchors with
    // the part along the line of sight taken out. That is the number an
    // elevation is supposed to carry, and it is not the distance between the
    // two features in space -- two mortises at different depths, dimensioned on
    // the front elevation, read as their separation across that face.
    //
    // Pure on purpose: the projecting is the viewer's, the arithmetic is here.

    /** a - b, as a plain triple. */
    function subtract(a, b) {
        return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
    }

    function dot(a, b) {
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    }

    function length(v) {
        return Math.sqrt(dot(v, v));
    }

    /**
     * How far apart two world points are, seen from a given direction.
     *
     * The component along the line of sight is dropped, because it is the part
     * a projection does not show. Two points separated only in depth are zero
     * apart here, which is the degenerate case a viewport has to refuse rather
     * than dimension.
     */
    function projectedSeparation(a, b, look) {
        const delta = subtract(b, a);
        const gaze = length(look) > 0 ? look : [0, 0, 1];
        const unit = length(gaze);
        const along = dot(delta, gaze) / (unit * unit);
        return length([
            delta[0] - gaze[0] * along,
            delta[1] - gaze[1] * along,
            delta[2] - gaze[2] * along,
        ]);
    }

    // Below this the two anchors are on top of each other in this view, and
    // there is no direction to draw a dimension along.
    const DEGENERATE_PIXELS = 2;

    /**
     * The lines and label of one dimension, in the viewport's own pixels.
     *
     * Offset perpendicular to the run between the anchors, so the dimension
     * line sits clear of the thing it measures with witness lines reaching back
     * to it -- which is how a dimension is drawn on paper, and leaves the
     * drawing itself unobscured.
     *
     * null when the two anchors land on the same place: nothing meaningful can
     * be drawn, and a zero-length dimension line with a number beside it would
     * be a lie rather than an empty result.
     */
    function dimensionLayout(from, to, options) {
        const settings = options || {};
        const offset = settings.offset === undefined ? 24 : settings.offset;
        const gap = settings.gap === undefined ? 4 : settings.gap;
        const overshoot = settings.overshoot === undefined ? 6 : settings.overshoot;

        const run = [to.x - from.x, to.y - from.y];
        const span = Math.sqrt(run[0] * run[0] + run[1] * run[1]);
        if (span < DEGENERATE_PIXELS) {
            return null;
        }
        // Perpendicular to the run, consistently to one side of it.
        const away = [-run[1] / span, run[0] / span];

        const at = (point, distance) => ({
            x: point.x + away[0] * distance,
            y: point.y + away[1] * distance,
        });

        const lineFrom = at(from, offset);
        const lineTo = at(to, offset);
        return {
            line: { from: lineFrom, to: lineTo },
            // Short of the feature, and a little past the dimension line, so
            // neither end quite touches: the convention that keeps a drawing
            // readable where lines meet.
            witness: [
                { from: at(from, Math.sign(offset) * gap), to: at(from, offset + Math.sign(offset) * overshoot) },
                { from: at(to, Math.sign(offset) * gap), to: at(to, offset + Math.sign(offset) * overshoot) },
            ],
            label: {
                x: (lineFrom.x + lineTo.x) / 2,
                y: (lineFrom.y + lineTo.y) / 2,
                // Kept the right way up: text upside down is unreadable, and a
                // dimension read from the other side says the same thing.
                angle: normalizeAngle(Math.atan2(run[1], run[0]) * 180 / Math.PI),
            },
        };
    }

    function normalizeAngle(degrees) {
        let angle = degrees;
        while (angle > 90) {
            angle -= 180;
        }
        while (angle < -90) {
            angle += 180;
        }
        return angle;
    }

    const KigumiMeasurements = {
        projectedSeparation,
        dimensionLayout,
        DEGENERATE_PIXELS,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiMeasurements;
    }
    globalScope.KigumiMeasurements = KigumiMeasurements;
})(typeof window !== 'undefined' ? window : globalThis);
