(function (globalScope) {
    'use strict';
    // What a right-click offers, as data rather than as markup.
    //
    // There is more than one of these now -- exporting a member, choosing which
    // feature under the pointer you meant -- and there will be more. Written as
    // one menu that is handed a list, rather than one template per menu, so
    // that dismissing, keyboard handling and where it sits on screen are solved
    // once instead of copied.
    //
    // Deliberately holds no DOM. The caller renders `state`, which is plain
    // data, and calls `choose` with an id. That keeps the awkward half -- what
    // is open, what it says, what happens when it is dismissed -- testable
    // without a browser, which is where the bugs in a menu actually live.

    /** How far from the edge of the canvas a menu will sit, in pixels. */
    const EDGE_MARGIN_PX = 8;

    class ContextMenu {
        constructor() {
            this._open = null;
        }

        get isOpen() {
            return this._open !== null;
        }

        /** What to render, or null when nothing is open. */
        get state() {
            if (!this._open) {
                return null;
            }
            const { x, y, title, items } = this._open;
            return { x, y, title, items };
        }

        /**
         * Offer a menu at a point.
         *
         * `items` are { id, label, disabled?, checked? }. `onChoose` is called
         * with the id of whatever is picked, and the menu closes either way --
         * a menu that stays open after a choice is one nobody dismissed.
         *
         * Opening replaces whatever was open. Two menus at once is not a state
         * worth being able to reach.
         */
        open({ x, y, title, items, onChoose }) {
            const usable = (items || []).filter((item) => item && item.id);
            if (usable.length === 0) {
                // Nothing to offer is not a menu. Saying so here means no
                // caller has to remember to check first.
                this._open = null;
                return false;
            }
            this._open = { x, y, title: title || null, items: usable, onChoose };
            return true;
        }

        close() {
            const was = this._open !== null;
            this._open = null;
            return was;
        }

        /**
         * Pick an item by id. Closes, and answers whether anything happened.
         *
         * A disabled item is offered so that what is NOT available is visible
         * rather than missing, and choosing one does nothing at all -- not even
         * close, since the menu has not been used.
         */
        choose(id) {
            if (!this._open) {
                return false;
            }
            const item = this._open.items.find((one) => one.id === id);
            if (!item || item.disabled) {
                return false;
            }
            const { onChoose } = this._open;
            this._open = null;
            if (typeof onChoose === 'function') {
                onChoose(id, item);
            }
            return true;
        }
    }

    /**
     * Where a menu of this size fits, given a point and the room available.
     *
     * Flipped back from an edge rather than clipped at it: a menu running off
     * the bottom of the canvas loses its last item, and the last item is where
     * the destructive ones tend to sit.
     */
    function menuPosition(at, size, within, margin = EDGE_MARGIN_PX) {
        const fit = (start, extent, limit) => {
            if (start + extent + margin <= limit) {
                return start;
            }
            // Back from the edge, or hard against the near one if it cannot fit
            // either way -- an unreachable menu is worse than a cramped one.
            return Math.max(margin, limit - extent - margin);
        };
        return {
            x: fit(at.x, size.width, within.width),
            y: fit(at.y, size.height, within.height),
        };
    }

    const KigumiContextMenu = { ContextMenu, menuPosition, EDGE_MARGIN_PX };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiContextMenu;
    }
    globalScope.KigumiContextMenu = KigumiContextMenu;
})(typeof window !== 'undefined' ? window : globalThis);
