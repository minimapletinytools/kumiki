// The worker's Pyodide, which the fs and child_process stand-ins work through. Set once it has loaded.
const runtime = { py: null };
module.exports = runtime;
