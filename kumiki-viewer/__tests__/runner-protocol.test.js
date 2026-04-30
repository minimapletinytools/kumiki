const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

function resolvePython(projectRoot) {
  if (process.env.HORSEY_VIEWER_PYTHON) {
    return process.env.HORSEY_VIEWER_PYTHON;
  }

  const candidates = [
    '.venv/bin/python3',
    '.venv/bin/python',
    'venv/bin/python3',
    'venv/bin/python',
  ];

  for (const rel of candidates) {
    const candidate = path.join(projectRoot, rel);
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  return 'python3';
}

function createRunnerClient(fixtureName = 'minimal_frame.py') {
  const extensionRoot = path.resolve(__dirname, '..');
  const projectRoot = path.resolve(extensionRoot, '..');
  const runnerPath = path.join(extensionRoot, 'runner.py');
  const examplePath = path.join(extensionRoot, 'test-fixtures', fixtureName);
  const pythonCmd = resolvePython(projectRoot);

  const child = spawn(pythonCmd, [runnerPath, examplePath], {
    cwd: projectRoot,
    stdio: ['pipe', 'pipe', 'pipe'],
  });

  let buffer = '';
  const waiters = [];
  const stderr = [];

  child.stdout.on('data', (chunk) => {
    buffer += chunk.toString();
    let newlineIndex = buffer.indexOf('\n');

    while (newlineIndex >= 0) {
      const line = buffer.slice(0, newlineIndex).trim();
      buffer = buffer.slice(newlineIndex + 1);

      if (line) {
        let parsed;
        try {
          parsed = JSON.parse(line);
        } catch (error) {
          continue;
        }
        const waiter = waiters.shift();
        if (waiter) {
          waiter.resolve(parsed);
        }
      }

      newlineIndex = buffer.indexOf('\n');
    }
  });

  child.stderr.on('data', (chunk) => {
    stderr.push(chunk.toString());
  });

  function readMessage(timeoutMs = 15000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error(`Timed out waiting for runner message. stderr:\n${stderr.join('')}`));
      }, timeoutMs);

      waiters.push({
        resolve: (message) => {
          clearTimeout(timer);
          resolve(message);
        },
      });
    });
  }

  let requestId = 0;
  async function request(command, payload = {}, timeoutMs = 15000) {
    requestId += 1;
    const id = requestId;
    child.stdin.write(`${JSON.stringify({ id, command, payload })}\n`);
    const message = await readMessage(timeoutMs);
    return message;
  }

  async function shutdown() {
    if (!child.killed && child.exitCode === null) {
      try {
        await request('shutdown');
      } catch (error) {
        // Ignore shutdown race conditions.
      }
    }
    if (!child.killed && child.exitCode === null) {
      child.kill();
    }
  }

  return { child, readMessage, request, shutdown, stderr };
}

async function waitForReadyAndCollectMilestones(client, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  const milestones = [];

  while (Date.now() < deadline) {
    const remaining = Math.max(1, deadline - Date.now());
    const message = await client.readMessage(remaining);
    if (message && message.type === 'milestone') {
      milestones.push(message);
      continue;
    }
    if (message && message.type === 'ready') {
      return { ready: message, milestones };
    }
  }

  throw new Error('Timed out waiting for ready event');
}

describe('runner protocol', () => {
  jest.setTimeout(60000);

  test('ready + command flow returns frame and geometry payloads', async () => {
    const client = createRunnerClient();

    try {
      const ready = await client.readMessage();
      expect(ready.type).toBe('ready');
      expect(Array.isArray(ready.commands)).toBe(true);
      expect(ready.commands).toContain('get_frame');
      expect(ready.commands).toContain('get_geometry');

      const ping = await client.request('ping');
      expect(ping.ok).toBe(true);
      expect(ping.result).toEqual({ pong: true });

      const frame = await client.request('get_frame');
      expect(frame.ok).toBe(true);
      expect(frame.result.timber_count).toBeGreaterThan(0);

      const geometry1 = await client.request('get_geometry');
      expect(geometry1.ok).toBe(true);
      expect(geometry1.result.kind).toBe('triangle-geometry');
      expect(Array.isArray(geometry1.result.meshes)).toBe(true);
      expect(geometry1.result.meshes.length).toBeGreaterThan(0);
      const firstMesh = geometry1.result.meshes[0];
      expect(typeof firstMesh.memberKey).toBe('string');
      expect(typeof firstMesh.memberType).toBe('string');
      expect(firstMesh.memberType).toBe('timber');
      expect(geometry1.result.changedKeys.length).toBe(geometry1.result.meshes.length);
      expect(Array.isArray(geometry1.result.remeshMetrics)).toBe(true);
      expect(geometry1.result.remeshMetrics.length).toBe(geometry1.result.changedKeys.length);
      expect(geometry1.result.counts.totalTimbers).toBe(geometry1.result.meshes.length);
      expect(geometry1.result.counts.changedTimbers).toBe(geometry1.result.changedKeys.length);
      expect(geometry1.result.counts.removedTimbers).toBe(geometry1.result.removedKeys.length);
      if (geometry1.result.remeshMetrics.length > 0) {
        const metric = geometry1.result.remeshMetrics[0];
        expect(typeof metric.timberKey).toBe('string');
        expect(typeof metric.remesh_s).toBe('number');
        expect(metric.remesh_s).toBeGreaterThanOrEqual(0);
        expect(typeof metric.csg_depth).toBe('number');
        expect(metric.csg_depth).toBeGreaterThanOrEqual(1);
        expect(typeof metric.triangle_count).toBe('number');
        expect(metric.triangle_count).toBeGreaterThanOrEqual(0);
      }

      const geometry2 = await client.request('get_geometry');
      expect(geometry2.ok).toBe(true);
      expect(geometry2.result.kind).toBe('triangle-geometry');
      expect(Array.isArray(geometry2.result.changedKeys)).toBe(true);
      expect(geometry2.result.changedKeys).toHaveLength(geometry2.result.meshes.length);
      expect(Array.isArray(geometry2.result.remeshMetrics)).toBe(true);
      expect(geometry2.result.remeshMetrics).toHaveLength(geometry2.result.meshes.length);
      expect(geometry2.result.counts.totalTimbers).toBe(geometry2.result.meshes.length);

    } finally {
      await client.shutdown();
    }
  });

  test('geometry payload includes accessories as selectable members', async () => {
    const client = createRunnerClient('accessory_frame.py');

    try {
      const ready = await client.readMessage();
      expect(ready.type).toBe('ready');

      const frame = await client.request('get_frame');
      expect(frame.ok).toBe(true);
      expect(frame.result.accessories_count).toBeGreaterThan(0);

      const geometry = await client.request('get_geometry');
      expect(geometry.ok).toBe(true);
      expect(Array.isArray(geometry.result.meshes)).toBe(true);
      expect(geometry.result.meshes.length).toBeGreaterThanOrEqual(frame.result.timber_count + frame.result.accessories_count);

      const accessoryMeshes = geometry.result.meshes.filter((mesh) => mesh.memberType === 'accessory');
      expect(accessoryMeshes.length).toBeGreaterThan(0);
      for (const mesh of accessoryMeshes) {
        expect(typeof mesh.memberKey).toBe('string');
        expect(mesh.memberKey.startsWith('accessory:')).toBe(true);
      }
    } finally {
      await client.shutdown();
    }
  });

  test('milestone fixture emits startup milestones and frame timbers in raw payload', async () => {
    const client = createRunnerClient('milestone_joint_frame.py');

    try {
      const startup = await waitForReadyAndCollectMilestones(client, 20000);
      expect(startup.ready.type).toBe('ready');
      expect(startup.milestones.length).toBeGreaterThan(0);

      const milestoneNames = startup.milestones
        .map((entry) => (entry && typeof entry.name === 'string' ? entry.name : ''))
        .filter(Boolean);

      expect(milestoneNames).toEqual(
        expect.arrayContaining([
          'fixture:start',
          'fixture:joint-created',
          'fixture:frame-ready',
        ])
      );

      const frame = await client.request('get_frame');
      expect(frame.ok).toBe(true);
      expect(frame.result.name).toBe('Runner Milestone Joint Frame');
      expect(frame.result.timber_count).toBeGreaterThan(0);
      expect(Array.isArray(frame.result.timbers)).toBe(true);
      expect(frame.result.timbers.length).toBe(frame.result.timber_count);
      expect(frame.result.timbers.some((timber) => timber && typeof timber.name === 'string' && timber.name.length > 0)).toBe(true);
    } finally {
      await client.shutdown();
    }
  });

  test('slot commands: load_slot, list_slots, get_frame with slot, unload_slot', async () => {
    const client = createRunnerClient();

    try {
      const ready = await client.readMessage();
      expect(ready.type).toBe('ready');

      // Main slot should already be loaded
      const slots1 = await client.request('list_slots');
      expect(slots1.ok).toBe(true);
      expect(slots1.result.activeSlot).toBe('main');
      expect(slots1.result.slots).toHaveProperty('main');

      // Load a second slot
      const extensionRoot = path.resolve(__dirname, '..');
      const secondFixture = path.join(extensionRoot, 'test-fixtures', 'minimal_frame.py');
      const loadSlot = await client.request('load_slot', { slot: 'secondary', filePath: secondFixture });
      expect(loadSlot.ok).toBe(true);
      expect(loadSlot.result.slot).toBe('secondary');
      expect(loadSlot.result.frame.timber_count).toBeGreaterThan(0);

      // List slots — should now have 2
      const slots2 = await client.request('list_slots');
      expect(slots2.ok).toBe(true);
      expect(Object.keys(slots2.result.slots)).toHaveLength(2);
      expect(slots2.result.slots).toHaveProperty('secondary');

      // Get frame from secondary slot
      const frame = await client.request('get_frame', { slot: 'secondary' });
      expect(frame.ok).toBe(true);
      expect(frame.result.timber_count).toBeGreaterThan(0);

      // Get geometry from secondary slot
      const geom = await client.request('get_geometry', { slot: 'secondary' });
      expect(geom.ok).toBe(true);
      expect(geom.result.kind).toBe('triangle-geometry');
      expect(geom.result.meshes.length).toBeGreaterThan(0);

      // Unload second slot
      const unload = await client.request('unload_slot', { slot: 'secondary' });
      expect(unload.ok).toBe(true);
      expect(unload.result.removed).toBe(true);

      // Verify it's gone
      const slots3 = await client.request('list_slots');
      expect(Object.keys(slots3.result.slots)).toHaveLength(1);
      expect(slots3.result.slots).not.toHaveProperty('secondary');
    } finally {
      await client.shutdown();
    }
  });

  test('raise_specific_pattern loads pattern into slot', async () => {
    const client = createRunnerClient('patternbook_frame.py');

    try {
      const ready = await client.readMessage();
      expect(ready.type).toBe('ready');

      // The main slot loaded the first pattern from the patternbook
      const mainFrame = await client.request('get_frame');
      expect(mainFrame.ok).toBe(true);
      expect(mainFrame.result.timber_count).toBeGreaterThan(0);

      // Now load the second pattern into a new slot
      const extensionRoot = path.resolve(__dirname, '..');
      const sourceFile = path.join(extensionRoot, 'test-fixtures', 'patternbook_frame.py');
      const raise = await client.request('raise_specific_pattern', {
        slot: 'pattern_1',
        sourceFile,
        patternName: 'tall_post_pattern',
      });
      expect(raise.ok).toBe(true);
      expect(raise.result.patternName).toBe('tall_post_pattern');
      expect(raise.result.slot).toBe('pattern_1');
      expect(raise.result.frame.timber_count).toBeGreaterThan(0);

      // Get geometry from the pattern slot
      const geom = await client.request('get_geometry', { slot: 'pattern_1' });
      expect(geom.ok).toBe(true);
      expect(geom.result.meshes.length).toBeGreaterThan(0);

      // Main slot should still work
      const mainGeom = await client.request('get_geometry', { slot: 'main' });
      expect(mainGeom.ok).toBe(true);

      // Unload pattern slot
      const unload = await client.request('unload_slot', { slot: 'pattern_1' });
      expect(unload.ok).toBe(true);
      expect(unload.result.removed).toBe(true);
    } finally {
      await client.shutdown();
    }
  });

  test('raise_specific_pattern supports csg patterns', async () => {
    const client = createRunnerClient();

    try {
      const ready = await client.readMessage();
      expect(ready.type).toBe('ready');

      const projectRoot = path.resolve(__dirname, '..', '..');
      const sourceFile = path.join(projectRoot, 'patterns', 'CSG_debug_examples.py');
      const raise = await client.request('raise_specific_pattern', {
        slot: 'pattern_csg',
        sourceFile,
        patternName: 'halfspace_cut',
      });

      expect(raise.ok).toBe(true);
      expect(raise.result.patternName).toBe('halfspace_cut');
      expect(raise.result.slot).toBe('pattern_csg');
      expect(raise.result.frame.timber_count).toBe(0);
      expect(raise.result.frame.accessories_count).toBeGreaterThan(0);

      const geom = await client.request('get_geometry', { slot: 'pattern_csg' });
      expect(geom.ok).toBe(true);
      expect(geom.result.meshes.length).toBeGreaterThan(0);
      expect(geom.result.meshes[0].memberType).toBe('accessory');
    } finally {
      await client.shutdown();
    }
  });

  test('list_available_patterns discovers patterns', async () => {
    const client = createRunnerClient();

    try {
      const ready = await client.readMessage();
      expect(ready.type).toBe('ready');

      // Pattern scanning loads every pattern file — give it plenty of time
      const result = await client.request('list_available_patterns', {}, 120000);
      expect(result.ok).toBe(true);
      expect(Array.isArray(result.result.sources)).toBe(true);
      // In this project, shipped and/or local patterns should exist
      if (result.result.sources.length > 0) {
        const source = result.result.sources[0];
        expect(typeof source.source).toBe('string');
        expect(Array.isArray(source.patterns)).toBe(true);
        if (source.patterns.length > 0) {
          expect(typeof source.patterns[0].name).toBe('string');
          expect(typeof source.patterns[0].source_file).toBe('string');
        }
      }
    } finally {
      await client.shutdown();
    }
  });
});
