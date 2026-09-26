#!/usr/bin/env node
// Downloads the pinned, checksum-verified uv into build-app/uv/<os>-<arch>/
// for electron-builder to bundle (see electron-builder.yml).
//
// Run: node scripts/fetch-uv.js [darwin-arm64 win32-x64 ...]   (default: every arch of this OS)

const fs = require('fs');
const path = require('path');
const { downloadUvRelease, UV_RELEASE_ASSETS } = require('../python-toolchain');

const BUILDER_OS = { darwin: 'mac', win32: 'win', linux: 'linux' };
const OUT_DIR = path.join(__dirname, '..', 'build-app', 'uv');

async function main() {
    const keys = process.argv.slice(2);
    const targets = keys.length > 0 ? keys : Object.keys(UV_RELEASE_ASSETS).filter((key) => key.startsWith(`${process.platform}-`));
    for (const key of targets) {
        if (!UV_RELEASE_ASSETS[key]) {
            throw new Error(`No pinned uv release for ${key}. Known: ${Object.keys(UV_RELEASE_ASSETS).join(', ')}`);
        }
        const [platform, arch] = key.split('-');
        const binary = platform === 'win32' ? 'uv.exe' : 'uv';
        const targetPath = path.join(OUT_DIR, `${BUILDER_OS[platform]}-${arch}`, binary);
        if (fs.existsSync(targetPath)) {
            console.log(`uv for ${key} already at ${targetPath}`);
            continue;
        }
        await downloadUvRelease({ platformKey: key, targetPath, log: console.log });
    }
}

main().catch((error) => {
    console.error(error.message || error);
    process.exit(1);
});
