import { expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

export const origin = () => new URL(process.env.BASE_URL ?? 'http://localhost:8080').origin;
export const newEmail = () => `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;

/** Development returns the code in the response, so no mailbox is needed. Cookies land in the page's context. */
export async function signInQuietly(page: Page, email = newEmail()) {
  const headers = { Origin: origin() };
  const sent = await page.request.post('/api/auth/request-code', { data: { email }, headers });
  expect(sent.status()).toBe(202);
  const code = (await sent.json()).data.dev_code;
  const verified = await page.request.post('/api/auth/verify', { data: { email, code, accept_terms: true }, headers });
  expect(verified.status()).toBe(200);
  return email;
}

export function preferChinese(page: Page) {
  return page.addInitScript(() => localStorage.setItem('caretrip:lang-choice', 'zh'));
}

/** WCAG 2.1 A and AA rules; any violation fails with the rule IDs and the elements involved. */
export async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
  const problems = results.violations.map(v => `${v.id} (${v.impact}): ${v.nodes.map(n => n.target.join(' ')).join(', ')}`);
  expect(problems, problems.join('\n')).toEqual([]);
}
