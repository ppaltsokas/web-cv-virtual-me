import { createHash, randomBytes, scrypt, timingSafeEqual } from 'crypto';
import { promisify } from 'util';
import { accessPage, accessMessages } from './access-page.js';
import { entranceAssets, entranceCsp } from './entrance-assets.js';

const deriveKey = promisify(scrypt);
const passwordOptions = { N: 131072, r: 8, p: 1, maxmem: 192 * 1024 * 1024 };
const sessionLifetime = 8 * 60 * 60 * 1000;
const tokenHash = token => createHash('sha256').update(token).digest('hex');

export async function hashAccessPassword(password) {
  const salt = randomBytes(16).toString('hex');
  const key = await deriveKey(password, salt, 64, passwordOptions);
  return `scrypt:${salt}:${key.toString('hex')}`;
}

export async function readLimitedBody(request, limit) {
  const chunks = [];
  let size = 0;
  const timeout = setTimeout(() => request.destroy(), 10_000);
  try {
    for await (const chunk of request.iterator({ destroyOnReturn: false })) {
      size += chunk.length;
      if (size > limit) {
        request.resume();
        throw Object.assign(new Error('Request too large'), { status: 413 });
      }
      chunks.push(chunk);
    }
    return Buffer.concat(chunks);
  } finally {
    clearTimeout(timeout);
  }
}

export function createPrivateAccess(env = process.env, now = Date.now) {
  const hosted = Boolean(env.RAILWAY_ENVIRONMENT_ID) || env.NODE_ENV === 'production';
  const enabled = hosted || /^(true|1|yes|on)$/i.test(env.PRIVATE_CV_ENABLED || '')
    || Boolean(env.CV_ACCESS_PASSWORD_HASH || env.CV_API_PROXY_SECRET);
  let origin;
  let apiOrigin;
  let valid = true;
  try {
    origin = new URL(env.CV_PUBLIC_ORIGIN || 'http://127.0.0.1:3000');
    apiOrigin = new URL(env.CV_API_ORIGIN || 'http://127.0.0.1:8000');
    for (const url of [origin, apiOrigin]) {
      if (url.username || url.password || url.search || url.hash || url.pathname !== '/'
          || (url.protocol !== 'https:' && !(url.protocol === 'http:' && !hosted
            && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)))) valid = false;
    }
    if (enabled && (!env.CV_PUBLIC_ORIGIN || !env.CV_API_ORIGIN
        || !/^scrypt:[a-f0-9]{32}:[a-f0-9]{128}$/.test(env.CV_ACCESS_PASSWORD_HASH || '')
        || !/^[A-Za-z0-9_-]{32,128}$/.test(env.CV_API_PROXY_SECRET || ''))) valid = false;
  } catch {
    valid = false;
  }
  const secure = origin?.protocol === 'https:';
  const cookieName = secure ? '__Host-cv_access' : 'cv_access';
  const sessions = new Map();
  let attempts = 0;
  let windowStart = now();
  let verifying = false;
  const sameOrigin = request => request.headers.origin === origin?.origin;
  const cookie = (token, maxAge) => `${cookieName}=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAge}${secure ? '; Secure' : ''}`;
  return {
    enabled, valid, apiOrigin, proxySecret: env.CV_API_PROXY_SECRET,
    async authorize(request, response, pathname, reply) {
      if (!valid) { reply(503, 'Service temporarily unavailable'); return { handled: true }; }
      if (!enabled) return { handled: false };
      response.setHeader('Cache-Control', 'no-store');
      response.setHeader('Referrer-Policy', 'same-origin');
      response.setHeader('X-Frame-Options', 'DENY');
      for (const [key, session] of sessions) if (session.expires <= now()) sessions.delete(key);
      const cookies = (request.headers.cookie || '').split(';').map(value => value.trim())
        .filter(value => value.startsWith(`${cookieName}=`));
      const token = cookies.length === 1 ? cookies[0].slice(cookieName.length + 1) : '';
      const visitor = /^[A-Za-z0-9_-]{43}$/.test(token) ? tokenHash(token) : undefined;
      const signedIn = Boolean(visitor && sessions.has(visitor));
      if (entranceAssets.has(pathname) && ['GET', 'HEAD'].includes(request.method)) {
        return { handled: false, entranceAsset: true };
      }
      if (pathname === '/access' && ['GET', 'HEAD'].includes(request.method)) {
        response.setHeader('Content-Security-Policy', entranceCsp);
        reply(200, accessPage(signedIn), 'text/html; charset=utf-8');
        return { handled: true };
      }
      if (pathname === '/access/login' && request.method === 'POST') {
        // Explicit negotiation only; fetch never follows a portfolio redirect to infer success.
        const json = (request.headers.accept || '').split(',').some(value => {
          const [type, ...parameters] = value.trim().toLowerCase().split(';');
          return type === 'application/json' && !parameters.some(part => /^\s*q=0(?:\.0*)?\s*$/.test(part));
        });
        response.setHeader('Vary', 'Accept');
        const failure = (status, error) => {
          if (json) reply(status, JSON.stringify({ authenticated: false, error, message: accessMessages[error] }), 'application/json; charset=utf-8');
          else {
            response.setHeader('Content-Security-Policy', entranceCsp);
            reply(status, accessPage(false, error), 'text/html; charset=utf-8');
          }
        };
        if (!sameOrigin(request)) { failure(403, 'forbidden'); return { handled: true }; }
        if (now() - windowStart >= 15 * 60 * 1000) { attempts = 0; windowStart = now(); }
        if (verifying || attempts >= 10) {
          response.setHeader('Retry-After', String(Math.max(1, Math.ceil((windowStart + 15 * 60 * 1000 - now()) / 1000))));
          failure(429, 'rate_limited'); return { handled: true };
        }
        attempts += 1;
        if (!(request.headers['content-type'] || '').startsWith('application/x-www-form-urlencoded')) {
          failure(415, 'invalid_request'); return { handled: true };
        }
        verifying = true;
        try {
          const body = await readLimitedBody(request, 1024);
          const values = new URLSearchParams(body.toString('utf8')).getAll('password');
          const password = values.length === 1 ? values[0] : '';
          const [, salt, expected] = env.CV_ACCESS_PASSWORD_HASH.split(':');
          const derived = await deriveKey(password.slice(0, 128), salt, 64, passwordOptions);
          if (!password || password.length > 128 || !timingSafeEqual(derived, Buffer.from(expected, 'hex'))) {
            failure(401, 'invalid_password'); return { handled: true };
          }
          if (sessions.size >= 64) { failure(503, 'unavailable'); return { handled: true }; }
          if (signedIn) sessions.delete(visitor);
          const freshToken = randomBytes(32).toString('base64url');
          sessions.set(tokenHash(freshToken), { expires: now() + sessionLifetime });
          response.setHeader('Set-Cookie', cookie(freshToken, sessionLifetime / 1000));
          if (json) reply(200, JSON.stringify({ authenticated: true, redirect: '/' }), 'application/json; charset=utf-8');
          else { response.setHeader('Location', '/'); reply(303, 'Signed in'); }
        } catch (error) {
          failure(error.status === 413 ? 413 : 503, error.status === 413 ? 'invalid_request' : 'unavailable');
        } finally {
          verifying = false;
        }
        return { handled: true };
      }
      if (pathname === '/access/logout' && request.method === 'POST') {
        if (!sameOrigin(request)) { reply(403, 'Forbidden'); return { handled: true }; }
        if (signedIn) sessions.delete(visitor);
        response.setHeader('Set-Cookie', cookie('', 0));
        response.setHeader('Location', '/access'); reply(303, 'Signed out'); return { handled: true };
      }
      if (!signedIn) {
        if (['GET', 'HEAD'].includes(request.method) && !pathname.startsWith('/api/')) {
          response.setHeader('Location', '/access'); reply(303, 'Sign in required');
        } else reply(401, 'Sign in required');
        return { handled: true };
      }
      if (!['GET', 'HEAD'].includes(request.method) && !sameOrigin(request)) {
        reply(403, 'Forbidden'); return { handled: true };
      }
      return { handled: false, visitor };
    },
  };
}
