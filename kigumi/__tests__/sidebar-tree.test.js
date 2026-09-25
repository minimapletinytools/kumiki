const { visibleRows, highlightParts, collapseAll, keyAction } = require('../webview/sidebar/sidebar-tree');

const TREE = [
  {
    key: 'frames', label: 'Frames', expanded: true, children: [
      { key: 'shed', label: 'shed.py', action: { command: 'open' } },
      { key: 'stool', label: 'stool.py', action: { command: 'open' } },
    ],
  },
  {
    key: 'patterns', label: 'Patterns', expanded: false, children: [
      {
        key: 'book', label: 'book', description: '2 patterns', children: [
          { key: 'lap', label: 'half_lap', action: { command: 'open' } },
          { key: 'bridle', label: 'bridle', action: { command: 'open' } },
        ],
      },
    ],
  },
];

const keys = (rows) => rows.map((row) => row.node.key);

describe('visibleRows', () => {
  test('follows each container default until overridden', () => {
    expect(keys(visibleRows(TREE))).toEqual(['frames', 'shed', 'stool', 'patterns']);

    const overrides = new Map([['frames', false], ['patterns', true]]);
    expect(keys(visibleRows(TREE, { overrides }))).toEqual(['frames', 'patterns', 'book']);
  });

  test('a filter shows matches with their ancestors, expanded', () => {
    const rows = visibleRows(TREE, { filter: 'LAP' });

    expect(keys(rows)).toEqual(['patterns', 'book', 'lap']);
    expect(rows.map((row) => row.depth)).toEqual([0, 1, 2]);
    expect(rows[0].isExpanded).toBe(true);
  });

  test('a filter also matches descriptions', () => {
    expect(keys(visibleRows(TREE, { filter: '2 patterns' }))).toEqual(['patterns', 'book']);
  });

  test('a filter that matches nothing shows nothing', () => {
    expect(visibleRows(TREE, { filter: 'zzz' })).toEqual([]);
  });
});

test('highlightParts splits around the first match, ignoring case', () => {
  expect(highlightParts('half_lap', 'LAP')).toEqual(['half_', 'lap', '']);
  expect(highlightParts('shed', '')).toEqual(['shed', '', '']);
});

test('collapseAll closes every container, nested ones included', () => {
  const overrides = collapseAll(TREE);
  expect([...overrides.entries()]).toEqual([['frames', false], ['patterns', false], ['book', false]]);
});

describe('keyAction', () => {
  const rows = visibleRows(TREE);

  test('arrows move, clamped at the ends', () => {
    expect(keyAction(rows, 'frames', 'ArrowDown')).toEqual({ focus: 'shed' });
    expect(keyAction(rows, 'frames', 'ArrowUp')).toEqual({ focus: 'frames' });
    expect(keyAction(rows, 'patterns', 'End')).toEqual({ focus: 'patterns' });
    expect(keyAction(rows, null, 'ArrowDown')).toEqual({ focus: 'frames' });
  });

  test('right expands a closed container, then steps into it', () => {
    expect(keyAction(rows, 'patterns', 'ArrowRight')).toEqual({ toggle: 'patterns' });
    expect(keyAction(rows, 'frames', 'ArrowRight')).toEqual({ focus: 'shed' });
  });

  test('left collapses an open container, or goes to the parent', () => {
    expect(keyAction(rows, 'frames', 'ArrowLeft')).toEqual({ toggle: 'frames' });
    expect(keyAction(rows, 'stool', 'ArrowLeft')).toEqual({ focus: 'frames' });
  });

  test('enter runs a row with an action and toggles a plain container', () => {
    expect(keyAction(rows, 'shed', 'Enter')).toEqual({ run: 'shed' });
    expect(keyAction(rows, 'frames', 'Enter')).toEqual({ toggle: 'frames' });
  });
});
