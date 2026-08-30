(function (globalScope) {
    'use strict';
    // Timber tags as the runner ships them: {kind, name}. The kind is one of
    // these three; anything else is read as generic rather than dropped, so an
    // unknown kind still shows up as a label the user can see.
    const TAG_KINDS = ['generic', 'slice', 'member'];

    /** One tag from the payload, or null if there is no usable name in it. */
    function coerceTag(tag) {
        if (typeof tag === 'string') {
            const name = tag.trim();
            return name ? { kind: 'generic', name } : null;
        }
        if (!tag || typeof tag.name !== 'string') {
            return null;
        }
        const name = tag.name.trim();
        if (!name) {
            return null;
        }
        return { kind: TAG_KINDS.includes(tag.kind) ? tag.kind : 'generic', name };
    }

    function coerceTags(tags) {
        if (!Array.isArray(tags)) {
            return [];
        }
        return tags.map(coerceTag).filter((tag) => tag !== null);
    }

    const KigumiTags = { TAG_KINDS, coerceTag, coerceTags };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiTags;
    }
    globalScope.KigumiTags = KigumiTags;
})(typeof window !== 'undefined' ? window : globalThis);
