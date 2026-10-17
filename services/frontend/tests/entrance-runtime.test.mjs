import assert from 'node:assert/strict';
import { test } from 'node:test';

class Element extends EventTarget {
  constructor() {
    super(); this.attributes = {}; this.value = ''; this.textContent = ''; this.dataset = {};
    this.classes = new Set(); this.classList = { toggle: (name, value) => value ? this.classes.add(name) : this.classes.delete(name) };
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  focus() { this.focused = true; }
  select() { this.selected = true; }
  reportValidity() { return Boolean(this.input.value); }
}
const settle = () => new Promise(resolve => setImmediate(resolve));
let fixtureNumber = 0;
async function mount(t, { reduced = false, message = '', signedIn = false } = {}) {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const root = new Element(), form = new Element(), input = new Element(), submit = new Element(), status = new Element();
  const desktop = new Element(), mobile = new Element();
  for (const [scene, variant] of [[desktop, 'landscape'], [mobile, 'portrait']]) {
    scene.dataset.variant = variant;
    scene.pauseAnimations = () => { scene.paused = true; };
    scene.unpauseAnimations = () => { scene.paused = false; };
  }
  status.textContent = message; input.value = 'synthetic-browser-password'; form.input = input;
  root.querySelector = selector => ({ '[data-login-form]': signedIn ? undefined : form, '[data-status]': status })[selector];
  root.querySelectorAll = () => [desktop, mobile];
  form.querySelector = selector => ({ input, '[data-submit]': submit })[selector];
  const document = new Element(), window = new Element(), motion = new Element(), portrait = new Element();
  document.hidden = false; document.querySelector = () => root; motion.matches = reduced; portrait.matches = false;
  const calls = [], pending = [], destinations = [];
  const bindings = { document, window, matchMedia: query => query.includes('reduced-motion') ? motion : portrait,
    location: { assign: destination => destinations.push(destination) },
    FormData: class { *[Symbol.iterator]() { yield ['password', input.value]; } },
    fetch: (...args) => {
      calls.push(args);
      return new Promise((resolve, reject) => {
        pending.push({ resolve, reject });
        args[1].signal.addEventListener('abort', () => reject(new DOMException('Timeout', 'AbortError')));
      });
    } };
  const originals = new Map(Object.keys(bindings).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries(bindings)) Object.defineProperty(globalThis, key, { value, configurable: true, writable: true });
  t.after(() => {
    window.dispatchEvent(new Event('pagehide'));
    for (const [key, descriptor] of originals) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; }
  });
  await import('../public/entrance/entrance.js?fixture=' + ++fixtureNumber);
  const submitForm = () => form.dispatchEvent(new Event('submit', { cancelable: true }));
  const respond = async (code, data, headers = {}) => {
    pending.shift().resolve(new Response(JSON.stringify(data), { status: code, headers })); await settle();
  };
  return { root, form, input, submit, status, document, window, motion, portrait, desktop, mobile, calls, pending, destinations, submitForm, respond };
}

test('runtime immediately shows the form, deduplicates requests and navigates on confirmed success', async t => {
  const f = await mount(t);
  assert.equal(f.root.dataset.state, 'ready');
  assert.equal(f.submit.disabled, false);
  f.submitForm(); f.submitForm();
  assert.equal(f.calls.length, 1); assert.equal(f.submit.disabled, true);
  const [url, options] = f.calls[0];
  assert.equal(url, '/access/login'); assert.equal(options.redirect, 'error');
  assert.equal(options.credentials, 'same-origin'); assert.equal(options.headers.Accept, 'application/json');
  assert.equal(options.body.get('password'), 'synthetic-browser-password');
  await f.respond(200, { authenticated: true, redirect: '/' });
  assert.deepEqual(f.destinations, ['/']); assert.equal(f.input.value, '');
  t.mock.timers.tick(1); assert.deepEqual(f.destinations, ['/']);
});

test('password rejection and retry leave the NPC idle and never wait for an animation', async t => {
  const f = await mount(t);
  f.submitForm(); await f.respond(401, { error: 'invalid_password' });
  assert.equal(f.root.dataset.state, 'rejected'); assert.equal(f.root.dataset.pose, undefined);
  assert.equal(f.desktop.paused, false);
  assert.equal(f.input.attributes['aria-invalid'], 'true'); assert.equal(f.input.selected, true);
  assert.equal(f.submit.disabled, false);
  f.submitForm(); await f.respond(200, { authenticated: true, redirect: '/' });
  assert.deepEqual(f.destinations, ['/']);
});

test('native failure messages persist; throttling, service, network and timeout failures recover distinctly', async t => {
  const f = await mount(t, { message: 'Incorrect password. Please try again.' });
  assert.equal(f.status.textContent, 'Incorrect password. Please try again.');
  f.submitForm(); await f.respond(429, { error: 'rate_limited' }, { 'Retry-After': '90' });
  assert.match(f.status.textContent, /2 minutes/);
  f.submitForm(); await f.respond(503, { error: 'unavailable' });
  assert.match(f.status.textContent, /temporarily unavailable/);
  f.submitForm(); f.pending.shift().reject(new TypeError('Network unavailable')); await settle();
  assert.match(f.status.textContent, /Check your connection/);
  f.submitForm(); t.mock.timers.tick(12000); await settle();
  assert.match(f.status.textContent, /connection took too long/);
  assert.equal(f.submit.disabled, false); assert.equal(f.input.readOnly, false);
});

test('visibility, reduced motion and portrait framing pause the actual SVG breeze and inactive scene', async t => {
  const f = await mount(t);
  assert.equal(f.desktop.paused, false); assert.equal(f.mobile.paused, true);
  f.portrait.matches = true; f.portrait.dispatchEvent(new Event('change'));
  assert.equal(f.desktop.paused, true); assert.equal(f.mobile.paused, false);
  f.document.hidden = true; f.document.dispatchEvent(new Event('visibilitychange'));
  assert.equal(f.mobile.paused, true); assert.equal(f.root.classes.has('paused'), true);
  f.document.hidden = false; f.document.dispatchEvent(new Event('visibilitychange'));
  assert.equal(f.mobile.paused, false);
  f.motion.matches = true; f.motion.dispatchEvent(new Event('change'));
  assert.equal(f.desktop.paused, true); assert.equal(f.mobile.paused, true);
  assert.equal(f.root.dataset.state, 'ready'); assert.equal(f.calls.length, 0);
});

test('reduced-motion visitors receive the form immediately with the scene paused', async t => {
  const f = await mount(t, { reduced: true });
  assert.equal(f.root.dataset.state, 'ready'); assert.equal(f.desktop.paused, true); assert.equal(f.mobile.paused, true);
});

test('signed-in access page pauses ambient effects correctly without a login form', async t => {
  const f = await mount(t, { signedIn: true });
  assert.equal(f.desktop.paused, false); assert.equal(f.calls.length, 0);
  f.document.hidden = true; f.document.dispatchEvent(new Event('visibilitychange'));
  assert.equal(f.desktop.paused, true);
});

test('page disposal aborts pending authentication, ignores stale results and restores a native form', async t => {
  const f = await mount(t); f.submitForm();
  const signal = f.calls[0][1].signal; f.window.dispatchEvent(new Event('pagehide'));
  assert.equal(signal.aborted, true); assert.equal(f.submit.disabled, false); assert.equal(f.input.readOnly, false);
  await settle(); assert.deepEqual(f.destinations, []);
});
