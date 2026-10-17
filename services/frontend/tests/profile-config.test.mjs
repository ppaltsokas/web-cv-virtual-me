import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { loadProfile, publicProfile, escapeHtml, interpolate } from '../profile-config.mjs';
import { accessPage } from '../access-page.js';

test('a different owner controls the entrance, page data and chat identity', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'profile-template-'));
  const previous = process.env.PORTFOLIO_PROFILE;
  try {
    const profile = loadProfile({ PORTFOLIO_PROFILE: 'config/profile.example.json' });
    profile.resume.personalInfo.name = 'Sam Rivera';
    profile.chat.name = 'Virtual Sam';
    profile.chat.greeting = 'Meet my fictional design portfolio.';
    profile.birthMonthYear = 'January 1990';
    const filename = path.join(directory, 'profile.json');
    fs.writeFileSync(filename, JSON.stringify(profile));
    process.env.PORTFOLIO_PROFILE = filename;
    const loaded = loadProfile();
    const serialized = JSON.stringify(publicProfile(loaded));
    assert.ok(serialized.includes('Virtual Sam'));
    assert.ok(!serialized.includes('birthMonthYear'));
    assert.ok(!serialized.includes('January 1990'));
    assert.ok(!serialized.includes('voice'));
    assert.ok(accessPage().includes('Sam Rivera'));
    assert.ok(!accessPage().includes('Alex Morgan'));
  } finally {
    if (previous === undefined) delete process.env.PORTFOLIO_PROFILE;
    else process.env.PORTFOLIO_PROFILE = previous;
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test('HTML title text is escaped and unsafe social links are rejected', () => {
  assert.equal(escapeHtml(interpolate('Welcome {name}', '<script>alert(1)</script>')), 'Welcome &lt;script&gt;alert(1)&lt;/script&gt;');
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'profile-validation-'));
  try {
    const profile = loadProfile({ PORTFOLIO_PROFILE: 'config/profile.example.json' });
    profile.resume.personalInfo.socials.github = 'javascript:alert(1)';
    const filename = path.join(directory, 'profile.json');
    fs.writeFileSync(filename, JSON.stringify(profile));
    assert.throws(() => loadProfile({ PORTFOLIO_PROFILE: filename }), /HTTPS/);
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});
