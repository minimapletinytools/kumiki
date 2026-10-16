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

    const ARROW = ' \u203a ';

    /** A tree row's fully qualified name, from its timber down. See itemLines for `item`. */
    function qualifiedName(item) {
        if (item.kind === 'member') {
            return item.member.name;
        }
        if (item.kind === 'csg') {
            return [item.timberName, ...(item.path || [])].join(ARROW) || item.timberName;
        }
        if (item.kind === 'joint') {
            return `joint ${item.name}`;
        }
        if (item.kind === 'measurement') {
            return [item.drawing ? `drawing ${item.drawing}` : null, item.viewport,
                `measurement ${item.between}`].filter(Boolean).join(ARROW);
        }
        return `tag ${item.tagKind}:${item.name}`;
    }

    /**
     * A row of the layers tree, in full -- though not a node's features, which run to dozens. `item` is one of {kind: 'member', member} (as
     * memberLines takes), {kind: 'csg', timberName, memberKey, path, node} (the tree's node),
     * {kind: 'joint', name, timbers}, {kind: 'tag', tagKind, name, members}, or {kind:
     * 'measurement', drawing, viewport, between, anchors: [{describes, reference}], measureKind,
     * value, origin, refused}.
     */
    function itemLines(item) {
        if (item.kind === 'member') {
            return memberLines(item.member);
        }
        if (item.kind === 'csg') {
            const node = item.node || {};
            const kind = node.displayName || node.kind;
            const lines = [`- ${node.label ? `"${node.label}" ` : ''}(${kind || 'node'}) on timber "${item.timberName}"`
                + ` (member key ${item.memberKey})`, `  path: ${qualifiedName(item)}`];
            if (node.role) lines.push(`  role: ${node.role === 'cut' ? 'cut away' : node.role}`);
            if (node.jointName) lines.push(`  joint: ${node.jointName}`);
            return lines;
        }
        if (item.kind === 'joint') {
            return [`- Joint "${item.name}"`, `  timbers: ${(item.timbers || []).join(', ') || 'none'}`];
        }
        if (item.kind === 'measurement') {
            const lines = [`- Measurement ${qualifiedName(item)}`];
            if (item.measureKind) lines.push(`  kind: ${typeof item.measureKind === 'string' ? item.measureKind : JSON.stringify(item.measureKind)}`);
            lines.push(`  value: ${item.value || (item.refused ? `not drawn (${item.refused})` : 'not drawn')}`);
            if (item.origin) lines.push(`  origin: ${item.origin}`);
            (item.anchors || []).forEach((anchor, index) => {
                lines.push(`  ${index ? 'to' : 'from'}: ${anchor.describes}`);
                if (anchor.reference) lines.push(`    reference: ${JSON.stringify(anchor.reference)}`);
            });
            return lines;
        }
        return [`- Tag ${item.tagKind}:${item.name}`, `  members: ${(item.members || []).join(', ') || 'none'}`];
    }

    /**
     * The text to copy. `selection` is {sourceFile?, frameName?, members: [...], feature?}, or
     * {sourceFile?, frameName?, item, detailed} for a row of the layers tree: its fully qualified
     * name alone, or with `detailed`, everything itemLines says about it.
     *
     * Members are {key, name, type, width, height, length, placement, tags} (metres), a feature
     * as {timberName, memberKey, path, featureLabel, featureType, jointName, geometry, reference}.
     */
    function describeSelection(selection) {
        if (selection.item && !selection.detailed) {
            return [selection.sourceFile, qualifiedName(selection.item)].filter(Boolean).join(ARROW) + '\n';
        }
        const where = [selection.frameName ? `frame "${selection.frameName}"` : null,
            selection.sourceFile ? `in ${selection.sourceFile}` : null].filter(Boolean).join(' ');
        const lines = [`Selected in Kigumi${where ? ` (${where})` : ''}, in metres, world space:`];
        if (selection.item) {
            lines.push(...itemLines(selection.item));
        } else if (selection.feature) {
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
