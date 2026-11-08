// worker_threads, for the browser worker: there are no threads to start, so callers do the work here.
module.exports = { Worker: null, isMainThread: true, parentPort: null, workerData: null };
