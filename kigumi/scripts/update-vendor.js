#!/usr/bin/env node
// Downloads vendored webview dependencies into kigumi/webview/vendor/.
// These are bundled into the extension so the viewer works offline.
//
// Run: npm run update-vendor

const fs = require('fs');
const path = require('path');
const https = require('https');

const VENDOR_DIR = path.join(__dirname, '..', 'webview', 'vendor');

const TARGETS = [
    {
        file: 'three.min.js',
        url: 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js',
        note: 'three.js r128 (global THREE)',
        minBytes: 400_000,
    },
    {
        file: 'Reflector.js',
        url: 'https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/objects/Reflector.js',
        note: 'three r128 Reflector (attaches to global THREE)',
        minBytes: 4_000,
    },
    {
        file: 'lit.min.js',
        url: 'https://esm.sh/lit@3.2.0/es2022/lit.bundle.mjs',
        note: 'lit 3.2.0 self-contained ESM bundle',
        minBytes: 10_000,
    },
];

function download(url, redirectsLeft = 5) {
    return new Promise((resolve, reject) => {
        https.get(url, (res) => {
            if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                if (redirectsLeft <= 0) {
                    reject(new Error(`Too many redirects for ${url}`));
                    return;
                }
                const next = new URL(res.headers.location, url).toString();
                res.resume();
                resolve(download(next, redirectsLeft - 1));
                return;
            }
            if (res.statusCode !== 200) {
                reject(new Error(`HTTP ${res.statusCode} for ${url}`));
                return;
            }
            const chunks = [];
            res.on('data', (c) => chunks.push(c));
            res.on('end', () => resolve(Buffer.concat(chunks)));
            res.on('error', reject);
        }).on('error', reject);
    });
}

async function main() {
    fs.mkdirSync(VENDOR_DIR, { recursive: true });
    let failed = 0;
    for (const t of TARGETS) {
        const dest = path.join(VENDOR_DIR, t.file);
        process.stdout.write(`Fetching ${t.file} ... `);
        try {
            const buf = await download(t.url);
            if (buf.length < t.minBytes) {
                throw new Error(`response only ${buf.length} bytes (expected >= ${t.minBytes}); CDN may have returned a stub`);
            }
            fs.writeFileSync(dest, buf);
            console.log(`${buf.length} bytes  [${t.note}]`);
        } catch (err) {
            failed += 1;
            console.log(`FAILED: ${err.message}`);
        }
    }
    if (failed > 0) {
        console.error(`\n${failed} vendor file(s) failed to update.`);
        process.exit(1);
    }
    console.log('\nVendored dependencies updated.');
}

main().catch((err) => {
    console.error(err);
    process.exit(1);
});
