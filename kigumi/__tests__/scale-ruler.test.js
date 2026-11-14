const { rulerLength } = require('../webview/scale-ruler.js');

test('the longest round length that fits, in the viewer\'s units', () => {
    // 1 mm a pixel: 100 mm is 100 px, 200 mm would be 200.
    expect(rulerLength(0.001, 'metric')).toMatchObject({ label: '100 mm', px: 100 });
    // 1 cm a pixel: 1 m is 100 px.
    expect(rulerLength(0.01, 'metric')).toMatchObject({ label: '1 m' });
    expect(rulerLength(0.01, 'metric').px).toBeCloseTo(100);
    // An inch a pixel: 10 feet is 120 px.
    expect(rulerLength(0.0254, 'imperial')).toMatchObject({ label: "10'" });
    expect(rulerLength(0.0254 / 64, 'imperial')).toMatchObject({ label: '1"' });
    // A shaku is 10/33 m: at a sun a pixel, 1 shaku is 10 px and 10 shaku 100.
    expect(rulerLength((10 / 33) / 10, 'shaku')).toMatchObject({ label: '10尺' });
    expect(rulerLength((10 / 33) / 1000, 'shaku')).toMatchObject({ label: '1寸' });
});

test('the shortest when even that is too wide, and none without a scale', () => {
    expect(rulerLength(0.00001, 'metric')).toMatchObject({ label: '1 mm', px: 100 });
    expect(rulerLength(0, 'metric')).toBeNull();
    expect(rulerLength(NaN, 'metric')).toBeNull();
    expect(rulerLength(0.001, 'nonsense')).toMatchObject({ label: '100 mm' });
});
