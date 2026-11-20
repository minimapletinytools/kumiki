// Which layout the shell starts in (webview/shell/choose-layout.js).
import { chooseLayout } from '../webview/shell/choose-layout.js';

const both = ['desktop', 'phone'];

test('a small touch screen gets the phone layout, where the host has one', () => {
    expect(chooseLayout({ offered: both, coarsePointer: true, shortestSide: 390 })).toBe('phone');
    expect(chooseLayout({ offered: ['desktop'], coarsePointer: true, shortestSide: 390 })).toBe('desktop');
});

test('a tablet, or a small window with a mouse, gets the desktop layout', () => {
    expect(chooseLayout({ offered: both, coarsePointer: true, shortestSide: 768 })).toBe('desktop');
    expect(chooseLayout({ offered: both, coarsePointer: false, shortestSide: 390 })).toBe('desktop');
});

test('?layout= picks either, but only one the host offers', () => {
    expect(chooseLayout({ offered: both, asked: 'phone', coarsePointer: false, shortestSide: 1200 })).toBe('phone');
    expect(chooseLayout({ offered: both, asked: 'desktop', coarsePointer: true, shortestSide: 390 })).toBe('desktop');
    expect(chooseLayout({ offered: ['desktop'], asked: 'phone', coarsePointer: false, shortestSide: 1200 })).toBe('desktop');
    expect(chooseLayout({ offered: both, asked: 'tablet', coarsePointer: false, shortestSide: 1200 })).toBe('desktop');
});
