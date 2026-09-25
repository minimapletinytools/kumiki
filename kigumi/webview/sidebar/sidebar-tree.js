(function (globalScope) {
    'use strict';
    // Pure helpers for the sidebar tree: which rows show, filtering, and
    // keyboard movement. No DOM, so jest covers them directly.

    function isContainer(node) {
        return Array.isArray(node.children);
    }

    // `overrides` maps key → expanded for rows the user toggled; other
    // containers use the model's default.
    function isExpanded(node, overrides) {
        return overrides.has(node.key) ? overrides.get(node.key) : node.expanded === true;
    }

    function matches(node, needle) {
        const text = `${node.label || ''} ${node.description || ''}`.toLowerCase();
        return text.includes(needle);
    }

    /**
     * The rows to draw, in order: { node, depth, parentKey, isContainer,
     * isExpanded }. With a filter, a row shows when it or a descendant matches,
     * and containers holding a match are expanded.
     */
    function visibleRows(tree, { overrides = new Map(), filter = '' } = {}) {
        const needle = filter.trim().toLowerCase();
        const rows = [];

        function walk(nodes, depth, parentKey) {
            for (const node of nodes) {
                const container = isContainer(node);
                if (!needle) {
                    const expanded = container && isExpanded(node, overrides);
                    rows.push({ node, depth, parentKey, isContainer: container, isExpanded: expanded });
                    if (expanded) {
                        walk(node.children, depth + 1, node.key);
                    }
                    continue;
                }
                const descendantMatches = container && node.children.some((child) => subtreeMatches(child, needle));
                if (!matches(node, needle) && !descendantMatches) {
                    continue;
                }
                const expanded = container && (descendantMatches || isExpanded(node, overrides));
                rows.push({ node, depth, parentKey, isContainer: container, isExpanded: expanded });
                if (expanded) {
                    walk(descendantMatches ? node.children.filter((child) => subtreeMatches(child, needle)) : node.children, depth + 1, node.key);
                }
            }
        }

        walk(tree, 0, null);
        return rows;
    }

    function subtreeMatches(node, needle) {
        return matches(node, needle)
            || (isContainer(node) && node.children.some((child) => subtreeMatches(child, needle)));
    }

    /** `label` split around the first filter match: [before, match, after]. */
    function highlightParts(label, filter) {
        const text = String(label || '');
        const needle = filter.trim().toLowerCase();
        const at = needle ? text.toLowerCase().indexOf(needle) : -1;
        if (at === -1) {
            return [text, '', ''];
        }
        return [text.slice(0, at), text.slice(at, at + needle.length), text.slice(at + needle.length)];
    }

    /** Overrides that collapse every container in the tree. */
    function collapseAll(tree) {
        const overrides = new Map();
        (function walk(nodes) {
            for (const node of nodes) {
                if (isContainer(node)) {
                    overrides.set(node.key, false);
                    walk(node.children);
                }
            }
        })(tree);
        return overrides;
    }

    /**
     * What a key press does to the focused row: { focus } to move, { toggle }
     * to expand/collapse, { run } to activate, or null.
     */
    function keyAction(rows, focusedKey, key) {
        if (rows.length === 0) {
            return null;
        }
        const index = rows.findIndex((row) => row.node.key === focusedKey);
        const row = index === -1 ? null : rows[index];
        const at = (i) => ({ focus: rows[Math.max(0, Math.min(rows.length - 1, i))].node.key });

        switch (key) {
            case 'ArrowDown':
                return at(index === -1 ? 0 : index + 1);
            case 'ArrowUp':
                return at(index === -1 ? 0 : index - 1);
            case 'Home':
                return at(0);
            case 'End':
                return at(rows.length - 1);
            case 'ArrowRight':
                if (!row || !row.isContainer) return null;
                return row.isExpanded ? at(index + 1) : { toggle: row.node.key };
            case 'ArrowLeft':
                if (!row) return null;
                if (row.isContainer && row.isExpanded) return { toggle: row.node.key };
                return row.parentKey ? { focus: row.parentKey } : null;
            case 'Enter':
            case ' ':
                if (!row) return null;
                return row.node.action ? { run: row.node.key } : (row.isContainer ? { toggle: row.node.key } : null);
            default:
                return null;
        }
    }

    const KigumiSidebarTree = { visibleRows, highlightParts, collapseAll, keyAction, isExpanded };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiSidebarTree;
    }
    globalScope.KigumiSidebarTree = KigumiSidebarTree;
})(typeof window !== 'undefined' ? window : globalThis);
