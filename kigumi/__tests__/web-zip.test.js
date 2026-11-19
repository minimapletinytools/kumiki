// The .zip a browser project exports as (hosts/pyodide/page/zip.js), read back by Python's zipfile.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const { makeZip } = require('../hosts/pyodide/page/zip');

test('a standard reader opens it, with every file, its folders and a non-ASCII name intact', () => {
    const files = { 'shed/my_cute_frame.py': 'print("hi")\n', 'shed/.kigumi/drawings/x.json': '{}', 'shed/かわいい.py': '# 架構\n', 'shed/empty.txt': '' };
    const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-zip-')), 'shed.zip');
    fs.writeFileSync(file, makeZip(files, { date: new Date(2026, 10, 19, 8, 30) }));

    const read = JSON.parse(execFileSync('python3', ['-I', '-c', `
import json, sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    assert z.testzip() is None, "a CRC is wrong"
    print(json.dumps({"files": {i.filename: z.read(i).decode() for i in z.infolist()}, "date": z.infolist()[0].date_time}))
`, file], { encoding: 'utf8' }));
    expect(read.files).toEqual(files);
    expect(read.date).toEqual([2026, 11, 19, 8, 30, 0]);
});
