import assert from 'node:assert/strict';
import test from 'node:test';

import { ApiError, AuthRequiredError, api, setAuthRequiredHandler } from '../src/api/client.ts';

function respond(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

test('requests rely on the same-origin session cookie and send no Case token', async () => {
  const requests = [];
  globalThis.fetch = async (path, init) => {
    requests.push({ path, init });
    return respond(200, { data: { case_id: 'case-one', status: 'RECEIVED' } });
  };
  await api.caseData('case-one');
  assert.equal(requests[0].init.credentials, 'same-origin');
  assert.equal(requests[0].init.headers['X-Case-Token'], undefined);
});

test('creating a trip does not store any access token in the browser', async () => {
  const stored = [];
  globalThis.localStorage = { getItem: () => null, setItem: (key, value) => stored.push([key, value]) };
  globalThis.fetch = async () => respond(201, { data: { case_id: 'case-one', status: 'RECEIVED', role: 'OWNER' } });
  const created = await api.createCase('Auckland for three travelers', '2026-10-20');
  assert.equal(created.role, 'OWNER');
  assert.deepEqual(stored, []);
});

test('an expired session calls the sign-in handler and raises AuthRequiredError', async () => {
  let prompted = 0;
  setAuthRequiredHandler(() => { prompted += 1; });
  globalThis.fetch = async () => respond(401, { error: { code: 'AUTH_REQUIRED', message: 'Please sign in to continue.' } });
  await assert.rejects(api.cases(), AuthRequiredError);
  assert.equal(prompted, 1);
  setAuthRequiredHandler(null);
});

test('business errors keep the server code and message', async () => {
  globalThis.fetch = async () => respond(403, { error: { code: 'ROLE_FORBIDDEN', message: 'Your role on this trip does not allow this action.' } });
  const failure = await api.resume('case-one').catch(error => error);
  assert.ok(failure instanceof ApiError);
  assert.equal(failure.code, 'ROLE_FORBIDDEN');
  assert.equal(failure.status, 403);
  assert.match(failure.message, /role/);
});

test('a snapshot is one request for the selected Case', async () => {
  const paths = [];
  const body = { case: { case_id: 'first' }, offers: [], evidence: { sources: [], assessments: [] }, approval: null,
    orders: [], events: [] };
  globalThis.fetch = async path => { paths.push(path); return respond(200, { data: body }); };
  const snapshot = await api.snapshot('first');
  assert.deepEqual(paths, ['/api/cases/first/snapshot']);
  assert.equal(snapshot.caseData.case_id, 'first');
  assert.deepEqual(snapshot.offers, []);
  assert.equal('case' in snapshot, false);
});
