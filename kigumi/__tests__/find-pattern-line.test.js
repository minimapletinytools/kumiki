const fs = require('fs');
const os = require('os');
const path = require('path');
const { findPatternLine } = require('../pattern-source-utils');

const BOOK = `from kumiki import *

def helper():
    pass

@pattern("corner_joints/plain_miter_joint")
def plain_miter(center):
    return helper()

@pattern('splice/lapped_gooseneck', tags=["main"])
def gooseneck(center):
    pass

def dovetail(center):
    pass

PATTERNS = [Pattern(path=f"{FOLDER}/" + "shiplap", lambda_=lambda c: None)]
`;

describe('the line a pattern is declared on', () => {
    let file;
    beforeAll(() => {
        file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-find-')), 'book.py');
        fs.writeFileSync(file, BOOK);
    });

    test.each([
        ['corner_joints/plain_miter_joint', 6],
        ['splice/lapped_gooseneck', 10],
        ['generated/shiplap', 17],
        ['old/dovetail', 14],
    ])('%s is on line %i', async (patternPath, line) => {
        expect(await findPatternLine(file, patternPath)).toBe(line);
    });

    test('a pattern the file does not mention, or a file that is gone, has none', async () => {
        expect(await findPatternLine(file, 'missing/nowhere')).toBeNull();
        expect(await findPatternLine(path.join(path.dirname(file), 'gone.py'), 'a/b')).toBeNull();
    });
});
