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
        this.values = {};
        try {
            this.values = JSON.parse(fs.readFileSync(filePath, 'utf8')) || {};
        } catch (_error) {
            this.values = {};
        }
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
        fs.mkdirSync(path.dirname(this.filePath), { recursive: true });
        fs.writeFileSync(this.filePath, `${JSON.stringify(this.values, null, 2)}\n`, 'utf8');
        for (const listener of [...this.listeners]) {
            listener(key);
        }
    }

    onChange(listener) {
        this.listeners.add(listener);
        return { dispose: () => this.listeners.delete(listener) };
    }
}

module.exports = { SettingsStore, defaultsFromPackageJson };
