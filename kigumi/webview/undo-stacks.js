(function (globalScope) {
    'use strict';
    // Undo and redo, one stack per drawing per loaded frame.
    //
    // Not one stack for the viewer. A drawing is an independent thing to edit:
    // undoing in one after working in another would take back a change you
    // cannot see, which is the worst kind of undo. The 3D view's measurements
    // are a drawing like any other and get a stack of their own.
    //
    // WHAT IS ON IT: making a measurement, deleting one, changing its kind,
    // dragging it. NOT showing and hiding, which is about looking rather than
    // about the drawing, and not selection.
    //
    // WHAT IT HOLDS is a pair of calls, not a snapshot. The model of record is
    // python and the drawings file; the viewer holds no copy to restore. So an
    // entry says how to do a thing and how to undo it, and the caller sends
    // whichever it is handed. A create's undo is a delete, a drag's undo is a
    // drag back.
    //
    // SURVIVES SAVING, since saving is not an edit. PURGED on reload and on
    // changing frames: what a stack holds refers to features and viewports that
    // the reloaded frame may not have, and an undo that cannot be trusted to
    // apply is worse than one that is not offered.

    /** One drawing of one frame. Frames are separate files; ids repeat between them. */
    function stackKey(frameKey, drawingId) {
        return `${frameKey || ''}\u0000${drawingId || ''}`;
    }

    class UndoStacks {
        constructor() {
            this.stacks = new Map();
            /**
             * While a measurement is half-made, undo and redo are refused.
             * There is nothing on the stack for it -- it is not written until
             * it is confirmed -- so the alternative is undo reaching past the
             * thing in front of you to something you are no longer looking at.
             */
            this.suspended = false;
        }

        _stack(frameKey, drawingId) {
            const key = stackKey(frameKey, drawingId);
            if (!this.stacks.has(key)) {
                this.stacks.set(key, { done: [], undone: [] });
            }
            return this.stacks.get(key);
        }

        /**
         * Record something that has happened.
         *
         * `entry` is { label, redo, undo }, where redo and undo are whatever
         * the caller needs to perform each direction. This module never looks
         * inside them.
         *
         * Clears the redo side, as every undo stack does: once you do something
         * new, the future you had undone your way out of is not reachable any
         * more.
         */
        push(frameKey, drawingId, entry) {
            const stack = this._stack(frameKey, drawingId);
            stack.done.push(entry);
            stack.undone.length = 0;
        }

        canUndo(frameKey, drawingId) {
            return !this.suspended && this._stack(frameKey, drawingId).done.length > 0;
        }

        canRedo(frameKey, drawingId) {
            return !this.suspended && this._stack(frameKey, drawingId).undone.length > 0;
        }

        /** The undo side of the last thing done, or null. */
        undo(frameKey, drawingId) {
            if (!this.canUndo(frameKey, drawingId)) {
                return null;
            }
            const stack = this._stack(frameKey, drawingId);
            const entry = stack.done.pop();
            stack.undone.push(entry);
            return entry;
        }

        /** The redo side of the last thing undone, or null. */
        redo(frameKey, drawingId) {
            if (!this.canRedo(frameKey, drawingId)) {
                return null;
            }
            const stack = this._stack(frameKey, drawingId);
            const entry = stack.undone.pop();
            stack.done.push(entry);
            return entry;
        }

        /**
         * Hold undo and redo off while a measurement is being made.
         *
         * Deliberately a flag rather than the caller checking: the draft and
         * the stacks do not know about each other, and every keyboard path
         * would otherwise have to remember.
         */
        suspend(suspended) {
            this.suspended = Boolean(suspended);
        }

        /** Everything for one frame, gone. Reloading it, or leaving it. */
        purgeFrame(frameKey) {
            const prefix = stackKey(frameKey, '');
            for (const key of Array.from(this.stacks.keys())) {
                if (key.startsWith(prefix)) {
                    this.stacks.delete(key);
                }
            }
        }

        purgeAll() {
            this.stacks.clear();
            this.suspended = false;
        }

        /** What the buttons should say they can do. */
        depth(frameKey, drawingId) {
            const stack = this._stack(frameKey, drawingId);
            return { done: stack.done.length, undone: stack.undone.length };
        }
    }

    const KigumiUndoStacks = { UndoStacks, stackKey };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiUndoStacks;
    }
    globalScope.KigumiUndoStacks = KigumiUndoStacks;
})(typeof window !== 'undefined' ? window : globalThis);
