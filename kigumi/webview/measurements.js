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
    // Which measurements a pair of features admits is decided by what the two
    // project to here, not by what they are. The table of that, and of what is
    // worth adding later, is on MeasureKind in kumiki/drawing.py; this applies
    // it, since only the viewport knows how anything lies to the view.
    //
    // Pure on purpose: the projecting is the viewer's, the arithmetic is here.

    // How square something has to be to the view before it counts as square:
    // an edge a hair off end-on still projects to a line, just a very short
    // one, and calling it a point would refuse a dimension that is drawable.
    const ALIGNMENT_EPSILON = 1e-3;

    // Two projected lines within this of parallel are treated as parallel: the
    // angle between them would be a number nobody wrote down deliberately, and
    // their separation is what was meant.
    const PARALLEL_EPSILON = 1e-2;

    /**
     * What a feature looks like once projected into a viewport.
     *
     * This, not what the feature is, decides what can be measured: a face seen
     * edge-on behaves as a line, an edge seen end-on behaves as a point, and a
     * face seen at any other angle covers the view and cannot be dimensioned at
     * all.
     */
    function projectedForm(geometry, look) {
        if (!geometry || !geometry.kind) {
            return { form: 'none' };
        }
        const gaze = normalized(look);
        if (geometry.kind === 'point') {
            return { form: 'point' };
        }
        if (geometry.kind === 'line') {
            const direction = normalized(geometry.direction || [0, 0, 0]);
            const alongView = Math.abs(dot(direction, gaze));
            return alongView > 1 - ALIGNMENT_EPSILON
                ? { form: 'point' }
                : { form: 'line', direction: flatten(direction, gaze) };
        }
        if (geometry.kind === 'plane') {
            const normal = normalized(geometry.normal || [0, 0, 0]);
            const facingView = Math.abs(dot(normal, gaze));
            if (facingView > ALIGNMENT_EPSILON) {
                // Not edge-on: it covers the view, and an area has no distance.
                return { form: 'area' };
            }
            // Edge-on, so it draws as a line running along the plane, square to
            // its normal and to the line of sight.
            return { form: 'line', direction: cross(normal, gaze) };
        }
        return { form: 'none' };
    }

    /** The part of a direction that survives projection. */
    function flatten(direction, gaze) {
        const along = dot(direction, gaze);
        return normalized([
            direction[0] - gaze[0] * along,
            direction[1] - gaze[1] * along,
            direction[2] - gaze[2] * along,
        ]);
    }

    function cross(a, b) {
        return normalized([
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        ]);
    }

    function normalized(v) {
        const size = length(v);
        return size > 0 ? [v[0] / size, v[1] / size, v[2] / size] : [0, 0, 0];
    }

    /**
     * Which measurements this pair admits in this viewport, best first.
     *
     * Empty when there is nothing to measure -- a face that is not edge-on, or
     * two features that project onto each other. The caller says why rather
     * than drawing nothing without explanation.
     */
    function availableKinds(formA, formB) {
        if (formA.form === 'none' || formB.form === 'none') {
            return [];
        }
        if (formA.form === 'area' || formB.form === 'area') {
            // A face seen at an angle covers the view: there is no line to
            // measure to, and its centre is a point about nothing.
            return [];
        }
        const forms = [formA.form, formB.form].sort().join('-');
        if (forms === 'point-point') {
            return ['aligned', 'horizontal', 'vertical'];
        }
        if (forms === 'line-point') {
            return ['perpendicular'];
        }
        // Two lines: parallel ones have a separation, crossing ones an angle.
        const alignment = Math.abs(dot(formA.direction, formB.direction));
        return alignment > 1 - PARALLEL_EPSILON
            ? ['perpendicular', 'horizontal', 'vertical']
            : ['angle'];
    }

    /** Whether a measurement asking for `kind` can be drawn from these forms. */
    function kindApplies(kind, formA, formB) {
        return availableKinds(formA, formB).indexOf(kind) !== -1;
    }

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

    /**
     * What one measurement comes to, in world units or degrees.
     *
     * Everything is computed with the depth taken out first, because a drawing
     * is a projection and the number it carries is the one seen in the view.
     */
    function measureValue(kind, from, to, formA, formB, axes) {
        const gaze = normalized(axes.look);
        const delta = subtract(to, from);
        const along = dot(delta, gaze);
        const flat = [
            delta[0] - gaze[0] * along,
            delta[1] - gaze[1] * along,
            delta[2] - gaze[2] * along,
        ];

        if (kind === 'angle') {
            const facing = Math.min(1, Math.abs(dot(formA.direction, formB.direction)));
            return { unit: 'angle', value: Math.acos(facing) * 180 / Math.PI };
        }
        if (kind === 'horizontal') {
            return { unit: 'length', value: Math.abs(dot(flat, normalized(axes.right))) };
        }
        if (kind === 'vertical') {
            return { unit: 'length', value: Math.abs(dot(flat, normalized(axes.up))) };
        }
        if (kind === 'perpendicular') {
            // Square to whichever of the two is a line: for a point and a line
            // that is the point's distance from it, and for two parallel lines
            // the gap between them.
            const line = formA.form === 'line' ? formA : formB;
            const direction = normalized(line.direction);
            const slide = dot(flat, direction);
            return {
                unit: 'length',
                value: length([
                    flat[0] - direction[0] * slide,
                    flat[1] - direction[1] * slide,
                    flat[2] - direction[2] * slide,
                ]),
            };
        }
        return { unit: 'length', value: length(flat) };
    }

    /**
     * The arc of an angle dimension, around where the two lines cross.
     *
     * Drawn at the crossing rather than between the two features, because an
     * angle is a property of the corner they make and reads as nothing anywhere
     * else. null when they are too near parallel to have a crossing on the
     * sheet -- which the rules should already have refused, but a dimension
     * drawn from a crossing at infinity would be worse than none.
     */
    function angleLayout(fromPoint, fromDirection, toPoint, toDirection, options) {
        const settings = options || {};
        const radius = settings.radius === undefined ? 34 : settings.radius;
        const cross2d = fromDirection.x * toDirection.y - fromDirection.y * toDirection.x;
        if (Math.abs(cross2d) < 1e-6) {
            return null;
        }
        const between = { x: toPoint.x - fromPoint.x, y: toPoint.y - fromPoint.y };
        const travel = (between.x * toDirection.y - between.y * toDirection.x) / cross2d;
        const vertex = {
            x: fromPoint.x + fromDirection.x * travel,
            y: fromPoint.y + fromDirection.y * travel,
        };

        // Toward each feature, so the arc is drawn in the corner being measured
        // rather than in the one opposite it.
        const facing = (point, direction) => {
            const towards = (point.x - vertex.x) * direction.x + (point.y - vertex.y) * direction.y;
            return towards < 0 ? { x: -direction.x, y: -direction.y } : direction;
        };
        const first = facing(fromPoint, fromDirection);
        const second = facing(toPoint, toDirection);

        const startAngle = Math.atan2(first.y, first.x);
        const endAngle = Math.atan2(second.y, second.x);
        let sweep = endAngle - startAngle;
        while (sweep > Math.PI) {
            sweep -= 2 * Math.PI;
        }
        while (sweep < -Math.PI) {
            sweep += 2 * Math.PI;
        }
        const midAngle = startAngle + sweep / 2;
        return {
            vertex,
            start: { x: vertex.x + Math.cos(startAngle) * radius, y: vertex.y + Math.sin(startAngle) * radius },
            end: { x: vertex.x + Math.cos(endAngle) * radius, y: vertex.y + Math.sin(endAngle) * radius },
            radius,
            largeArc: 0,
            sweepFlag: sweep > 0 ? 1 : 0,
            label: {
                x: vertex.x + Math.cos(midAngle) * (radius + 12),
                y: vertex.y + Math.sin(midAngle) * (radius + 12),
            },
        };
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
        projectedForm,
        availableKinds,
        kindApplies,
        projectedSeparation,
        measureValue,
        dimensionLayout,
        angleLayout,
        DEGENERATE_PIXELS,
        ALIGNMENT_EPSILON,
        PARALLEL_EPSILON,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiMeasurements;
    }
    globalScope.KigumiMeasurements = KigumiMeasurements;
})(typeof window !== 'undefined' ? window : globalThis);
