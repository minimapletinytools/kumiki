(function (globalScope) {
    'use strict';
    // "Copy for AI": what is selected, as text to paste into a conversation with an
    // assistant working on the frame's code. Plain words and SI numbers (metres,
    // world space), plus the feature reference exactly as the drawings file holds
    // it, so it can be found again in code.

    /** Members at most, beyond which a list stops being something to read. */
    const MAX_MEMBERS = 4;

    /** Whether there is something worth copying: a feature, or a few members. */
    function canCopy(memberCount, hasFeature) {
        return Boolean(hasFeature) || (memberCount >= 1 && memberCount <= MAX_MEMBERS);
    }

    function number(value) {
        return Number.isFinite(value) ? String(Math.round(value * 1e6) / 1e6) : '?';
    }

    function vector(values) {
        return Array.isArray(values) ? `[${values.map((v) => number(Number(v))).join(', ')}]` : null;
    }

    function memberLines(member) {
        const lines = [`- ${member.type === 'accessory' ? 'Accessory' : 'Timber'} "${member.name}"`
            + ` (member key ${member.key})`];
        if (member.width !== null && member.height !== null) {
            const length = member.length === null ? '' : `, length ${number(member.length)} m`;
            lines.push(`  size: ${number(member.width)} x ${number(member.height)} m${length}`);
        }
        const placed = member.placement || {};
        for (const [label, value] of [
            ['bottom position', placed.bottom_position],
            ['length direction', placed.length_direction],
            ['width direction', placed.width_direction],
            ['height direction', placed.height_direction],
        ]) {
            const text = vector(value);
            if (text) {
                lines.push(`  ${label}: ${text}`);
            }
        }
        if (member.tags && member.tags.length) {
            lines.push(`  tags: ${member.tags.map((tag) => `${tag.kind}:${tag.name}`).join(', ')}`);
        }
        return lines;
    }

    function featureLines(feature) {
        const kind = feature.featureType ? ` (${String(feature.featureType).toLowerCase()})` : '';
        const lines = [`- Feature "${feature.featureLabel || feature.nodeLabel || '?'}"${kind}`
            + ` on timber "${feature.timberName}" (member key ${feature.memberKey})`];
        if (feature.path) {
            lines.push(`  path: ${feature.path}`);
        }
        if (feature.jointName) {
            lines.push(`  joint: ${feature.jointName}`);
        }
        const geometry = feature.geometry || null;
        if (geometry && geometry.kind) {
            const parts = [`at ${vector(geometry.at)}`];
            if (geometry.normal) parts.push(`normal ${vector(geometry.normal)}`);
            if (geometry.direction) parts.push(`direction ${vector(geometry.direction)}`);
            lines.push(`  ${geometry.kind}: ${parts.join(', ')}`);
        }
        if (feature.reference) {
            lines.push(`  reference: ${JSON.stringify(feature.reference)}`);
        }
        return lines;
    }

    /**
     * The text to copy. `selection` is {sourceFile?, frameName?, members: [...], feature?}:
     * members as {key, name, type, width, height, length, placement, tags} (metres), a feature
     * as {timberName, memberKey, path, featureLabel, featureType, jointName, geometry, reference}.
     */
    function describeSelection(selection) {
        const where = [selection.frameName ? `frame "${selection.frameName}"` : null,
            selection.sourceFile ? `in ${selection.sourceFile}` : null].filter(Boolean).join(' ');
        const lines = [`Selected in Kigumi${where ? ` (${where})` : ''}, in metres, world space:`];
        if (selection.feature) {
            lines.push(...featureLines(selection.feature));
        } else {
            for (const member of selection.members || []) {
                lines.push(...memberLines(member));
            }
        }
        return lines.join('\n') + '\n';
    }

    const KigumiSelectionCopy = { MAX_MEMBERS, canCopy, describeSelection };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiSelectionCopy;
    }
    globalScope.KigumiSelectionCopy = KigumiSelectionCopy;
})(typeof window !== 'undefined' ? window : globalThis);
