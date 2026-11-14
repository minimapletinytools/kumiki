// The scale ruler at the bottom right of a view: the longest round length, in the viewer's units,
// that fits in the room it has at the view's scale.

const M_PER_INCH = 0.0254;
const M_PER_SHAKU = 10 / 33;

const metric = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000]
    .map((mm) => ({ metres: mm / 1000, label: mm < 1000 ? `${mm} mm` : `${mm / 1000} m` }));

const imperial = [
    ...[['1/16', 1 / 16], ['1/8', 1 / 8], ['1/4', 1 / 4], ['1/2', 1 / 2], ['1', 1], ['2', 2], ['3', 3], ['6', 6]]
        .map(([label, inches]) => ({ metres: inches * M_PER_INCH, label: `${label}"` })),
    ...[1, 2, 3, 5, 10, 20, 50, 100, 200, 500].map((feet) => ({ metres: feet * 12 * M_PER_INCH, label: `${feet}'` })),
];

// A sun is a tenth of a shaku, a bu a tenth of a sun.
const shaku = [
    ...[1, 2, 5].map((bu) => ({ metres: bu * M_PER_SHAKU / 100, label: `${bu}分` })),
    ...[1, 2, 5].map((sun) => ({ metres: sun * M_PER_SHAKU / 10, label: `${sun}寸` })),
    ...[1, 2, 5, 10, 20, 50, 100, 200].map((count) => ({ metres: count * M_PER_SHAKU, label: `${count}尺` })),
];

const STEPS = { metric, imperial, shaku };

/**
 * The ruler for a view drawn at `metresPerPixel`: { metres, label, px }, the longest round length in
 * `units` ('metric', 'imperial' or 'shaku') no wider than `maxPx`; the shortest there is when even
 * that is wider. Null without a usable scale.
 */
export function rulerLength(metresPerPixel, units, maxPx = 120) {
    if (!Number.isFinite(metresPerPixel) || metresPerPixel <= 0) return null;
    const steps = STEPS[units] || STEPS.metric;
    const fitting = steps.filter((step) => step.metres / metresPerPixel <= maxPx);
    const step = fitting.length ? fitting[fitting.length - 1] : steps[0];
    return { ...step, px: step.metres / metresPerPixel };
}
