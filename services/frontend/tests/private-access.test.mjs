import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtemp, writeFile, rm, mkdir } from 'node:fs/promises';
import fs from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { createStaticServer } from '../server.js';
import { createPrivateAccess, hashAccessPassword } from '../private-access.js';

const password = 'synthetic-password-do-not-use';
const passwordHash = await hashAccessPassword(password);
const proxySecret = 's'.repeat(43);
const origin = 'http://127.0.0.1:3000';

async function listen(server) {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return `http://127.0.0.1:${server.address().port}`;
}

async function fixture(context, extra = {}, clock = Date.now) {
  const distDir = await mkdtemp(path.join(tmpdir(), 'private-cv-test-'));
  await writeFile(path.join(distDir, 'index.html'), 'synthetic private CV');
  await writeFile(path.join(distDir, 'asset.js'), 'synthetic private asset');
  await writeFile(path.join(distDir, 'cv.pdf'), '%PDF-synthetic-private');
  await mkdir(path.join(distDir, 'entrance'));
  await writeFile(path.join(distDir, 'entrance', 'entrance.js'), 'synthetic public entrance');
  await writeFile(path.join(distDir, 'entrance', 'command-panel.svg'), '<svg xmlns="http://www.w3.org/2000/svg"/>');
  await writeFile(path.join(distDir, 'entrance', 'resume.json'), 'synthetic private resume');
  const env = { PRIVATE_CV_ENABLED: 'true', CV_PUBLIC_ORIGIN: origin,
    CV_API_ORIGIN: 'http://127.0.0.1:8000', CV_ACCESS_PASSWORD_HASH: passwordHash,
    CV_API_PROXY_SECRET: proxySecret, ...extra };
  const logs = [];
  const server = createStaticServer({ distDir, access: createPrivateAccess(env, clock),
    logger: { log: value => logs.push(value) } });
  const base = await listen(server);
  context.after(async () => {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    await rm(distDir, { recursive: true });
  });
  return { base, logs, distDir };
}

async function login(base, supplied = password) {
  return fetch(`${base}/access/login`, { method: 'POST', redirect: 'manual',
    headers: { Origin: origin, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ password: supplied }).toString() });
}

test('private CV requires login, limits attempts, expires sessions and revokes logout', async context => {
  let now = Date.now();
  const { base, logs } = await fixture(context, {}, () => now);
  assert.equal((await fetch(`${base}/`, { redirect: 'manual' })).status, 303);
  assert.equal((await fetch(`${base}/asset.js`, { redirect: 'manual' })).status, 303);
  assert.equal((await fetch(`${base}/api/chat`, { method: 'POST', body: '{}' })).status, 401);
  const page = await fetch(`${base}/access`);
  assert.equal(page.headers.get('cache-control'), 'no-store');
  assert.equal(page.headers.get('referrer-policy'), 'same-origin');
  assert.ok(!(await page.text()).includes('synthetic private CV'));
  const wrongPassword = await login(base, 'wrong');
  assert.equal(wrongPassword.status, 401);
  assert.equal(wrongPassword.headers.get('referrer-policy'), 'same-origin');
  for (const suppliedOrigin of [undefined, 'null', 'http://localhost:3000']) {
    const headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
    if (suppliedOrigin !== undefined) headers.Origin = suppliedOrigin;
    const rejected = await fetch(`${base}/access/login`, { method: 'POST', redirect: 'manual',
      headers, body: new URLSearchParams({ password }).toString() });
    assert.equal(rejected.status, 403);
    assert.equal(rejected.headers.get('set-cookie'), null);
  }
  const forged = await fetch(`${base}/access/login`, { method: 'POST',
    headers: { Origin: 'https://attacker.invalid', 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ password }).toString() });
  assert.equal(forged.status, 403);
  assert.equal(forged.headers.get('set-cookie'), null);
  const success = await login(base);
  assert.equal(success.status, 303);
  const setCookie = success.headers.get('set-cookie');
  assert.match(setCookie, /HttpOnly; SameSite=Lax; Max-Age=28800/);
  const cookie = setCookie.split(';')[0];
  assert.equal(await (await fetch(`${base}/`, { headers: { Cookie: cookie } })).text(), 'synthetic private CV');
  const alteredCookie = `${cookie.slice(0, -1)}${cookie.endsWith('a') ? 'b' : 'a'}`;
  assert.equal((await fetch(`${base}/api/health`, { headers: { Cookie: alteredCookie } })).status, 401);
  const logout = await fetch(`${base}/access/logout`, { method: 'POST', redirect: 'manual',
    headers: { Origin: origin, Cookie: cookie } });
  assert.equal(logout.status, 303);
  assert.equal((await fetch(`${base}/api/health`, { headers: { Cookie: cookie } })).status, 401);
  const freshCookie = (await login(base)).headers.get('set-cookie').split(';')[0];
  assert.notEqual(cookie, freshCookie);
  now += 8 * 60 * 60 * 1000;
  assert.equal((await fetch(`${base}/api/health`, { headers: { Cookie: freshCookie } })).status, 401);
  for (let attempt = 0; attempt < 10; attempt += 1) {
    assert.equal((await fetch(`${base}/access/login`, { method: 'POST', headers: { Origin: origin }, body: 'bad' })).status, 415);
  }
  assert.equal((await login(base)).status, 429);
  for (const value of [password, passwordHash, proxySecret, cookie]) assert.ok(!logs.join('\n').includes(value));
});

test('hosted access is closed when incomplete and HTTPS cookies are secure', async context => {
  const blocked = await fixture(context, { NODE_ENV: 'production', PRIVATE_CV_ENABLED: 'false',
    CV_ACCESS_PASSWORD_HASH: '', CV_PUBLIC_ORIGIN: 'https://cv.example', CV_API_ORIGIN: 'https://api.example' });
  assert.equal((await fetch(`${blocked.base}/`)).status, 503);
  assert.equal((await fetch(`${blocked.base}/health`)).status, 200);
  const secure = await fixture(context, { NODE_ENV: 'production', CV_PUBLIC_ORIGIN: 'https://cv.example', CV_API_ORIGIN: 'https://api.example' });
  const response = await fetch(`${secure.base}/access/login`, { method: 'POST', redirect: 'manual',
    headers: { Origin: 'https://cv.example', 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ password }).toString() });
  assert.equal(response.status, 303);
  assert.match(response.headers.get('set-cookie'), /^__Host-cv_access=.*; Secure$/);
  const page = await fetch(`${secure.base}/access`);
  assert.equal(page.headers.get('referrer-policy'), 'same-origin');
});

test('public entrance is isolated, CSP is restrictive, native failure stays usable, symlinks cannot escape', async context => {
  const { base, distDir } = await fixture(context);
  const page = await fetch(`${base}/access`);
  const html = await page.text();
  assert.match(html, /method="post" action="\/access\/login"/);
  assert.match(html, /autocomplete="current-password"/);
  assert.match(html, /type="module" src="\/entrance\/entrance.js"/);
  assert.ok(!html.includes('synthetic private'));
  const csp = page.headers.get('content-security-policy');
  assert.match(csp, /script-src 'self'/);
  assert.match(csp, /connect-src 'self'/);
  assert.match(csp, /font-src 'self'/);
  assert.ok(!/unsafe-inline|unsafe-eval|\*/.test(csp));
  assert.equal(await (await fetch(`${base}/entrance/entrance.js`)).text(), 'synthetic public entrance');
  assert.equal((await fetch(`${base}/entrance/entrance.js`, { method: 'HEAD' })).status, 200);
  const font = await fetch(`${base}/entrance/command-panel.svg`);
  assert.equal(font.status, 200);
  assert.equal(font.headers.get('content-type'), 'image/svg+xml');
  for (const route of ['/asset.js', '/cv.pdf', '/entrance/resume.json', '/entrance/missing.js', '/entrance/index.html']) {
    assert.equal((await fetch(`${base}${route}`, { redirect: 'manual' })).status, 303, route);
  }
  assert.equal((await fetch(`${base}/api/me/cv`)).status, 401);
  const denied = await login(base, 'wrong');
  assert.equal(denied.status, 401);
  assert.match(denied.headers.get('content-security-policy'), /script-src 'self'/);
  assert.match(await denied.text(), /Incorrect password/);
  const original = fs.promises.realpath;
  // Deterministic on Windows without symlink creation privileges. Exercise realpath containment.
  fs.promises.realpath = async candidate => candidate === path.join(distDir, 'entrance', 'entrance.js') ? path.join(distDir, 'asset.js') : original(candidate);
  try { assert.equal((await fetch(`${base}/entrance/entrance.js`)).status, 403); }
  finally { fs.promises.realpath = original; }
});

test('explicit JSON negotiation preserves session, failure status, origin checks, and throttling', async context => {
  const { base, logs } = await fixture(context);
  const post = (supplied, extra = {}) => fetch(`${base}/access/login`, { method: 'POST', redirect: 'manual',
    headers: { Origin: origin, Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded', ...extra },
    body: new URLSearchParams({ password: supplied }) });
  const rejected = await post('wrong');
  assert.equal(rejected.status, 401);
  assert.equal(rejected.headers.get('set-cookie'), null);
  assert.equal((await rejected.json()).error, 'invalid_password');
  const forbidden = await post(password, { Origin: 'https://attacker.invalid' });
  assert.equal(forbidden.status, 403);
  assert.equal((await forbidden.json()).error, 'forbidden');
  const native = await post(password, { Accept: 'application/json;q=0, text/html' });
  assert.equal(native.status, 303);
  const success = await post(password);
  assert.equal(success.status, 200);
  assert.deepEqual(await success.json(), { authenticated: true, redirect: '/' });
  assert.equal(success.headers.get('location'), null);
  assert.equal(success.headers.get('vary'), 'Accept');
  const cookie = success.headers.get('set-cookie').split(';')[0];
  assert.equal(await (await fetch(`${base}/`, { headers: { Cookie: cookie } })).text(), 'synthetic private CV');
  const signedIn = await (await fetch(`${base}/access`, { headers: { Cookie: cookie } })).text();
  assert.match(signedIn, /Sign out/);
  assert.ok(!signedIn.includes('data-login-form'));
  assert.ok(!signedIn.includes('data-skip'));
  const invalid = await post(password, { 'Content-Type': 'application/json' });
  assert.equal(invalid.status, 415);
  assert.equal((await invalid.json()).error, 'invalid_request');
  const oversized = await fetch(`${base}/access/login`, { method: 'POST', headers: { Origin: origin, Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded' }, body: 'x'.repeat(1025) });
  assert.equal(oversized.status, 413);
  assert.equal((await oversized.json()).error, 'invalid_request');
  // Exhaust remaining attempts cheaply with invalid media types.
  for (let index = 0; index < 5; index++) await post('bad', { 'Content-Type': 'text/plain' });
  const limited = await post(password);
  assert.equal(limited.status, 429);
  assert.equal((await limited.json()).error, 'rate_limited');
  assert.ok(Number(limited.headers.get('retry-after')) > 0);
  for (const secret of [password, passwordHash, proxySecret, cookie]) assert.ok(!logs.join('\n').includes(secret));
});

test('proxy streams, protects downloads, strips client secrets and rejects oversized bodies', async context => {
  const requests = [];
  let release;
  let upstreamCancelled = false;
  const upstream = http.createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    requests.push({ headers: request.headers, path: request.url, body: Buffer.concat(chunks).toString() });
    if (request.url === '/chat') {
      response.on('close', () => {
        if (!response.writableEnded) { upstreamCancelled = true; release?.(); }
      });
      response.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8', 'X-CV-Proxy-Key': proxySecret });
      response.write('first ');
      await new Promise(resolve => { release = resolve; });
      response.end('second [S1]\nSources: sample-project.md');
    } else if (request.url.endsWith('redirect.pdf')) {
      response.writeHead(302, { Location: 'https://attacker.invalid' }); response.end();
    } else {
      response.writeHead(200, { 'Content-Type': 'application/pdf', 'Content-Disposition': 'attachment; filename="cv.pdf"' });
      response.end('%PDF-protected');
    }
  });
  const upstreamBase = await listen(upstream);
  context.after(async () => {
    release?.(); upstream.closeAllConnections();
    await new Promise(resolve => upstream.close(resolve));
  });
  const { base } = await fixture(context, { CV_API_ORIGIN: upstreamBase });
  const cookie = (await login(base)).headers.get('set-cookie').split(';')[0];
  const headers = { Origin: origin, Cookie: cookie, 'Content-Type': 'application/json',
    Authorization: 'Bearer forged', 'X-Admin-Key': 'forged', 'X-CV-Proxy-Key': 'forged', 'X-CV-Visitor': 'forged', 'X-Forwarded-For': 'forged' };
  const body = JSON.stringify({ message: 'Events Explorer?', session_id: 'follow-up-session' });
  assert.equal((await fetch(`${base}/api/chat`, { method: 'POST', headers: { ...headers, Origin: 'https://attacker.invalid' }, body })).status, 403);
  assert.equal((await fetch(`${base}/api/diagnostics/status`, { headers })).status, 404);
  assert.equal((await fetch(`${base}/api/chat`, { method: 'POST', headers, body: 'x'.repeat(32769) })).status, 413);
  assert.equal(requests.length, 0);
  const response = await fetch(`${base}/api/chat`, { method: 'POST', headers, body });
  assert.equal(response.headers.get('x-cv-proxy-key'), null);
  const reader = response.body.getReader();
  assert.equal(new TextDecoder().decode((await reader.read()).value), 'first ');
  release();
  let remainder = '';
  for (;;) {
    const chunk = await reader.read();
    if (chunk.done) break;
    remainder += new TextDecoder().decode(chunk.value);
  }
  assert.equal(remainder, 'second [S1]\nSources: sample-project.md');
  assert.equal(requests[0].body, body);
  assert.equal(requests[0].headers['x-cv-proxy-key'], proxySecret);
  assert.match(requests[0].headers['x-cv-visitor'], /^[a-f0-9]{64}$/);
  for (const name of ['authorization', 'cookie', 'x-admin-key', 'x-forwarded-for']) assert.equal(requests[0].headers[name], undefined);
  assert.equal(await (await fetch(`${base}/api/me/cv`, { headers: { Cookie: cookie } })).text(), '%PDF-protected');
  assert.equal((await fetch(`${base}/api/kb/pdf/redirect.pdf`, { headers: { Cookie: cookie } })).status, 502);
  const interrupted = await fetch(`${base}/api/chat`, { method: 'POST', headers, body });
  const interruptedReader = interrupted.body.getReader();
  await interruptedReader.read();
  await interruptedReader.cancel();
  for (let poll = 0; poll < 100 && !upstreamCancelled; poll += 1) await new Promise(resolve => setTimeout(resolve, 10));
  assert.equal(upstreamCancelled, true);
});
