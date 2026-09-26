/**
 * Kigumi settings for the standalone app: a JSON file of `kigumi.<key>`
 * values over the defaults declared in package.json.
 */

const fs = require('fs');
const path = require('path');

function defaultsFromPackageJson(packageJson) {
    const properties = (((packageJson || {}).contributes || {}).configuration || {}).properties || {};
    const defaults = {};
    for (const [fullKey, spec] of Object.entries(properties)) {
        if (fullKey.startsWith('kigumi.') && spec && 'default' in spec) {
            defaults[fullKey.slice('kigumi.'.length)] = spec.default;
        }
    }
    return defaults;
}

class SettingsStore {
    constructor(filePath, defaults = {}) {
        this.filePath = filePath;
        this.defaults = defaults;
        this.listeners = new Set();
        this.values = this._read();
        this.watcher = null;
    }

    _read() {
        try {
            const parsed = JSON.parse(fs.readFileSync(this.filePath, 'utf8'));
            return parsed && typeof parsed === 'object' ? parsed : {};
        } catch (_error) {
            return {};
        }
    }

    _fire(key) {
        for (const listener of [...this.listeners]) {
            listener(key);
        }
    }

    _write() {
        fs.mkdirSync(path.dirname(this.filePath), { recursive: true });
        fs.writeFileSync(this.filePath, `${JSON.stringify(this.values, null, 2)}\n`, 'utf8');
    }

    // Re-reads the file, telling listeners about every key whose value changed.
    reload() {
        const before = this.values;
        this.values = this._read();
        const keys = new Set([...Object.keys(before), ...Object.keys(this.values)]);
        for (const key of keys) {
            if (JSON.stringify(before[key]) !== JSON.stringify(this.values[key])) {
                this._fire(key);
            }
        }
    }

    // Reloads whenever the file changes on disk. Watches the folder, since
    // editors often save by replacing the file.
    watch() {
        if (this.watcher) return;
        this._write();
        const name = path.basename(this.filePath);
        let timer = null;
        this.watcher = fs.watch(path.dirname(this.filePath), (_event, changed) => {
            if (changed && changed.toString() !== name) return;
            clearTimeout(timer);
            timer = setTimeout(() => this.reload(), 100);
        });
    }

    // Writes every default into the file so it lists what can be set.
    seedDefaults(extra = {}) {
        const all = { ...this.defaults, ...extra };
        let added = false;
        for (const [key, value] of Object.entries(all)) {
            if (!Object.prototype.hasOwnProperty.call(this.values, key)) {
                this.values[key] = value;
                added = true;
            }
        }
        if (added) this._write();
    }

    get(key, fallback) {
        if (Object.prototype.hasOwnProperty.call(this.values, key)) {
            return this.values[key];
        }
        if (Object.prototype.hasOwnProperty.call(this.defaults, key)) {
            return this.defaults[key];
        }
        return fallback;
    }

    set(key, value) {
        this.values[key] = value;
        this._write();
        this._fire(key);
    }

    dispose() {
        if (this.watcher) this.watcher.close();
        this.watcher = null;
        this.listeners.clear();
    }

    onChange(listener) {
        this.listeners.add(listener);
        return { dispose: () => this.listeners.delete(listener) };
    }
}

module.exports = { SettingsStore, defaultsFromPackageJson };
