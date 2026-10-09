import assert from 'node:assert/strict';
import test from 'node:test';
import { resolveRoute, routeHref } from '../src/routes.ts';

test('all four direct entry paths resolve within one SPA', () => {
  for (const path of ['/', '/dashboard', '/mobile', '/demo']) assert.equal(resolveRoute(path), path);
  assert.equal(resolveRoute('/mobile/'), '/mobile');
  assert.equal(resolveRoute('/unavailable'), null);
});

test('a case link carries the same case ID between views', () => {
  assert.equal(routeHref('/mobile', 'case-123'), '/mobile?caseId=case-123');
  assert.equal(routeHref('/demo', ''), '/demo');
});
