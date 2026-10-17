import { Readable } from 'stream';
import { pipeline } from 'stream/promises';
import { readLimitedBody } from './private-access.js';

export async function proxyApi(request, response, pathname, access, visitor, reply) {
  const allowed = (pathname === '/api/chat' && request.method === 'POST')
    || (['GET', 'HEAD'].includes(request.method) && (['/api/health', '/api/me/cv'].includes(pathname)
      || /^\/api\/kb\/images\/[^/]+$/.test(pathname) || /^\/api\/kb\/pdf\/.+$/.test(pathname)));
  if (!allowed) { reply(404, 'Not Found'); return; }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 180_000);
  const disconnected = () => controller.abort();
  response.once('close', disconnected);
  response.setHeader('Cache-Control', 'no-store');
  try {
    let body;
    if (request.method === 'POST') {
      if (!(request.headers['content-type'] || '').startsWith('application/json')) {
        reply(415, 'Unsupported media type'); return;
      }
      body = await readLimitedBody(request, 32 * 1024);
    }
    const headers = {};
    if (body) headers['Content-Type'] = 'application/json';
    if (access.proxySecret) headers['X-CV-Proxy-Key'] = access.proxySecret;
    if (visitor) headers['X-CV-Visitor'] = visitor;
    const rawPath = (request.url || '').split('?')[0].slice(4);
    const upstream = await fetch(new URL(rawPath, access.apiOrigin), {
      method: request.method, headers, body, signal: controller.signal, redirect: 'manual',
    });
    if (upstream.status >= 300 && upstream.status < 400) {
      await upstream.body?.cancel(); reply(502, 'Service temporarily unavailable'); return;
    }
    response.statusCode = upstream.status;
    for (const name of ['content-type', 'content-disposition', 'x-request-id', 'retry-after']) {
      const value = upstream.headers.get(name);
      if (value) response.setHeader(name, value);
    }
    response.flushHeaders();
    if (upstream.body) await pipeline(Readable.fromWeb(upstream.body), response);
    else response.end();
  } catch (error) {
    if (!response.headersSent && !response.destroyed) reply(error.status === 413 ? 413 : 502, 'Service temporarily unavailable');
    else response.destroy();
  } finally {
    clearTimeout(timeout);
    response.removeListener('close', disconnected);
  }
}
