(function (globalScope) {
    'use strict';
    // The tags across a hierarchy, each with the members wearing it. A tag is
    // identified by kind and name together, so a slice and a generic tag that
    // happen to share a name stay two separate rows.
    //
    // Kinds are listed structure-first rather than alphabetically: which member
    // something is, then which slice it falls in, then whatever the user called
    // it. An unknown kind sorts last.
    const KIND_ORDER = ['member', 'slice', 'generic'];

    function kindRank(kind) {
        const rank = KIND_ORDER.indexOf(kind);
        return rank === -1 ? KIND_ORDER.length : rank;
    }

    function buildTagIndex(hierarchy) {
        const entriesById = new Map();
        const timbers = (hierarchy && hierarchy.timbers) || [];
        for (const timber of timbers) {
            if (!timber || typeof timber.key !== 'string' || !timber.key) {
                continue;
            }
            for (const tag of timber.tags || []) {
                if (!tag || typeof tag.name !== 'string' || !tag.name) {
                    continue;
                }
                const id = tag.kind + ':' + tag.name;
                let entry = entriesById.get(id);
                if (!entry) {
                    entry = { id, kind: tag.kind, name: tag.name, memberKeys: [] };
                    entriesById.set(id, entry);
                }
                if (!entry.memberKeys.includes(timber.key)) {
                    entry.memberKeys.push(timber.key);
                }
            }
        }

        return Array.from(entriesById.values()).sort((a, b) => (
            kindRank(a.kind) - kindRank(b.kind) || a.name.localeCompare(b.name)
        ));
    }

    /** How much of one tag is in the selection: 'all', 'partial' or 'none'. */
    function tagSelectionState(entry, selectedTimbers) {
        const keys = (entry && entry.memberKeys) || [];
        if (keys.length === 0) {
            return 'none';
        }
        const selected = selectedTimbers instanceof Set
            ? selectedTimbers
            : new Set(selectedTimbers || []);
        let hits = 0;
        for (const key of keys) {
            if (selected.has(key)) {
                hits += 1;
            }
        }
        if (hits === 0) {
            return 'none';
        }
        return hits === keys.length ? 'all' : 'partial';
    }

    const TagIndex = { KIND_ORDER, buildTagIndex, tagSelectionState };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = TagIndex;
    }
    globalScope.TagIndex = TagIndex;
})(typeof window !== 'undefined' ? window : globalThis);
