const fs = require('fs');
const os = require('os');
const path = require('path');
const { extractRunnerErrorDetails, parseTracebackLocation, deriveViewerErrorMessage } = require('../runner-errors');

test('a runner error gives its message, traceback and type; a plain error its message', () => {
  const error = new Error('outer');
  error.runnerError = { message: 'inner', traceback: 'Traceback…', type: 'ValueError' };
  expect(extractRunnerErrorDetails(error)).toEqual({ message: 'inner', traceback: 'Traceback…', type: 'ValueError' });
  expect(extractRunnerErrorDetails(new Error('plain'))).toEqual({ message: 'plain', traceback: null, type: null });
});

test('the innermost traceback line in a file that exists is where it happened', () => {
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-tb-')), 'frame.py');
  fs.writeFileSync(file, '');
  const traceback = `File "${file}", line 3, in build\nFile "/no/such/file.py", line 9, in inner`;
  expect(parseTracebackLocation(traceback)).toEqual({ filePath: file, lineNumber: 3 });
  expect(parseTracebackLocation(null)).toBeNull();
});

test('a traceback goes to the view\'s file first, then to a file not from installed packages', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-tb-'));
  const [frame, helper, library] = ['frame.py', 'helper.py', 'site-packages/lib.py'].map((name) => path.join(dir, name));
  fs.mkdirSync(path.dirname(library));
  for (const file of [frame, helper, library]) fs.writeFileSync(file, '');
  const traceback = `File "${frame}", line 3\nFile "${helper}", line 5\nFile "${library}", line 7`;
  expect(parseTracebackLocation(traceback, { prefer: frame })).toEqual({ filePath: frame, lineNumber: 3 });
  expect(parseTracebackLocation(traceback)).toEqual({ filePath: helper, lineNumber: 5 });
  expect(parseTracebackLocation(`File "${library}", line 7`)).toEqual({ filePath: library, lineNumber: 7 });
});

test('a view says what went wrong plainly', () => {
  expect(deriveViewerErrorMessage({ message: '' })).toBe('Unable to render this file in Kigumi viewer.');
  expect(deriveViewerErrorMessage({ message: 'No patternbook found in x' })).toMatch(/does not define a patternbook/);
  expect(deriveViewerErrorMessage({ message: 'boom' })).toBe('Kigumi failed to render this file: boom');
});
