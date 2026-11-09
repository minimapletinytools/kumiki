const fs = require('fs');
const os = require('os');
const path = require('path');
const { unusedName, newFilePath, createFile, frameName, newFrameSource } = require('../new-files');

describe('new-files', () => {
    let root;
    beforeEach(() => {
        root = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-new-files-'));
    });
    afterEach(() => {
        fs.rmSync(root, { recursive: true, force: true });
    });

    test('unusedName skips names the folder has', () => {
        expect(unusedName(root, 'untitled', '.py')).toBe('untitled.py');
        fs.writeFileSync(path.join(root, 'untitled.py'), '');
        fs.writeFileSync(path.join(root, 'untitled_2.py'), '');
        expect(unusedName(root, 'untitled', '.py')).toBe('untitled_3.py');
    });

    test('newFilePath places a name in its folder, subfolders included', () => {
        const parts = path.join(root, 'parts');
        expect(newFilePath(root, parts, ' post.py ')).toEqual({ filePath: path.join(parts, 'post.py') });
        expect(newFilePath(root, root, 'a/b.txt')).toEqual({ filePath: path.join(root, 'a', 'b.txt') });
    });

    test('newFilePath refuses an empty name, one outside the project, and one that exists', () => {
        fs.writeFileSync(path.join(root, 'taken.py'), '');
        expect(newFilePath(root, root, '  ')).toEqual({ error: 'message.newFileNameEmpty' });
        expect(newFilePath(root, root, '../escape.py')).toEqual({ error: 'message.newFileOutsideProject' });
        expect(newFilePath(root, root, '/etc/passwd')).toEqual({ error: 'message.newFileOutsideProject' });
        expect(newFilePath(root, root, 'folder/')).toEqual({ error: 'message.newFileOutsideProject' });
        expect(newFilePath(root, root, 'taken.py')).toEqual({ error: 'message.newFileExists' });
    });

    test('createFile makes the folders it needs and never overwrites', () => {
        const filePath = path.join(root, 'a', 'b', 'c.py');
        createFile(filePath, 'x = 1\n');
        expect(fs.readFileSync(filePath, 'utf8')).toBe('x = 1\n');
        expect(() => createFile(filePath, 'y')).toThrow();
        expect(fs.readFileSync(filePath, 'utf8')).toBe('x = 1\n');
    });

    test('frameName makes a Python name and a title from what was typed', () => {
        expect(frameName('my_frame')).toEqual({ name: 'my_frame', title: 'My Frame' });
        expect(frameName('Garden Shed')).toEqual({ name: 'garden_shed', title: 'Garden Shed' });
        expect(frameName('tea-house.py')).toEqual({ name: 'tea_house', title: 'Tea House' });
        expect(frameName('BigBarn')).toEqual({ name: 'big_barn', title: 'Big Barn' });
        expect(frameName('3 bays')).toEqual({ name: 'frame_3_bays', title: 'Frame 3 Bays' });
        expect(frameName(' .py ')).toEqual({ error: 'message.newFrameNameEmpty' });
    });

    test('newFrameSource is a frame function of that name', () => {
        const source = newFrameSource({ name: 'garden_shed', title: 'Garden Shed' });
        expect(source).toContain('@frame\ndef garden_shed(k: Optional[Kiwari] = None) -> Frame:');
        expect(source).toContain('name="Garden Shed"');
    });
});
