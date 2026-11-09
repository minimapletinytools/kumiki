/**
 * New File and New Frame, from the explorer: where the file goes, what it's called, and a new
 * frame's starting source. Kept apart from the commands (kigumi-app.js) so it can be tested alone.
 */

const fs = require('fs');
const path = require('path');

/** The first of `stem.ext`, `stem_2.ext`, … that `dir` doesn't have. */
function unusedName(dir, stem, ext) {
    for (let n = 1; ; n += 1) {
        const name = n === 1 ? `${stem}${ext}` : `${stem}_${n}${ext}`;
        if (!fs.existsSync(path.join(dir, name))) {
            return name;
        }
    }
}

/**
 * Where a new file named `text` in `dir` goes: `{ filePath }`, or `{ error }` (an i18n key).
 * `text` may name subfolders ("parts/post.py"), but not leave the project at `root`.
 */
function newFilePath(root, dir, text) {
    const name = String(text || '').trim();
    if (!name) {
        return { error: 'message.newFileNameEmpty' };
    }
    const filePath = path.resolve(dir, name);
    const relative = path.relative(root, filePath);
    if (!relative || relative.startsWith('..') || path.isAbsolute(relative) || /[\\/]$/.test(name)) {
        return { error: 'message.newFileOutsideProject' };
    }
    if (fs.existsSync(filePath)) {
        return { error: 'message.newFileExists' };
    }
    return { filePath };
}

/** Makes an empty file, and any folders it needs; returns its path. */
function createFile(filePath, content = '') {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content, { flag: 'wx' });
    return filePath;
}

/**
 * A frame name as typed ("My Frame", "my-frame.py") made into a Python name: `{ name, title }`,
 * or `{ error }`. `name` is the function and the file's stem; `title` is the frame's name.
 */
function frameName(text) {
    const words = String(text || '').trim().replace(/\.py$/i, '')
        .split(/[^A-Za-z0-9]+/).filter(Boolean);
    if (words.length === 0) {
        return { error: 'message.newFrameNameEmpty' };
    }
    let name = words.join('_').replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase();
    if (/^[0-9]/.test(name)) {
        name = `frame_${name}`;
    }
    const title = name.split('_').map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
    return { name, title };
}

/** A new frame's source: one post, to build on. */
function newFrameSource({ name, title }) {
    return `"""${title}."""

from kumiki import *


@frame
def ${name}(k: Optional[Kiwari] = None) -> Frame:
    post = create_axis_aligned_timber(
        bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
        length=mm(1000),
        size=Matrix([mm(90), mm(90)]),
        length_direction=TimberFace.TOP,
        width_direction=TimberFace.RIGHT,
        ticket=TimberTicket(path="Post"),
    )
    return Frame(cut_timbers=[CutTimber(post)], name=${JSON.stringify(title)})
`;
}

module.exports = { unusedName, newFilePath, createFile, frameName, newFrameSource };
