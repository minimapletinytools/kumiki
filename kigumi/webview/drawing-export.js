// A drawing as a PNG: the page as the viewer renders it, cropped from the canvas, with the dimension
// overlay (an SVG over the canvas) drawn on top.

// The style properties the overlay's lines and text take from the stylesheet, which an SVG drawn
// as an image doesn't see.
const INLINED = ['fill', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-opacity', 'stroke-dasharray',
    'stroke-linecap', 'stroke-linejoin', 'opacity', 'visibility', 'display', 'font-family', 'font-size',
    'font-weight', 'font-style', 'text-anchor', 'dominant-baseline', 'paint-order'];

/** `svg` copied with each element's computed style written onto it, standalone at `width` x `height`. */
function standaloneSvg(svg, width, height) {
    const copy = svg.cloneNode(true);
    const sources = [svg, ...svg.querySelectorAll('*')];
    const copies = [copy, ...copy.querySelectorAll('*')];
    sources.forEach((source, index) => {
        const computed = window.getComputedStyle(source);
        copies[index].setAttribute('style', INLINED.map((name) => `${name}:${computed.getPropertyValue(name)}`).join(';'));
    });
    copy.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    copy.setAttribute('width', String(width));
    copy.setAttribute('height', String(height));
    return new window.XMLSerializer().serializeToString(copy);
}

/** Resolve to `markup` (an SVG document) loaded as an image. */
function svgImage(markup) {
    return new Promise((resolve, reject) => {
        const image = new window.Image();
        image.onload = () => resolve(image);
        image.onerror = () => reject(new Error('The dimensions could not be drawn'));
        image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`;
    });
}

/**
 * Return a PNG data URL of the page: `canvas` (rendered at `scale` device pixels per CSS pixel)
 * cropped to `pageRect` (CSS pixels, from the top left), with `overlay` (an SVG sized as the
 * canvas in CSS pixels) drawn over it.
 */
async function composeDrawingPng({ canvas, overlay, pageRect, cssWidth, cssHeight, scale }) {
    const out = document.createElement('canvas');
    out.width = Math.max(1, Math.round(pageRect.width * scale));
    out.height = Math.max(1, Math.round(pageRect.height * scale));
    const context = out.getContext('2d');
    context.drawImage(canvas, pageRect.x * scale, pageRect.y * scale, out.width, out.height, 0, 0, out.width, out.height);
    if (overlay) {
        const image = await svgImage(standaloneSvg(overlay, cssWidth, cssHeight));
        context.drawImage(image, -pageRect.x * scale, -pageRect.y * scale, cssWidth * scale, cssHeight * scale);
    }
    return out.toDataURL('image/png');
}

/** A file name for a drawing's export: its name with anything awkward in a path replaced. */
function drawingFileName(name) {
    return `${String(name || 'drawing').replace(/[^\p{L}\p{N}._-]+/gu, '_').replace(/^_+|_+$/g, '') || 'drawing'}.png`;
}

export { composeDrawingPng, drawingFileName };
