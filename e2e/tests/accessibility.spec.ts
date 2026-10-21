import { expect, test } from '@playwright/test';
import { expectAccessible, origin, preferChinese, signInQuietly } from './helpers';

const PUBLIC_PAGES = ['/', '/terms', '/privacy'];
const SIGNED_IN_PAGES = ['/account', '/dashboard', '/mobile', '/demo'];

for (const lang of ['en', 'zh'] as const) {
  test.describe(`${lang} pages`, () => {
    test.beforeEach(async ({ page }) => { if (lang === 'zh') await preferChinese(page); });

    for (const path of PUBLIC_PAGES) {
      test(`${path} meets WCAG 2.1 AA`, async ({ page }) => {
        await page.goto(path);
        await expect(page.locator('main')).toBeVisible();
        await expectAccessible(page);
      });
    }

    test('the sign-in page meets WCAG 2.1 AA', async ({ page }) => {
      await page.goto('/account');
      await expect(page.locator('#auth-email')).toBeVisible();
      await expectAccessible(page);
    });

    test('signed-in pages meet WCAG 2.1 AA', async ({ page }) => {
      await signInQuietly(page);
      // With consent given, the account page shows the full travel-needs form.
      await page.request.put('/api/auth/me/consent', { data: { granted: true }, headers: { Origin: origin() } });
      for (const path of SIGNED_IN_PAGES) {
        await page.goto(path);
        await expect(page.locator('main').first()).toBeVisible();
        await expectAccessible(page);
      }
    });
  });
}
