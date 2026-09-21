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


    /** The kinds the solid admits, by their composed names. */
    const SOLID_KIND_NAMES = Object.freeze(['angle', 'perpendicular_distance']);

    /** How many segments an arc is drawn with. Enough to read as a curve. */
    const ANGLE_ARC_SAMPLES = 24;

    /** How far past the arc the label sits, as a multiple of the radius. */
    const ANGLE_LABEL_REACH = 1.28;

    /**
     * The older names, as kumiki.drawing reads them too.
     *
     * `aligned` and `perpendicular` both become one kind: between two points
     * the shortest distance IS the distance, which is why the two collapsed.
     */
    const LEGACY_KINDS = Object.freeze({
        aligned: 'projected_perpendicular_distance',
        perpendicular: 'projected_perpendicular_distance',
        horizontal: 'projected_horizontal_distance',
        vertical: 'projected_vertical_distance',
        angle: 'projected_angle',
    });

    /** A kind by its composed name, whatever name it arrived under. */
    /** Whether a vector points anywhere. Guards every rule that normalises one. */
    function hasDirection(vector) {
        return Array.isArray(vector)
            && vector.length === 3
            && vector.some((part) => Number.isFinite(part) && Math.abs(part) > 1e-12);
    }

    function normalizeKind(kind) {
        return LEGACY_KINDS[kind] || kind;
    }

    /**
     * A kind's composed name, however it arrived.
     *
     * A file and the runner write kinds STRUCTURED -- {operation, space,
     * direction} -- because one name is ambiguous: `angle` composes for a solid
     * angle and is also what every measurement written before spaces existed
     * calls a projected one. Everything below compares names, and comparing a
     * structured kind against them matched nothing, so every measurement a
     * python file declared with a kind read as `kind-unavailable`.
     */
    function kindName(kind, space) {
        if (!kind) {
            return null;
        }
        if (typeof kind === 'string') {
            // `angle` composes for a SOLID angle and is also what everything
            // written before spaces called a projected one, so a bare name
            // cannot say which it is. Where the caller knows the space, it
            // settles it; otherwise the older reading wins, as it does in
            // python. Without this the solid name was upgraded to the projected
            // one and every rule below about solid angles was unreachable.
            if (space === '3d' && SOLID_KIND_NAMES.indexOf(kind) !== -1) {
                return kind;
            }
            return normalizeKind(kind);
        }
        const operation = kind.operation || 'distance';
        const parts = [];
        if ((kind.space || 'projected') === 'projected') {
            parts.push('projected');
        }
        if (operation === 'distance') {
            parts.push(kind.direction || 'perpendicular');
        }
        parts.push(operation);
        return parts.join('_');
    }

    /**
     * A kind in the form python reads back, which says the space outright.
     *
     * `space` settles the one name that cannot say it for itself: a bare
     * `angle` composes for a solid angle, and python reads it as the projected
     * one because every file holding that word was written meaning that. So a
     * solid angle has to be written structured or it comes back as a different
     * measurement. Every other name carries its own space.
     */
    function kindWire(kind, space) {
        if (!kind) {
            return null;
        }
        if (typeof kind !== 'string') {
            return {
                operation: kind.operation || 'distance',
                space: kind.space || 'projected',
                direction: kind.direction || 'perpendicular',
            };
        }
        const name = kindName(kind, space);
        const parts = name.split('_');
        const projected = parts[0] === 'projected';
        if (projected) {
            parts.shift();
        }
        const operation = parts[parts.length - 1];
        return {
            operation,
            space: projected ? 'projected' : (space || '3d'),
            direction: operation === 'distance' && parts.length > 1
                ? parts[0] : 'perpendicular',
        };
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
     * The arc of an angle dimension, around where the two lines cross.
     *
     * Drawn at the crossing rather than between the two features, because an
     * angle is a property of the corner they make and reads as nothing anywhere
     * else. null when they are too near parallel to have a crossing on the
     * sheet -- which the rules should already have refused, but a dimension
     * drawn from a crossing at infinity would be worse than none.
     */
    /**
     * Points along an angle's arc, in world space, swept in the angle's OWN plane.
     *
     * A drafted angle lies on the work. Drawn instead as a flat arc between two
     * projected directions it shows the PROJECTED angle, which agrees with the
     * number beside it only when the camera happens to look down the plane --
     * from anywhere else a right angle reads as twenty degrees and the arc
     * floats free of the timber.
     *
     * `radius` is in world units, so the arc foreshortens with everything else.
     */
    function angleArcPoints(rays, radius, samples) {
        if (!hasDirection(rays && rays.from) || !hasDirection(rays && rays.to)) {
            // Not a corner. A measurement carrying rays of no length describes
            // nothing, and sweeping them would draw a heap of identical points
            // that reads as a dot on the timber.
            return [];
        }
        const from = normalized(rays.from);
        const upright = normalized(rays.normal || cross(rays.from, rays.to));
        if (!hasDirection(upright)) {
            // Parallel rays span no plane, so there is no way round from one to
            // the other.
            return [];
        }
        // In the plane, square to `from`, turning toward `to`.
        const across = cross(upright, from);
        const facing = Math.max(-1, Math.min(1, dot(from, normalized(rays.to))));
        const sweep = Math.acos(facing);
        const count = Math.max(2, samples || ANGLE_ARC_SAMPLES);
        const points = [];
        for (let step = 0; step <= count; step += 1) {
            const turn = sweep * (step / count);
            const along = Math.cos(turn);
            const over = Math.sin(turn);
            points.push([
                rays.vertex[0] + (from[0] * along + across[0] * over) * radius,
                rays.vertex[1] + (from[1] * along + across[1] * over) * radius,
                rays.vertex[2] + (from[2] * along + across[2] * over) * radius,
            ]);
        }
        return points;
    }

    /** Where an angle's label sits: past the middle of its arc, in the plane. */
    function angleLabelPoint(rays, radius) {
        const middle = angleArcPoints(rays, radius, 2)[1];
        const out = subtract(middle, rays.vertex);
        const size = length(out);
        if (size < 1e-9) {
            return middle;
        }
        return [
            rays.vertex[0] + (out[0] / size) * radius * ANGLE_LABEL_REACH,
            rays.vertex[1] + (out[1] / size) * radius * ANGLE_LABEL_REACH,
            rays.vertex[2] + (out[2] / size) * radius * ANGLE_LABEL_REACH,
        ];
    }

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


    /**
     * Whether a measurement can be drawn in this viewport, and what it comes to.
     *
     * One answer for both the sheet and the list, so that a dimension which is
     * not drawn and a row which says why cannot disagree. Five ways to fail, and
     * they are worth telling apart: a reference that no longer resolves, and a
     * plane that disagrees with the view it is drawn in, are broken wherever you
     * look at them, while the other three are about this view alone -- the same
     * measurement can read fine under one viewport and be refused by the next.
     *
     * The measurement's own plane decides the projection when it has one; the
     * viewport's look is the fallback, which is what every measurement written
     * before planes existed relies on. That is what keeps a number steady while
     * a camera orbits -- the plane does not move when the camera does.
     *
     * `options.orthographic` says whether the viewport projects onto a plane at
     * all. A perspective camera does not, so the match below means nothing there
     * and is not asked -- see the 3D view and a drawing's preview.
     */
    /**
     * How closely a measurement's plane has to match an orthographic viewport's.
     *
     * Both are computed -- one derived when the measurement was made, one from
     * the viewport's declared camera -- so they agree to within arithmetic
     * rather than exactly.
     */
    const PLANE_MATCH_EPSILON = 1e-6;

    /**
     * Whether a measurement's plane is the one this viewport projects onto.
     *
     * Up to sign, since a plane has no front, and only in direction: where the
     * plane sits along the view cannot change an orthographic projection.
     */
    function planeMatchesView(plane, look) {
        if (!plane || !plane.normal) {
            return true;
        }
        return Math.abs(Math.abs(dot(normalized(plane.normal), normalized(look))) - 1)
            <= PLANE_MATCH_EPSILON;
    }

    /**
     * Which space a measurement is taken in.
     *
     * Its own kind knows, when it has one written structured. A kind that
     * arrived as a bare name cannot say -- `angle` reads as the projected one
     * -- so the view answers instead, and only the 3D view has no sheet.
     */
    function measureSpace(measure, options) {
        const kind = measure && measure.kind;
        if (kind && typeof kind !== 'string' && kind.space) {
            return kind.space;
        }
        return (options && options.space) || 'projected';
    }

    /**
     * The runner's answer, in the shape this file has always returned.
     *
     * A translation and nothing else: no rule is applied here. `reason` arrives
     * in the same words and the same order measurementStatus uses below, so a
     * dimension that is not drawn and a row that says why cannot disagree --
     * which two derivations of the same verdict eventually do.
     */
    function settledStatus(settled) {
        const shared = {
            kind: settled.kind ? kindName(settled.kind, settled.space) : null,
            available: settled.available || [],
            space: settled.space,
            formA: settled.a || null,
            formB: settled.b || null,
        };
        if (settled.reason) {
            return Object.assign({ drawable: false, reason: settled.reason }, shared);
        }
        return Object.assign({ drawable: true, value: settled.value }, shared);
    }

    function measurementStatus(measure, axes, options) {
        if (!measure || measure.unresolved || !measure.a || !measure.b
            || !measure.a.at || !measure.b.at) {
            return { drawable: false, reason: 'unresolved' };
        }
        const orthographic = !options || options.orthographic !== false;
        const plane = measure.plane || null;
        if (orthographic && !planeMatchesView(plane, axes.look)) {
            // Not re-planed to match: that would quietly change the number
            // someone has already read off the sheet.
            return { drawable: false, reason: 'plane-mismatch', plane };
        }
        // Settled by the runner, which resolved the anchors and knows the rest.
        // The value does not depend on the camera -- a measurement carries the
        // plane it was taken on and is read against that -- so the only part
        // left here is the question just asked above, which IS about the
        // camera: does the view being drawn into show that plane.
        if (measure.settled) {
            return settledStatus(measure.settled);
        }
        // Nothing sent, so nothing drawn. This file used to work the answer out
        // for itself here, and the reason that had to stop is that it could
        // only judge the pair against whatever camera happened to be showing:
        // for a measurement carrying no plane the same two points then read as
        // their separation from one angle and their diagonal from another,
        // which is the drift MeasurementPlane exists to prevent.
        //
        // The runner sends an answer for every measurement it can place and a
        // refusal, with a reason, for every one it cannot -- and warns on the
        // latter, since none of them should happen. So arriving here means a
        // measurement from some path that predates that, and the honest thing
        // is to say so rather than to invent a number.
        return { drawable: false, reason: 'not-settled' };
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

    /**
     * Just the reference part of an anchor, as the file holds it.
     *
     * A measurement read back carries where its anchors resolved to as well --
     * a world point and the plane or line it lies on -- and writing that back
     * would put in the drawings file what the next resolve recomputes anyway,
     * and what goes stale the moment the timber moves.
     */
    function anchorReference(anchor) {
        if (!anchor) {
            return null;
        }
        if (anchor.kind === 'edge' || anchor.kind === 'point') {
            // Its two parents carry no resolved fields of their own: only the
            // anchor they hang off is merged into.
            return {
                kind: anchor.kind,
                timber: anchor.timber,
                a: anchor.a,
                b: anchor.b,
                type: anchor.type,
            };
        }
        return {
            timber: anchor.timber,
            csgPath: anchor.csgPath || [],
            feature: anchor.feature,
            type: anchor.type,
        };
    }

    /**
     * A measurement's identity, as a string, scoped to its viewport.
     *
     * The two features plus the id that lets one pair be measured twice --
     * sorted, because measuring A to B and measuring B to A are one
     * measurement, and the anchors are already canonically ordered.
     */
    function measurementKey(measure) {
        const name = (anchor) => {
            if (!anchor) {
                return '';
            }
            if (anchor.kind === 'edge' || anchor.kind === 'point') {
                // A derived feature has no csgPath or feature of its own -- it
                // is named by the two parents that form it, sorted, the same
                // way DerivedFeaturePath sorts them. Leaving them out gave
                // every derived edge on a timber the same key, so editing one
                // edited whichever happened to be found first.
                const parents = [anchor.a, anchor.b]
                    .map((part) => `${((part || {}).csgPath || []).join('/')}/${(part || {}).feature || ''}`)
                    .sort()
                    .join('&');
                return [anchor.timber, anchor.kind, parents, anchor.type].join('|');
            }
            return [anchor.timber, (anchor.csgPath || []).join('/'), anchor.feature, anchor.type]
                .join('|');
        };
        return [name(measure.a), name(measure.b)].sort().join('::')
            + '::' + (measure.measureId || '');
    }

    /**
     * How far from the run a dimension sits, given where the pointer is.
     *
     * The one degree of freedom a dimension has once its two ends are fixed:
     * it slides along the perpendicular and nowhere else. Signed, because
     * which SIDE it sits on is the other half of that freedom -- dragging
     * through the run puts it on the far side rather than stopping at zero.
     *
     * The same perpendicular dimensionLayout offsets along, so what is dragged
     * is what is drawn.
     */
    function offsetForPointer(from, to, pointer) {
        const run = { x: to.x - from.x, y: to.y - from.y };
        const span = Math.hypot(run.x, run.y);
        if (span < DEGENERATE_PIXELS) {
            return null;
        }
        const away = { x: -run.y / span, y: run.x / span };
        return (pointer.x - from.x) * away.x + (pointer.y - from.y) * away.y;
    }

    /**
     * Why a measurement cannot be drawn, when the reason is not about the view.
     *
     * An anchor that no longer resolves, and a plane that disagrees with the
     * viewport it is drawn in, are wrong wherever you look at them -- a rename
     * away from being fixed, or a drawing whose python has moved. So are the
     * three the runner sends when it cannot work a measurement out at all: no
     * plane to judge it along, an end with no extent because a timber's CSG
     * would not render, and no answer attached at all. It warns about each, and
     * they are damage by the same test -- turning the camera will not help.
     *
     * The rest are about THIS view: the same measurement reads fine under one
     * viewport and is refused by the next, which is information rather than
     * damage.
     *
     * Worth telling apart because only the first kind is something to go and
     * mend, and only the first kind should be shouting.
     */
    const BROKEN_REASONS = Object.freeze([
        'unresolved', 'plane-mismatch', 'no-plane', 'no-span', 'not-settled']);

    function isBroken(status) {
        return Boolean(status) && !status.drawable
            && BROKEN_REASONS.indexOf(status.reason) !== -1;
    }

    const KigumiMeasurements = {
        BROKEN_REASONS,
        isBroken,
        measurementKey,
        offsetForPointer,
        anchorReference,
        normalizeKind,
        measureSpace,
        kindName,
        kindWire,
        hasDirection,
        measurementStatus,
        settledStatus,
        planeMatchesView,
        PLANE_MATCH_EPSILON,
        dimensionLayout,
        angleLayout,
        angleArcPoints,
        angleLabelPoint,
        DEGENERATE_PIXELS,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiMeasurements;
    }
    globalScope.KigumiMeasurements = KigumiMeasurements;
})(typeof window !== 'undefined' ? window : globalThis);
