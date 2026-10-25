/**
 * Undo for the agent's turns: each file a turn changes, as it was before and as the turn left it.
 * Undoing a turn (and every later one) puts files back as they were before it, unless one has been
 * changed since the agent left it; those are listed instead, and put back only when asked again.
 *
 * Kept with the conversation (toJSON), so undo still works after it is reopened.
 */
class Checkpoints {
    /** @param {object} files  the project's files (agent/project-files.js) */
    constructor(files, saved = []) {
        this.files = files;
        // [{ turn, files: { absolutePath: { before: text|null, after: text|null } } }]
        this.kept = saved;
        this.open = null;
    }

    /** A turn starts: what it changes is kept from now. */
    begin(turn) {
        this.open = { turn, files: {} };
    }

    /** Before the turn writes `absolute`: keep it as it was, the first time. */
    async beforeWrite(absolute) {
        if (!this.open || absolute in this.open.files) return;
        this.open.files[absolute] = { before: await this.files.read(absolute), after: null };
    }

    /** The turn is over: what it changed, as relative paths, or null if nothing. */
    async end() {
        const turn = this.open;
        this.open = null;
        if (!turn || !Object.keys(turn.files).length) return null;
        for (const [absolute, versions] of Object.entries(turn.files)) {
            versions.after = await this.files.read(absolute);
        }
        this.kept.push(turn);
        return { turn: turn.turn, files: Object.keys(turn.files).map((file) => this.files.relative(file)) };
    }

    /**
     * Put back the files `turn` and later turns changed. Files changed since the agent left them
     * are left alone, and listed, unless `force`. Returns { restored, conflicts } (relative paths).
     */
    async restore(turn, { force = false } = {}) {
        const undone = this.kept.filter((checkpoint) => checkpoint.turn >= turn);
        // The state each file was in before the earliest undone turn, and the last state the agent left.
        const first = new Map();
        const last = new Map();
        for (const checkpoint of undone) {
            for (const [file, versions] of Object.entries(checkpoint.files)) {
                if (!first.has(file)) first.set(file, versions.before);
                last.set(file, versions.after);
            }
        }
        const conflicts = [];
        for (const [file, after] of last) {
            if ((await this.files.read(file)) !== after) conflicts.push(file);
        }
        if (conflicts.length && !force) {
            return { restored: [], conflicts: conflicts.map((file) => this.files.relative(file)) };
        }
        for (const [file, before] of first) {
            if (before === null) await this.files.remove(file);
            else await this.files.write(file, before);
        }
        this.kept = this.kept.filter((checkpoint) => checkpoint.turn < turn);
        return { restored: [...first.keys()].map((file) => this.files.relative(file)), conflicts: [] };
    }

    toJSON() {
        return this.kept;
    }
}

module.exports = { Checkpoints };
