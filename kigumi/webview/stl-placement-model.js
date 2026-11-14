/** Validate the one editable STL transform; no viewer selection or drawing state lives here. */
export function placement(value = {}) {
    const result = {};
    for (const key of ['translation', 'rotation', 'scale']) {
        const values = value[key] || (key === 'scale' ? [1, 1, 1] : [0, 0, 0]);
        if (!Array.isArray(values) || values.length !== 3 || !values.every(Number.isFinite)
            || (key === 'scale' && values.some(v => v <= 0))) throw new Error(`Invalid ${key}`);
        result[key] = values.slice();
    }
    return result;
}

export function configuration(value) {
    return `placement=${JSON.stringify(placement(value))}`;
}

export function agentPrompt(name, value) {
    return `Update the create_stl_timber call for ${JSON.stringify(name)} with ${configuration(value)}. `
        + 'Translation is in metres, rotation is intrinsic XYZ degrees, and scale is applied before rotation. '
        + 'If the call is shared by several timbers, separate this member before applying the change. Preserve other source edits.';
}
