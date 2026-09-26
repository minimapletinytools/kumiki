/**
 * Minimal glob matching for the watch patterns Kigumi uses ("name.py",
 * "**" + "/*.py", "kumiki/**" + "/*.py"). Paths use "/" separators.
 */

function globToRegExp(glob) {
    let source = '';
    for (let i = 0; i < glob.length; i += 1) {
        const char = glob[i];
        if (char === '*' && glob[i + 1] === '*') {
            if (glob[i + 2] === '/') {
                source += '(?:.*/)?';
                i += 2;
            } else {
                source += '.*';
                i += 1;
            }
        } else if (char === '*') {
            source += '[^/]*';
        } else if (char === '?') {
            source += '[^/]';
        } else {
            source += char.replace(/[.+^${}()|[\]\\]/g, '\\$&');
        }
    }
    return new RegExp(`^${source}$`);
}

function createMatcher(glob) {
    const pattern = globToRegExp(glob);
    return (relativePath) => pattern.test(relativePath.split('\\').join('/'));
}

module.exports = { globToRegExp, createMatcher };
