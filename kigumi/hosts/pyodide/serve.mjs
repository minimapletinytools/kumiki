// Serve dist/ on http://127.0.0.1:8123/ (or $PORT), as a static site would: for trying the build.
import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const DIST = path.join(path.dirname(fileURLToPath(import.meta.url)), 'dist');
const TYPES = {
    '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.map': 'application/json', '.wasm': 'application/wasm',
    '.whl': 'application/octet-stream', '.png': 'image/png', '.svg': 'image/svg+xml', '.ttf': 'font/ttf', '.woff2': 'font/woff2',
};
const port = Number(process.env.PORT || 8123);

http.createServer((request, response) => {
    const pathname = decodeURIComponent(new URL(request.url, 'http://x').pathname);
    let file = path.join(DIST, pathname);
    if (!file.startsWith(DIST)) {
        response.writeHead(403).end();
        return;
    }
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
    fs.readFile(file, (error, body) => {
        if (error) {
            response.writeHead(404).end();
            return;
        }
        response.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' });
        response.end(body);
    });
}).listen(port, '127.0.0.1', () => console.log(`Kigumi in a browser: http://127.0.0.1:${port}/`));
