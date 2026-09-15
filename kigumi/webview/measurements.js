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
     * Which kinds each projected pair admits, best first.
     *
     * The same table kumiki.drawing.kinds_for holds, and it is checked against
     * that one by a test -- two copies of a rule is how a rule drifts. Kept
     * here as well because the projection itself needs a camera, so the viewer
     * is the only place that knows which pair it is looking at.
     *
     * Names are composed from the kind's parts: space, then direction, then
     * operation. Everything here is projected, since that is what a sheet has.
     */
    /**
     * The older names, as kumiki.drawing reads them too.
     *
     * `aligned` and `perpendicular` both become one kind: between two points
     * the shortest distance IS the distance, which is why the two collapsed.
     */
    /** The kinds the solid admits, by their composed names. */
    const SOLID_KIND_NAMES = Object.freeze(['angle', 'perpendicular_distance']);

    /** How many segments an arc is drawn with. Enough to read as a curve. */
    const ANGLE_ARC_SAMPLES = 24;

    /** How far past the arc the label sits, as a multiple of the radius. */
    const ANGLE_LABEL_REACH = 1.28;

    const LEGACY_KINDS = Object.freeze({
        aligned: 'projected_perpendicular_distance',
        perpendicular: 'projected_perpendicular_distance',
        horizontal: 'projected_horizontal_distance',
        vertical: 'projected_vertical_distance',
        angle: 'projected_angle',
    });

    /** A kind by its composed name, whatever name it arrived under. */
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

    const PROJECTED_RULES = Object.freeze({
        'point-point': Object.freeze([
            'projected_perpendicular_distance',
            'projected_horizontal_distance',
            'projected_vertical_distance',
        ]),
        'line-point': Object.freeze(['projected_perpendicular_distance']),
        'line-line-parallel': Object.freeze(['projected_perpendicular_distance']),
        'line-line-crossing': Object.freeze(['projected_angle']),
    });

    /**
     * What a feature IS, with nothing projected away.
     *
     * The 3D view's camera belongs to the reader and turns as they look around,
     * so a feature there cannot be classified by how it happens to appear: a
     * face is a plane whatever angle it is seen from. Asking projectedForm
     * there called every face not seen exactly edge-on an 'area' -- nothing to
     * measure -- which is nearly all of them.
     *
     * PYTHON HAS A COPY OF THIS, as solid_form in drawing.py, and a test runs
     * the two against each other.
     */
    function solidForm(geometry) {
        if (!geometry || !geometry.kind) {
            return { form: 'none' };
        }
        if (geometry.kind === 'point') {
            return { form: 'point' };
        }
        if (geometry.kind === 'line') {
            return { form: 'line', direction: normalized(geometry.direction || [0, 0, 0]) };
        }
        if (geometry.kind === 'plane') {
            // The NORMAL, under its own name. It was carried as `direction`
            // once, which is the field meaning "the way this feature runs as
            // drawn" -- so an angle between two faces built its arc out of two
            // normals and pointed at nothing.
            return { form: 'plane', normal: normalized(geometry.normal || [0, 0, 0]) };
        }
        return { form: 'none' };
    }

    /** What a solid form is oriented by: a line's direction, a plane's normal. */
    function orientationOf(form) {
        return (form && (form.normal || form.direction)) || null;
    }

    /**
     * Whether two solid features run together.
     *
     * Two planes are parallel when their NORMALS align and two lines when their
     * DIRECTIONS do -- but a line is parallel to a plane when it runs square to
     * the normal, the opposite test. One carries a normal and the other a
     * direction, so comparing them as though both were directions would call a
     * line lying in a plane a crossing.
     */
    function solidParallel(formA, formB) {
        const one = orientationOf(formA);
        const other = orientationOf(formB);
        if (!one || !other) {
            return null;
        }
        const alignment = Math.abs(dot(one, other));
        return formA.form === formB.form
            ? alignment > 1 - PARALLEL_EPSILON
            : alignment < PARALLEL_EPSILON;
    }

    /**
     * Which kinds this pair admits in the 3D view, best first.
     *
     * No camera comes into it: what a pair admits in the solid does not depend
     * on where anyone is standing. Two flat features that cross admit an angle;
     * anything else admits the distance between them.
     */
    function solidKinds(formA, formB) {
        if (formA.form === 'none' || formB.form === 'none') {
            return [];
        }
        const flat = (form) => form === 'line' || form === 'plane';
        if (flat(formA.form) && flat(formB.form) && solidParallel(formA, formB) === false) {
            return ['angle'];
        }
        return ['perpendicular_distance'];
    }

    /**
     * Which kinds this pair admits in this viewport, best first.
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
        if (forms === 'line-line') {
            // Parallel ones have a separation, crossing ones an angle.
            const alignment = Math.abs(dot(formA.direction, formB.direction));
            return alignment > 1 - PARALLEL_EPSILON
                ? PROJECTED_RULES['line-line-parallel']
                : PROJECTED_RULES['line-line-crossing'];
        }
        return PROJECTED_RULES[forms] || [];
    }

    /** Whether a measurement asking for `kind` can be drawn from these forms. */
    function kindApplies(kind, formA, formB) {
        return availableKinds(formA, formB).indexOf(normalizeKind(kind)) !== -1;
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

        const named = kindName(kind, axes && axes.space);

        if (named === 'angle') {
            // From the RAYS when the measurement has them: they are the two
            // ways the corner opens, so the number and the arc drawn from them
            // are one answer. Normals alone cannot tell 45 degrees from 135 --
            // they give the same absolute dot either way -- which is the whole
            // reason the side has to be settled where the corner is.
            if (axes && axes.rays) {
                const facing = Math.max(-1, Math.min(1,
                    dot(normalized(axes.rays.from), normalized(axes.rays.to))));
                return { unit: 'angle', value: Math.acos(facing) * 180 / Math.PI };
            }
            // No rays: a pair that makes no corner, or an older measurement.
            const one = orientationOf(formA);
            const other = orientationOf(formB);
            const facing = Math.min(1, Math.abs(dot(one, other)));
            const between = Math.acos(facing) * 180 / Math.PI;
            return {
                unit: 'angle',
                value: formA.form === formB.form ? between : 90 - between,
            };
        }
        if (named === 'perpendicular_distance') {
            // In the solid, so the whole separation rather than the part of it
            // that survives a projection.
            const plane = formA.form === 'plane' ? formA
                : (formB.form === 'plane' ? formB : null);
            if (plane) {
                // To a plane, the distance is taken along its normal.
                return {
                    unit: 'length',
                    value: Math.abs(dot(delta, normalized(plane.normal))),
                };
            }
            const solidLine = formA.form === 'line' ? formA
                : (formB.form === 'line' ? formB : null);
            if (solidLine === null) {
                return { unit: 'length', value: length(delta) };
            }
            const along = normalized(solidLine.direction);
            const slide = dot(delta, along);
            return {
                unit: 'length',
                value: length([
                    delta[0] - along[0] * slide,
                    delta[1] - along[1] * slide,
                    delta[2] - along[2] * slide,
                ]),
            };
        }
        if (named === 'projected_angle') {
            const facing = Math.min(1, Math.abs(dot(formA.direction, formB.direction)));
            return { unit: 'angle', value: Math.acos(facing) * 180 / Math.PI };
        }
        if (named === 'projected_horizontal_distance') {
            return { unit: 'length', value: Math.abs(dot(flat, normalized(axes.right))) };
        }
        if (named === 'projected_vertical_distance') {
            return { unit: 'length', value: Math.abs(dot(flat, normalized(axes.up))) };
        }
        if (named === 'projected_perpendicular_distance') {
            // Between two points there is no line to be square to, and the
            // shortest distance is just the distance -- which is what makes
            // this one kind rather than the two it used to be.
            const line = formA.form === 'line' ? formA : (formB.form === 'line' ? formB : null);
            if (line === null) {
                return { unit: 'length', value: length(flat) };
            }
            // Square to whichever of the two is a line: for a point and a line
            // that is the point's distance from it, and for two parallel lines
            // the gap between them.
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
        const from = normalized(rays.from);
        const upright = normalized(rays.normal || cross(rays.from, rays.to));
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

    // Under this, in world units, the two have projected onto each other and
    // there is nothing between them to dimension.
    const DEGENERATE_WORLD = 1e-6;

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
        const look = plane && plane.normal ? plane.normal : axes.look;
        // Which space this is judged in comes from the MEASUREMENT, not from
        // the camera: a drawing shown in perspective still projects onto its
        // sheet, so "not orthographic" does not mean "solid". A kind says its
        // own space; without one, the view says, and only the 3D view has no
        // sheet to project onto.
        const space = measureSpace(measure, options);
        const solid = space === '3d';
        const formA = solid
            ? solidForm(measure.a.geometry)
            : projectedForm(measure.a.geometry, look);
        const formB = solid
            ? solidForm(measure.b.geometry)
            : projectedForm(measure.b.geometry, look);
        const available = solid
            ? solidKinds(formA, formB)
            : availableKinds(formA, formB);
        if (available.length === 0) {
            return { drawable: false, reason: 'not-measurable', formA, formB };
        }
        const wanted = kindName(measure.kind, space);
        if (wanted && available.indexOf(wanted) === -1) {
            return {
                drawable: false, reason: 'kind-unavailable',
                kind: wanted, available, formA, formB,
            };
        }
        const kind = wanted || available[0];
        // The plane's look, not the viewport's, for the same reason the forms
        // were taken with it: the two have to describe one projection.
        const value = measureValue(
            kind, measure.a.at, measure.b.at, formA, formB,
            { ...axes, look, space, rays: measure.angle || null });
        if (value.unit === 'length' && value.value < DEGENERATE_WORLD) {
            return { drawable: false, reason: 'degenerate', kind, formA, formB };
        }
        return { drawable: true, kind, value, available, formA, formB };
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
        if (anchor.kind === 'edge') {
            // Its two parents carry no resolved fields of their own: only the
            // anchor they hang off is merged into.
            return {
                kind: 'edge',
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
            if (anchor.kind === 'edge') {
                // A derived edge has no csgPath or feature of its own -- it is
                // named by the two faces that form it, sorted, the same way
                // DerivedFeaturePath sorts them. Leaving them out gave every
                // derived edge on a timber the same key, so editing one edited
                // whichever happened to be found first.
                const parents = [anchor.a, anchor.b]
                    .map((part) => `${((part || {}).csgPath || []).join('/')}/${(part || {}).feature || ''}`)
                    .sort()
                    .join('&');
                return [anchor.timber, 'edge', parents, anchor.type].join('|');
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
     * away from being fixed, or a drawing whose python has moved. The other
     * three refusals are about THIS view: the same measurement reads fine under
     * one viewport and is refused by the next, which is information rather than
     * damage.
     *
     * Worth telling apart because only the first kind is something to go and
     * mend, and only the first kind should be shouting.
     */
    const BROKEN_REASONS = Object.freeze(['unresolved', 'plane-mismatch']);

    function isBroken(status) {
        return Boolean(status) && !status.drawable
            && BROKEN_REASONS.indexOf(status.reason) !== -1;
    }

    const KigumiMeasurements = {
        PROJECTED_RULES,
        BROKEN_REASONS,
        isBroken,
        measurementKey,
        offsetForPointer,
        anchorReference,
        normalizeKind,
        projectedForm,
        measureSpace,
        kindName,
        kindWire,
        solidForm,
        orientationOf,
        solidKinds,
        solidParallel,
        measurementStatus,
        planeMatchesView,
        PLANE_MATCH_EPSILON,
        availableKinds,
        kindApplies,
        projectedSeparation,
        measureValue,
        dimensionLayout,
        angleLayout,
        angleArcPoints,
        angleLabelPoint,
        DEGENERATE_PIXELS,
        DEGENERATE_WORLD,
        ALIGNMENT_EPSILON,
        PARALLEL_EPSILON,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiMeasurements;
    }
    globalScope.KigumiMeasurements = KigumiMeasurements;
})(typeof window !== 'undefined' ? window : globalThis);
