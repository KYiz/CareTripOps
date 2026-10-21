import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';

import { translate } from '../src/language.ts';
import { zh } from '../src/locales/zh.ts';

function sourceFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap(entry => entry.isDirectory()
    ? sourceFiles(join(dir, entry.name)) : /\.(tsx|ts)$/.test(entry.name) ? [join(dir, entry.name)] : []);
}

// Every literal passed to t('…') or t("…"), plus English labels that are translated through t(variable).
function translatedKeys() {
  const keys = new Set();
  for (const file of sourceFiles(new URL('../src', import.meta.url).pathname)) {
    const source = readFileSync(file, 'utf8');
    for (const match of source.matchAll(/\bt\(\s*(['"])((?:\\.|(?!\1).)*)\1/g)) keys.add(match[2].replace(/\\(['"\\])/g, '$1'));
  }
  return keys;
}

test('every t() literal in the UI has a Chinese translation', () => {
  const missing = [...translatedKeys()].filter(key => !(key in zh));
  assert.deepEqual(missing, [], `Add Chinese for:\n${missing.join('\n')}`);
});

test('labels translated through variables have Chinese too', async () => {
  const labels = await import('../src/labels.ts');
  const statuses = ['RECEIVED', 'NEEDS_CLARIFICATION', 'REQUIREMENTS_READY', 'OFFERS_DISCOVERED', 'EVIDENCE_REVIEW',
    'EVIDENCE_CONFLICT', 'OFFERS_VERIFIED', 'AWAITING_REVIEW', 'AWAITING_APPROVAL', 'APPROVED', 'AWAITING_PAYMENT',
    'REJECTED', 'BOOKING', 'BOOKED', 'CANCELLED', 'HUMAN_REVIEW', 'FAILED', 'RECOVERY_REQUIRED'];
  const fields = ['destination', 'departure_date', 'traveler_count', 'duration_days', 'budget', 'currency'];
  const friendly = [undefined, ...statuses].flatMap(status => [labels.friendlyStatus(status), labels.friendlyStatus(status, 'running')]);
  const variable = [...statuses.map(labels.statusLabel), ...fields.map(labels.fieldLabel), ...friendly,
    'Traveler', 'Helps plan', 'Can view', 'Travel advisor', 'Can add trip details and use the guide. Cannot approve or pay.',
    'Can see the trip and its progress only.', 'LOW', 'MODERATE', 'PENDING', 'ACCEPTED', 'DECLINED', 'SUPERSEDED',
    'Idle', 'Thinking', 'Connecting', 'Listening', 'Speaking', 'Disconnected',
    'All journeys', 'Relaxing Getaways', 'Scenic Journeys', 'Nature & Gardens', 'Cultural Discovery', 'Family Holidays',
    'Accessible Experiences',
    ...Object.values(labels.FAILURE_REASONS), ...Object.values(labels.FACTOR_REASONS),
    ...Object.values(labels.CLAIM_LABELS),
    ...labels.needsPhrases({ wheelchair: 'SOMETIMES', step_free: true, accessible_bathroom: true, max_walk_meters: 100,
      dietary: ['VEGETARIAN', 'VEGAN', 'GLUTEN_FREE', 'HALAL', 'KOSHER', 'DIABETIC', 'LOW_SODIUM', 'NUT_ALLERGY', 'SOFT_FOOD'] }).map(need => need.key),
    ...['MANUAL', 'POWER'].flatMap(wheelchair => labels.needsPhrases({ wheelchair }).map(need => need.key)),
    'Gemini planning in progress', 'Gemini reviewed', 'Gemini unavailable; local outline', 'Local outline', 'Edited by you or your family',
    'Gemini Planner and Reviewer generated this outline.', 'Gemini planning failed; this local outline needs further review.',
    'The traveler or their family edited this outline. It has not been checked.', 'Local rule-based outline. No model itinerary was generated.',
    'Meets all your access needs', 'Meals suit your diet', 'Accessible bathroom', 'Accessible airport transfer',
    ...[[], [{ days_before: 7, refund_percent: 100 }, { days_before: 2, refund_percent: 50 }]].flatMap(policy => labels.policyLines(policy).map(line => line.key)),
    // BookingPanel passes these through t() as values.
    'Generous free-cancellation terms', 'Highly rated by guests', 'Yes', 'No', 'Not confirmed',
    'Lift to every guest floor', 'Step-free entrance', 'Little walking needed', 'Something went wrong with the booking.',
    'Saved. The trip is planning again with your decision.', 'Saved.'];
  // Destination descriptions and experience titles are data in LandingPage, shown through t(value).
  const landing = readFileSync(new URL('../src/components/LandingPage.tsx', import.meta.url), 'utf8');
  for (const match of landing.matchAll(/\b(?:description|title): '((?:\\.|[^'])*)'/g)) variable.push(match[1]);
  const missing = [...new Set(variable)].filter(key => !(key in zh));
  assert.deepEqual(missing, [], `Add Chinese for:\n${missing.join('\n')}`);
});

test('every server error code has readable Chinese text', async () => {
  const { ERROR_TEXT } = await import('../src/api/client.ts');
  const missing = Object.values(ERROR_TEXT).filter(text => !(text in zh));
  assert.deepEqual(missing, []);
});

test('placeholders survive translation', () => {
  for (const [english, chinese] of Object.entries(zh)) {
    const names = text => [...text.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort();
    assert.deepEqual(names(chinese), names(english), `Placeholder mismatch for "${english}"`);
  }
  assert.equal(translate('zh', 'Case {id}', { id: 'abc' }), translate('zh', 'Case {id}').replace('{id}', 'abc'));
  assert.equal(translate('en', 'Not in the dictionary {x}', { x: 1 }), 'Not in the dictionary 1');
});
