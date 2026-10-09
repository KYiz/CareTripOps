import assert from 'node:assert/strict';
import test from 'node:test';

import { api, caseAccessToken } from '../src/api/client.ts';

function installStorage() {
  const values = new Map();
  globalThis.localStorage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
  return values;
}

test('a new Case token is saved and reused for case reads after a reload', async () => {
  const values = installStorage();
  const requests = [];
  globalThis.fetch = async (path, init) => {
    requests.push({ path, init });
    return { ok: true, status: path === '/api/cases' ? 201 : 200,
      json: async () => ({ data: path === '/api/cases'
        ? { case_id: 'case-one', status: 'RECEIVED', access_token: 'secret-token' }
        : { case_id: 'case-one', status: 'RECEIVED' } }) };
  };
  await api.createCase('Auckland for three travelers', '2026-10-20');
  assert.equal(values.get('caretrip:access:case-one'), 'secret-token');
  const reloaded = await import('../src/api/client.ts?reload=1');
  await reloaded.api.caseData('case-one');
  assert.equal(requests[1].init.headers['X-Case-Token'], 'secret-token');
  assert.equal(caseAccessToken('case-one'), 'secret-token');
});

test('an old Case without a saved token tells the traveler to create a new trip', async () => {
  installStorage();
  globalThis.fetch = async () => ({ ok: false, status: 403,
    json: async () => ({ error: { code: 'CASE_ACCESS_DENIED' } }) });
  await assert.rejects(api.caseData('old-case'), /before secure access.*start a new trip/i);
});

test('snapshot requests use only the selected Case token', async () => {
  const values = installStorage();
  values.set('caretrip:access:first', 'first-token');
  values.set('caretrip:access:second', 'second-token');
  const requests = [];
  globalThis.fetch = async (path, init) => {
    requests.push({ path, token: init.headers['X-Case-Token'] });
    return { ok: true, status: 200, json: async () => ({ data: null }) };
  };
  await api.snapshot('first');
  await api.snapshot('second');
  assert.equal(requests.length, 12);
  assert.ok(requests.slice(0, 6).every(item => item.path.includes('/first') && item.token === 'first-token'));
  assert.ok(requests.slice(6).every(item => item.path.includes('/second') && item.token === 'second-token'));
});
