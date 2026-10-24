const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const root = path.resolve(__dirname, '..');
  const server = http.createServer((req, res) => {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    const file = path.join(root, pathname === '/' ? 'index.html' : pathname);
    if (!fs.existsSync(file)) {res.writeHead(404); res.end(); return;}
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.svg') ? 'image/svg+xml' : 'text/html');
    res.end(fs.readFileSync(file));
  }).listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  const browser = await chromium.launch({channel: 'chrome', headless: true});
  try {
    for (const [width, scheme] of [[390, 'light'], [1440, 'light'], [390, 'dark'], [1440, 'dark']]) {
      const context = await browser.newContext({viewport: {width, height: 900}, reducedMotion: 'reduce', colorScheme: scheme});
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const now = Date.now();
      const at = hours => new Date(now - hours * 3600000).toISOString();
      const item = (id, extra = {}) => ({id, kind: 'card', card_id: null, owner: 'ted', next_action_due: at(-1), action_started_at: at(1), status: 'open', stage: 'review', priority: 1, summary: id, ...extra});
      const malicious = '<img src=x onerror="window.injected=true">';
      let reconciliation = {generated_at: at(0), items: [item('new'), item('old', {action_started_at: at(13), next_action_due: at(2)}), item('broken', {owner: null, next_action_due: null, action_started_at: null, summary: malicious}), item('dead', {owner: 'external', status: 'dead_letter'})], ted_queue: ['new', 'old'], banner: null};
      let waitForOld = false, releaseOld, oldStarted;
      let started = new Promise(resolve => {oldStarted = resolve;});
      const oldGate = new Promise(resolve => {releaseOld = resolve;});
      await context.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.origin === 'http://127.0.0.1:' + server.address().port) return route.continue();
        if (url.pathname.endsWith('/ted-mockups')) return route.fulfill({json: {mockups: [], pins: []}});
        if (!url.pathname.endsWith('/ted-board')) return route.abort();
        const cardKey = url.searchParams.get('key');
        if (url.searchParams.get('resource') === 'control') return route.fulfill({json: {vetoes: [], rules: [], server_time: at(0)}});
        if (url.searchParams.get('resource') !== 'jobs') return route.fulfill({json: {cards: cardKey === 'fixture-b' ? [] : [{id: 'fallback', title: 'Fallback card', project: 'Test', section: 'up_next', body: '', options: [], steps: [], updated_at: at(0)}], pod_pulse: []}});
        if (cardKey === 'fixture-b') return route.fulfill({json: {jobs: [], approvals: []}});
        const result = {jobs: [], approvals: [], reconciliation};
        if (waitForOld) {oldStarted(); await oldGate;}
        return route.fulfill({json: result});
      });
      await page.goto('http://127.0.0.1:' + server.address().port + '/#k=fixture-a&tab=Jobs');
      await page.waitForFunction(() => state.jobsLoaded);
      assert.equal(await page.locator('.aging-wip').count(), 1, 'Jobs must include the open-work ledger');
      assert.equal(await page.locator('.aging-table tbody tr').count(), 4);
      assert.deepEqual(await page.locator('.aging-review-list li').evaluateAll(rows => rows.map(row => row.dataset.reviewId)), ['old', 'new']);
      assert.match(await page.locator('.aging-reviews').innerText(), /6 hours/);
      assert.match(await page.locator('[data-aging-id="old"]').innerText(), /Overdue by 2h/);
      assert.match(await page.locator('[data-aging-id="broken"]').innerText(), /Unknown owner.*Unknown action age.*Unknown deadline/s);
      assert.equal(await page.locator('.aging-table img').count(), 0);
      const contrast = await page.locator('.aging-due-overdue').evaluate(node => {
        const luminance = value => {
          const rgb = value.match(/[\d.]+/g).slice(0, 3).map(Number).map(channel => {const c = channel / 255; return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4;});
          return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
        };
        const foreground = luminance(getComputedStyle(node).color), background = luminance(getComputedStyle(document.body).backgroundColor);
        return (Math.max(foreground, background) + .05) / (Math.min(foreground, background) + .05);
      });
      assert.ok(contrast >= 4.5, 'Overdue text must have WCAG AA contrast');
      assert.equal(await page.evaluate(() => Boolean(window.injected)), false);
      assert.equal(await page.locator('#aging-banner').isVisible(), true);
      if (process.env.QA_OUT) await page.screenshot({path: path.join(process.env.QA_OUT, 'aging-wip-' + width + '-' + scheme + '.png'), fullPage: true});
      await page.evaluate(() => selectProject('inbox'));
      assert.equal(await page.locator('#aging-banner').isVisible(), true, '12-hour banner must be visible outside Jobs');
      await page.evaluate(() => selectProject('Jobs'));
      await page.waitForFunction(() => !state.jobsLoading);
      reconciliation = {...reconciliation, generated_at: at(1)};
      await page.evaluate(() => loadJobs());
      assert.match(await page.locator('.aging-warnings').innerText(), /Reconciliation is stale/);
      reconciliation = {generated_at: at(0), items: [], ted_queue: [], coverage_defects: ['sessions', 'github']};
      await page.evaluate(() => loadJobs());
      assert.match(await page.locator('.aging-warnings').innerText(), /Incomplete reconciliation coverage.*sessions.*github/);
      assert.match(await page.locator('.aging-wip').innerText(), /Coverage has not been confirmed/);
      assert.doesNotMatch(await page.locator('.aging-wip').innerText(), /No open work in the current reconciliation/);
      reconciliation = undefined;
      await page.evaluate(() => loadJobs());
      assert.match(await page.locator('.aging-warnings').innerText(), /coverage is unknown/);
      assert.equal(await page.locator('[data-aging-id="card:fallback"]').count(), 1);
      assert.match(await page.locator('[data-aging-id="card:fallback"]').innerText(), /Unknown owner/);
      reconciliation = {generated_at: at(0), items: [item('account-a-private', {action_started_at: at(13)})], ted_queue: []};
      await page.evaluate(() => loadJobs());
      waitForOld = true;
      await page.evaluate(() => {void loadJobs();});
      await started;
      await page.evaluate(() => {key = 'fixture-b'; resetForKeyChange(); render(); void load();});
      assert.equal(await page.locator('#aging-banner').isVisible(), false, 'Access reset must clear the previous banner immediately');
      releaseOld();
      await page.waitForFunction(() => state.loaded && state.jobsLoaded);
      assert.equal(await page.locator('[data-aging-id="account-a-private"]').count(), 0);
      assert.equal(await page.evaluate(() => state.reconciliation), null);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      assert.deepEqual(errors, []);
      await context.close();
    }
    console.log('PASS Google Chrome ' + browser.version() + ': aging WIP, review SLA, global banner, metadata defects, legacy fallback, safe text, key isolation, and mobile and desktop layout');
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
