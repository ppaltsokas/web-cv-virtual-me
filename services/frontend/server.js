import http from 'http';
import fs from 'fs';
import path from 'path';
import { randomUUID } from 'crypto';
import { fileURLToPath } from 'url';
import { createPrivateAccess } from './private-access.js';
import { proxyApi } from './api-proxy.js';

const filename = fileURLToPath(import.meta.url);
const defaultDistDir = path.join(path.dirname(filename), 'dist');
const mimeTypes = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.pdf': 'application/pdf',
  '.webp': 'image/webp',
  '.woff': 'font/woff',
};

function isContained(root, target) {
  const relative = path.relative(root, target);
  return relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}

export function createStaticServer({ distDir = defaultDistDir, logger = console, access = createPrivateAccess() } = {}) {
  const root = fs.realpathSync(distDir);
  return http.createServer(async (request, response) => {
    const requestId = randomUUID();
    response.on('finish', () => logger.log(JSON.stringify({
      requestId, method: request.method, status: response.statusCode,
    })));
    const reply = (status, body, contentType = 'text/plain') => {
      response.writeHead(status, {
        'Content-Type': contentType,
        'Content-Length': Buffer.byteLength(body),
        'X-Content-Type-Options': 'nosniff',
      });
      response.end(request.method === 'HEAD' ? undefined : body);
    };
    response.setHeader('X-Content-Type-Options', 'nosniff');
    let pathname;
    try {
      pathname = decodeURIComponent((request.url || '/').split('?')[0]);
    } catch {
      reply(400, 'Bad Request');
      return;
    }
    if (!pathname.startsWith('/') || pathname.startsWith('//') || /[\\%\x00-\x1f\x7f]/.test(pathname)
        || pathname.split('/').includes('..') || pathname.includes(':')) {
      reply(403, 'Forbidden');
      return;
    }
    if (['/health', '/healthz', '/_health'].includes(pathname) && ['GET', 'HEAD'].includes(request.method)) {
      reply(200, JSON.stringify({ status: 'ok', timestamp: new Date().toISOString() }), 'application/json');
      return;
    }
    const authorization = await access.authorize(request, response, pathname, reply);
    if (authorization.handled) return;
    if (pathname.startsWith('/api/')) {
      await proxyApi(request, response, pathname, access, authorization.visitor, reply);
      return;
    }
    if (!['GET', 'HEAD'].includes(request.method)) {
      response.setHeader('Allow', 'GET, HEAD');
      reply(405, 'Method Not Allowed');
      return;
    }
    const requestedPath = path.resolve(root, `.${pathname === '/' ? '/index.html' : pathname}`);
    if (!isContained(root, requestedPath)) {
      reply(403, 'Forbidden');
      return;
    }
    try {
      let filePath;
      try {
        filePath = await fs.promises.realpath(requestedPath);
      } catch (error) {
        if (error.code !== 'ENOENT' || path.extname(pathname)) throw error;
        filePath = await fs.promises.realpath(path.join(root, 'index.html'));
      }
      if (!isContained(root, filePath)) {
        reply(403, 'Forbidden');
        return;
      }
      // Public entrance symlinks must never point into the private build, even within dist.
      if (authorization.entranceAsset && !isContained(path.join(root, 'entrance'), filePath)) {
        reply(403, 'Forbidden');
        return;
      }
      const data = await fs.promises.readFile(filePath);
      reply(200, data, mimeTypes[path.extname(filePath).toLowerCase()] || 'application/octet-stream');
    } catch (error) {
      reply(['ENOENT', 'ENOTDIR', 'EISDIR'].includes(error.code) ? 404 : 500, 'Unable to serve resource');
    }
  });
}

if (process.argv[1] && path.resolve(process.argv[1]) === filename) {
  const port = process.env.PORT || 3000;
  try {
    const server = createStaticServer();
    server.on('error', () => {
      console.error('Static server failed to start');
      process.exit(1);
    });
    server.listen(port, '0.0.0.0', () => console.log(`Static server listening on port ${port}`));
  } catch {
    console.error('Static server failed to start');
    process.exit(1);
  }
}
