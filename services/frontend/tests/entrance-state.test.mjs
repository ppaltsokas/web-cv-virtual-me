import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createEntranceState, classifyLogin } from '../public/entrance/state.js';

test('form is immediately ready and never waits for artwork or an introduction', () => {
  const machine = createEntranceState();
  assert.equal(machine.snapshot.phase, 'loading');
  assert.equal(machine.send({ type: 'BOOT' }).phase, 'ready');
  assert.equal(machine.snapshot.attempt, 0);
  assert.equal(machine.snapshot.pose, undefined);
});

test('duplicate submissions and stale results cannot authenticate a visitor', () => {
  const machine = createEntranceState();
  machine.send({ type: 'BOOT' });
  const attempt = machine.send({ type: 'SUBMIT' }).attempt;
  assert.equal(machine.send({ type: 'SUBMIT' }).attempt, attempt);
  assert.equal(machine.send({ type: 'RESULT', attempt: attempt - 1, outcome: 'success' }).phase, 'submitting');
  assert.equal(machine.send({ type: 'RESULT', attempt, ...classifyLogin(503) }).phase, 'service-error');
  assert.equal(machine.send({ type: 'SUBMIT' }).attempt, attempt + 1);
  assert.equal(machine.send({ type: 'RESULT', attempt, outcome: 'success' }).phase, 'submitting');
  assert.equal(machine.send({ type: 'RESULT', attempt: attempt + 1, ...classifyLogin(401, { error: 'invalid_password' }) }).phase, 'rejected');
  assert.equal(machine.snapshot.pose, undefined);
});

test('only explicit authentication success navigates, immediately and without an NPC reaction', () => {
  const machine = createEntranceState();
  machine.send({ type: 'BOOT' }); machine.send({ type: 'SUBMIT' });
  const result = classifyLogin(200, { authenticated: true, redirect: '/' });
  assert.equal(machine.send({ type: 'RESULT', attempt: 1, ...result }).phase, 'navigating');
  assert.equal(machine.snapshot.pose, undefined);
});

test('redirects, malformed success, rate limits and service errors never masquerade as wrong passwords', () => {
  for (const [status, body] of [[200, {}], [200, { authenticated: true, redirect: 'https://attacker.invalid' }], [303, {}], [401, {}], [403, {}], [413, {}], [415, {}], [429, {}], [503, {}]]) {
    assert.equal(classifyLogin(status, body, '90').outcome, 'error');
  }
  assert.match(classifyLogin(429, {}, '90').message, /2 minutes/);
  assert.match(classifyLogin(503).message, /temporarily unavailable/);
  assert.notEqual(classifyLogin(429).message, classifyLogin(403).message);
});
