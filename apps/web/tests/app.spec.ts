import { expect, test } from '@playwright/test';

const workId = '11111111-1111-4111-8111-111111111111';
const eventId = '22222222-2222-4222-8222-222222222222';
const event = { id: eventId, work_id: workId, work_title: 'Fixture story', work_kind: 'anime', franchise_id: null, kind: 'release', title: 'A release window', summary: 'A source has announced a year.', verification: 'reported', lifecycle: 'scheduled', precision: 'year', date_label: '2027', scheduled_at: null, window_start: '2027-01-01', window_end: '2027-12-31', source_timezone: '', region: 'JP', platform: '', language: 'ja', published_at: '2026-10-01T10:00:00Z', observed_at: '2026-10-02T10:00:00Z', provider: 'fixture', evidence_count: 1, personal: false };

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    let body: unknown = {};
    if (url.pathname === '/api/auth/login') body = { token: 'test-token', user: { id: 1, username: 'fixture', is_staff: false } };
    else if (url.pathname === '/api/auth/me') body = { id: 1, username: 'fixture', is_staff: false };
    else if (url.pathname === '/api/stats') body = { followed: 1, upcoming: 1, needs_review: 0, stale_sources: 0 };
    else if (url.pathname === '/api/timeline') body = { events: url.searchParams.get('tba_only') === 'true' ? [] : [event], total: url.searchParams.get('tba_only') === 'true' ? 0 : 1, tba_count: 0, offset: 0, limit: 60 };
    else if (url.pathname === `/api/events/${eventId}`) body = { event, evidence: [{ id: 'evidence', url: 'https://bgm.tv/subject/1', provider: 'fixture', title: 'Original announcement', locator: 'release field', original_text: 'Releasing in 2027.', published_at: event.published_at, observed_at: event.observed_at }], revisions: [] };
    else if (['/api/filters', '/api/library', '/api/review', '/api/franchises'].includes(url.pathname)) body = [];
    else if (url.pathname === '/api/search') body = { candidates: [{ provider: 'bangumi', namespace: 'subject', external_id: '1', title: 'Fixture story', kind: 'anime', creators: ['Author A'] }, { provider: 'ndl', namespace: 'book', external_id: '2', title: 'Fixture story', kind: 'light_novel', creators: ['Author A'] }], errors: [] };
    else if (url.pathname === '/api/catalogue/import') body = { id: 'run', work_id: workId, provider: 'bangumi', status: 'succeeded', message: 'Imported', created_at: event.observed_at, finished_at: event.observed_at };
    else if (url.pathname === `/api/works/${workId}`) body = { work: { id: workId, title: 'Fixture story', original_title: 'Fixture story', kind: 'anime', aliases: [], creators: ['Author A'], summary: '', status: '', language: 'ja', canonical_url: '', image_url: '', identities: [], franchise_id: null, franchise_title: null, unit_count: 0, metadata: {} }, units: [], editions: [], relationships: [] };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
});

async function login(page: import('@playwright/test').Page) {
  await page.goto('/#/login');
  await page.getByLabel('Username', { exact: true }).fill('fixture');
  await page.getByLabel('Password', { exact: true }).fill('fixture-password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your next chapter' })).toBeVisible();
}

test('timeline keeps partial dates and exposes source evidence', async ({ page }) => {
  await login(page);
  const card = page.getByRole('button', { name: /Fixture story.*A release window/ });
  await expect(card).toContainText('2027');
  await expect(card).not.toContainText('January');
  await card.click();
  await expect(page.getByRole('heading', { name: 'Source evidence' })).toBeVisible();
  await expect(page.getByText('Releasing in 2027.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Close evidence' }).click();
});

test('search requires an explicit candidate choice for ambiguous titles', async ({ page }) => {
  await login(page);
  await page.getByRole('button', { name: 'Follow a story', exact: true }).click();
  await page.getByLabel('Title, work URL, ISBN, or provider ID').fill('Fixture story');
  await page.getByRole('button', { name: 'Search catalogues' }).click();
  const choices = page.locator('.search-result');
  await expect(choices).toHaveCount(2);
  await expect(choices.nth(0)).toContainText('Anime');
  await expect(choices.nth(1)).toContainText('Light novel');
  await choices.nth(0).click();
  await expect(page).toHaveURL(new RegExp('/works/' + workId));
});

test('mobile agenda fits the viewport and navigation stays reachable', async ({ page, isMobile }) => {
  await login(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  if (isMobile) {
    await page.getByRole('button', { name: 'Open navigation' }).click();
    await page.getByRole('link', { name: 'My library', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Your collection of stories' })).toBeVisible();
  }
});
