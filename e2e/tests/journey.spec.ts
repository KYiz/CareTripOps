import { expect, test } from '@playwright/test';
import { newEmail, origin, signInQuietly } from './helpers';

test('a new traveler accepts the terms, plans, approves and cancels a trip', async ({ page }) => {
  await page.goto('/account');
  await page.getByLabel('Your email address').fill(newEmail());
  await page.getByRole('button', { name: 'Email me a code' }).click();
  const code = await page.locator('.ct-auth-dev strong').textContent();
  await page.getByLabel('6-digit code').fill(code ?? '');
  await page.getByRole('button', { name: 'Sign in' }).click();
  // First sign-in asks for the terms, and the button waits for the tick.
  const agree = page.getByRole('button', { name: 'Agree and sign in' });
  await expect(agree).toBeDisabled();
  await page.getByRole('checkbox', { name: /I have read and accept/ }).check();
  await agree.click();
  await expect(page.getByRole('heading', { name: 'Account and privacy' })).toBeVisible();

  await page.goto('/mobile');
  await page.getByRole('button', { name: 'Plan this trip →' }).first().click();
  await page.getByRole('button', { name: /Review and approve/ }).click();
  await page.getByRole('button', { name: /^Approve NZD/ }).click();
  await expect(page.getByRole('heading', { name: 'Your trip is booked' })).toBeVisible({ timeout: 30_000 });

  await page.getByRole('button', { name: 'Cancel this booking' }).click();
  await page.getByRole('button', { name: 'Yes, cancel the booking' }).click();
  await expect(page.locator('strong', { hasText: 'Booking cancelled' })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/^Refund: NZD/)).toBeVisible();
});

test('the language choice switches the page and is remembered', async ({ page }) => {
  await page.goto('/terms');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Terms of Use');
  await page.getByRole('button', { name: '切换到中文' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('使用条款');
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-Hans');
  await page.reload();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('使用条款');
  await page.getByRole('button', { name: 'Switch to English' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Terms of Use');
});

test('a wheelchair user gets a verified Queenstown stay from the supplier service', async ({ page }) => {
  await signInQuietly(page);
  const headers = { Origin: origin() };
  await page.request.put('/api/auth/me/consent', { data: { granted: true }, headers });
  await page.request.put('/api/profile', { headers, data: { needs: { wheelchair: 'MANUAL', accessible_bathroom: true, dietary: ['VEGAN'] } } });
  const created = await page.request.post('/api/cases', { headers, data: {
    request: 'Three travelers want a relaxed three-day trip to Queenstown. Our total budget is NZD 1000.',
    demo_date: new Date(Date.now() + 10 * 86400000).toISOString().slice(0, 10) } });
  const caseId = (await created.json()).data.case_id;
  await page.goto(`/mobile?caseId=${caseId}`);
  await expect(page.getByRole('heading', { name: 'Lakefront Lodge on Lake Wakatipu' })).toBeVisible({ timeout: 30_000 });
  const access = page.getByRole('list', { name: 'Access at this stay' });
  await expect(access.getByText('Accessible bathroom')).toBeVisible();
  await expect(access.getByText('Accessible airport transfer')).toBeVisible();
  await page.goto(`/dashboard?caseId=${caseId}`);
  await expect(page.getByText('Manual wheelchair')).toBeVisible();
});

test('a traveler adds a mobile number and then signs in by text message', async ({ page }) => {
  await signInQuietly(page);
  const mobile = `021 ${100 + Math.floor(Math.random() * 900)} ${1000 + Math.floor(Math.random() * 9000)}`;
  await page.goto('/account');
  await page.getByLabel('Your mobile number').fill(mobile);
  await page.getByRole('button', { name: 'Text me a code' }).click();
  const code = await page.locator('#phone-title ~ form .ct-auth-dev strong').textContent();
  await page.getByLabel('6-digit code').fill(code ?? '');
  await page.getByRole('button', { name: 'Confirm this number' }).click();
  await expect(page.getByText(/Codes can also be texted to \+64/)).toBeVisible();

  await page.getByRole('button', { name: 'Sign out' }).click();
  await page.goto('/account');
  await page.getByRole('button', { name: 'Use my mobile number instead' }).click();
  await page.getByLabel('Your mobile number').fill(mobile);
  await page.getByRole('button', { name: 'Text me a code' }).click();
  await expect(page.getByRole('heading', { name: 'Check your text messages' })).toBeVisible();
  await page.getByLabel('6-digit code').fill(await page.locator('.ct-auth-dev strong').textContent() ?? '');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Account and privacy' })).toBeVisible();
});
