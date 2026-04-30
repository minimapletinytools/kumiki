const { SelectionStore } = require('../webview/selection-store');

describe('SelectionStore', () => {
  test('single timber selection replaces previous selection', () => {
    const store = new SelectionStore();
    store.selectTimber('A');
    store.selectTimber('B');

    expect(store.getSelectedTimbers()).toEqual(['B']);
    expect(store.isTimberSelected('A')).toBe(false);
  });

  test('additive timber selection keeps existing selection', () => {
    const store = new SelectionStore();
    store.selectTimber('A');
    store.selectTimber('B', true);

    expect(new Set(store.getSelectedTimbers())).toEqual(new Set(['A', 'B']));
  });

  test('toggleTimber adds and removes', () => {
    const store = new SelectionStore();
    store.toggleTimber('A');
    expect(store.isTimberSelected('A')).toBe(true);

    store.toggleTimber('A');
    expect(store.isTimberSelected('A')).toBe(false);
  });

  test('feature selection supports additive list behavior', () => {
    const store = new SelectionStore();
    store.selectFeature('timber-1', 'feature-a');
    store.selectFeature('timber-1', 'feature-b', true);

    expect(store.selectedFeatures).toEqual([
      { timberName: 'timber-1', featureId: 'feature-a' },
      { timberName: 'timber-1', featureId: 'feature-b' },
    ]);
  });

  test('clear operations clear only their selection type', () => {
    const store = new SelectionStore();
    store.selectTimber('A');
    store.selectFeature('A', 'face-1');

    store.clearTimberSelection();
    expect(store.getSelectedTimbers()).toEqual([]);
    expect(store.selectedFeatures).toEqual([{ timberName: 'A', featureId: 'face-1' }]);

    store.clearFeatureSelection();
    expect(store.selectedFeatures).toEqual([]);
  });

  test('onSelectionChanged emits and unsubscribe stops emitting', () => {
    const store = new SelectionStore();
    const listener = jest.fn();
    const unsubscribe = store.onSelectionChanged(listener);

    store.selectTimber('A');
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    store.selectTimber('B');
    expect(listener).toHaveBeenCalledTimes(1);
  });

  test('selectCSG stores csg selection state', () => {
    const store = new SelectionStore();
    store.selectCSG('post#0', ['mortise_and_tenon'], null);

    expect(store.csgSelection).toEqual({
      timberKey: 'post#0',
      path: ['mortise_and_tenon'],
      featureLabel: null,
    });
  });

  test('selectCSG updates path on deeper navigation', () => {
    const store = new SelectionStore();
    store.selectCSG('post#0', ['mortise_and_tenon'], null);
    store.selectCSG('post#0', ['mortise_and_tenon', 'tenon'], null);

    expect(store.csgSelection.path).toEqual(['mortise_and_tenon', 'tenon']);
  });

  test('selectCSG sets featureLabel at leaf', () => {
    const store = new SelectionStore();
    store.selectCSG('post#0', ['mortise_and_tenon', 'tenon'], 'front');

    expect(store.csgSelection.featureLabel).toBe('front');
  });

  test('clearCSGSelection clears csg state', () => {
    const store = new SelectionStore();
    store.selectCSG('post#0', ['mortise_and_tenon'], null);
    store.clearCSGSelection();

    expect(store.csgSelection).toBeNull();
  });

  test('clearCSGSelection is no-op when already null', () => {
    const store = new SelectionStore();
    const listener = jest.fn();
    store.onSelectionChanged(listener);
    store.clearCSGSelection();

    expect(listener).not.toHaveBeenCalled();
  });

  test('hasSelection includes csg selection', () => {
    const store = new SelectionStore();
    expect(store.hasSelection()).toBe(false);

    store.selectCSG('post#0', [], null);
    expect(store.hasSelection()).toBe(true);

    store.clearCSGSelection();
    expect(store.hasSelection()).toBe(false);
  });

  test('selectCSG emits csg-selected event', () => {
    const store = new SelectionStore();
    const listener = jest.fn();
    store.onSelectionChanged(listener);

    store.selectCSG('post#0', ['mortise_and_tenon'], null);

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith({
      type: 'csg-selected',
      csgSelection: {
        timberKey: 'post#0',
        path: ['mortise_and_tenon'],
        featureLabel: null,
      },
    });
  });

  test('clearCSGSelection emits clear-csg event', () => {
    const store = new SelectionStore();
    store.selectCSG('post#0', ['mortise_and_tenon'], null);

    const listener = jest.fn();
    store.onSelectionChanged(listener);
    store.clearCSGSelection();

    expect(listener).toHaveBeenCalledWith({ type: 'clear-csg' });
  });
});
