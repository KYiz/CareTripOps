import { expect, test, type Page } from '@playwright/test';
import { expectAccessible, origin, signInQuietly } from './helpers';

/** A booked Auckland trip created through the API, as the signed-in traveler. */
async function bookedTrip(page: Page) {
  await signInQuietly(page);
  const headers = { Origin: origin() };
  const created = await page.request.post('/api/cases', { headers, data: {
    request: 'Three travelers want a relaxed three-day Auckland trip with a lift. Budget NZD 1000.',
    demo_date: new Date(Date.now() + 10 * 86400000).toISOString().slice(0, 10) } });
  const caseId = (await created.json()).data.case_id as string;
  await expect.poll(async () => (await (await page.request.get(`/api/cases/${caseId}`)).json()).data.status,
    { timeout: 30_000 }).toBe('AWAITING_APPROVAL');
  const approval = (await (await page.request.get(`/api/cases/${caseId}/approvals`)).json()).data;
  await page.request.post(`/api/cases/${caseId}/approvals/${approval.approval_id}/decision`, { headers, data: {
    decision: 'APPROVE', nonce: approval.nonce, expected_state_version: approval.case_state_version } });
  await expect.poll(async () => (await (await page.request.get(`/api/cases/${caseId}`)).json()).data.status,
    { timeout: 30_000 }).toBe('BOOKED');
  return caseId;
}

test('the trip card is large-print, complete and accessible', async ({ page }) => {
  const caseId = await bookedTrip(page);
  await page.goto(`/trip-card?caseId=${caseId}`);
  await expect(page.getByRole('heading', { level: 1, name: 'Auckland' })).toBeVisible();
  await expect(page.getByText('Waterfront Accessible Suites')).toBeVisible();
  await expect(page.getByText('Emergency: 111')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Print this card' })).toBeVisible();
  await expectAccessible(page);
});

test('help reaches the advisor console', async ({ page }) => {
  const caseId = await bookedTrip(page);
  await page.goto(`/mobile?caseId=${caseId}`);
  await page.getByRole('navigation', { name: 'Traveler pages' }).getByRole('button', { name: 'Help' }).click();
  await expect(page.getByRole('link', { name: 'Call 111' })).toHaveAttribute('href', 'tel:111');
  const message = `Lost my glasses ${Date.now()}`;
  await page.getByLabel('What is happening? (optional)').fill(message);
  await page.getByRole('button', { name: 'I need help now' }).click();
  await expect(page.getByText('Your family and the CareTrip team have been told.', { exact: false })).toBeVisible();
  await expectAccessible(page);

  const advisor = process.env.E2E_ADVISOR_EMAIL;
  test.skip(!advisor, 'Set ADVISOR_EMAILS on the API and E2E_ADVISOR_EMAIL here to check the advisor console.');
  await page.context().clearCookies();
  await signInQuietly(page, advisor);
  await page.goto('/advisor');
  const card = page.locator('article', { hasText: message });
  await expect(card).toBeVisible();
  await expectAccessible(page);
  await card.getByLabel('What did you do?').fill('Called the traveler; glasses found at reception.');
  await card.getByRole('button', { name: 'I have contacted them' }).click();
  await expect(card).toHaveCount(0);
  await page.getByRole('button', { name: 'Trips' }).click();
  await expect(page.getByRole('heading', { name: 'Trips' })).toBeVisible();
  await expectAccessible(page);
});

test('the guide cites its sources and the traveler can rewrite the outline', async ({ page }) => {
  const caseId = await bookedTrip(page);
  await page.goto(`/mobile?caseId=${caseId}`);
  await page.getByRole('navigation', { name: 'Traveler pages' }).getByRole('button', { name: 'AI Guide' }).click();
  await page.getByRole('button', { name: 'Is my stay step-free?' }).click();
  const sources = page.locator('.ct-guide-sources');
  await expect(sources).toContainText('Evidence');
  await expect(sources.getByRole('link').first()).toHaveAttribute('href', /supplier\.example\/evidence/);

  await page.getByRole('button', { name: 'Edit the outline' }).click();
  await page.getByLabel('Title').first().fill('A slow harbour morning');
  await page.getByRole('button', { name: 'Save my outline' }).click();
  const journey = page.getByRole('region', { name: 'Illustrative journey map' });
  await expect(journey.getByText('A slow harbour morning')).toBeVisible();
  await expect(journey.getByText('Edited by you or your family')).toBeVisible();
  await expectAccessible(page);
});
