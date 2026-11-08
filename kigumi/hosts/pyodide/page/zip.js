/**
 * A .zip of text files, stored without compression, for exporting a web project from the browser.
 * Runs in the browser (window.KigumiZip) and in Node (require), so tests can read what it writes.
 */
(function (root) {
    'use strict';

    const CRC_TABLE = (() => {
        const table = new Uint32Array(256);
        for (let n = 0; n < 256; n++) {
            let c = n;
            for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
            table[n] = c >>> 0;
        }
        return table;
    })();

    function crc32(bytes) {
        let crc = 0xffffffff;
        for (let i = 0; i < bytes.length; i++) crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
        return (crc ^ 0xffffffff) >>> 0;
    }

    /** Return the zip's bytes for `files`: { path inside the zip: text }. */
    function makeZip(files, { date = new Date() } = {}) {
        const encoder = new TextEncoder();
        const time = (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2);
        const day = ((date.getFullYear() - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate();
        const locals = [];
        const centrals = [];
        let offset = 0;
        for (const [name, text] of Object.entries(files)) {
            const nameBytes = encoder.encode(name);
            const data = encoder.encode(text);
            const crc = crc32(data);
            const local = new DataView(new ArrayBuffer(30));
            local.setUint32(0, 0x04034b50, true);
            local.setUint16(4, 20, true);
            local.setUint16(6, 0x0800, true); // names are UTF-8
            local.setUint16(10, time, true);
            local.setUint16(12, day, true);
            local.setUint32(14, crc, true);
            local.setUint32(18, data.length, true);
            local.setUint32(22, data.length, true);
            local.setUint16(26, nameBytes.length, true);
            locals.push(new Uint8Array(local.buffer), nameBytes, data);

            const central = new DataView(new ArrayBuffer(46));
            central.setUint32(0, 0x02014b50, true);
            central.setUint16(4, 20, true);
            central.setUint16(6, 20, true);
            central.setUint16(8, 0x0800, true);
            central.setUint16(12, time, true);
            central.setUint16(14, day, true);
            central.setUint32(16, crc, true);
            central.setUint32(20, data.length, true);
            central.setUint32(24, data.length, true);
            central.setUint16(28, nameBytes.length, true);
            central.setUint32(42, offset, true);
            centrals.push(new Uint8Array(central.buffer), nameBytes);
            offset += 30 + nameBytes.length + data.length;
        }
        const centralSize = centrals.reduce((sum, part) => sum + part.length, 0);
        const end = new DataView(new ArrayBuffer(22));
        end.setUint32(0, 0x06054b50, true);
        end.setUint16(8, centrals.length / 2, true);
        end.setUint16(10, centrals.length / 2, true);
        end.setUint32(12, centralSize, true);
        end.setUint32(16, offset, true);
        const parts = [...locals, ...centrals, new Uint8Array(end.buffer)];
        const out = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
        let at = 0;
        for (const part of parts) {
            out.set(part, at);
            at += part.length;
        }
        return out;
    }

    const api = { makeZip, crc32 };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.KigumiZip = api;
})(typeof window !== 'undefined' ? window : globalThis);
