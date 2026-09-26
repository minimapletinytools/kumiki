/**
 * The open tabs of the standalone window, in order, and which one is active.
 */

class TabList {
    constructor() {
        this.tabs = [];
        this.activeId = null;
    }

    add(id, fields = {}) {
        this.tabs.push({ id, title: '', ...fields });
        this.activeId = id;
    }

    get(id) {
        return this.tabs.find((tab) => tab.id === id) || null;
    }

    update(id, fields) {
        const tab = this.get(id);
        if (tab) {
            Object.assign(tab, fields);
        }
    }

    activate(id) {
        if (this.get(id)) {
            this.activeId = id;
        }
    }

    // Removes a tab; closing the active one activates its right neighbour, else its left.
    remove(id) {
        const index = this.tabs.findIndex((tab) => tab.id === id);
        if (index === -1) {
            return;
        }
        this.tabs.splice(index, 1);
        if (this.activeId === id) {
            const next = this.tabs[index] || this.tabs[index - 1] || null;
            this.activeId = next ? next.id : null;
        }
    }

    get active() {
        return this.get(this.activeId);
    }

    snapshot() {
        return {
            activeId: this.activeId,
            tabs: this.tabs.map(({ id, title, kind }) => ({ id, title, kind })),
        };
    }
}

module.exports = { TabList };
