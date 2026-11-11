// The worker's Pyodide, which the filesystem adapter and Python runtime work through. Set once it has loaded.
const runtime = { py: null };
module.exports = runtime;
