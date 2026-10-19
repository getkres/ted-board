/* Run with node tests/gallery-position-ui.cjs. Every remote request is intercepted. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const os = require('node:os');
function playwright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, 'playwright'].filter(Boolean);
  const cache = path.join(os.homedir(), '.npm', '_npx');
  if (fs.existsSync(cache)) for (const dir of fs.readdirSync(cache)) candidates.push(path.join(cache, dir, 'node_modules', 'playwright'));
  for (const name of candidates) { try { return require(name); } catch {} }
  throw Error('Install playwright, or set PLAYWRIGHT_MODULE to its module directory.');
}
const {chromium} = playwright(), root = process.env.ROOT || path.resolve(__dirname, '..');
const uuid = n => '00000000-0000-4000-8000-' + String(n).padStart(12, '0');
const clone = v => JSON.parse(JSON.stringify(v));
const now = Date.now(), day = 86400000;
const image = (n, extra = {}) => ({id: uuid(n), project: 'Bookish', batch: 'test-shared batch', title: 'test-screen ' + n,
  status: 'open', verdict: null, sort: n, width: 800, height: 1000, created_at: new Date(now - n * 1000).toISOString(),
  preview_url: 'https://image.test/' + n, full_url: 'https://image.test/full-' + n, full_width: 1600, full_height: 2000, ...extra});
function fixtures() {
  return [...Array.from({length: 8}, (_, i) => image(i + 1)),
    ...Array.from({length: 8}, (_, i) => image(i + 21, {verdict: 'scrapped'})),
    ...Array.from({length: 8}, (_, i) => image(i + 41, {status: 'picked', verdict: 'approved', verdict_change: {at: new Date(now - 2 * day).toISOString()}})),
    ...Array.from({length: 8}, (_, i) => image(i + 61, {project: 'Fictora'})),
    ...Array.from({length: 8}, (_, i) => image(i + 81, {batch: 'test-second batch'}))];
}
const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1000"><rect width="800" height="1000" fill="#193548"/></svg>';
let server, browser, passes = 0, failures = [];
async function scenario(name, mobile, run, setup = {}) {
  if (process.env.SCENARIO && !name.includes(process.env.SCENARIO)) return;
  const ctx = await browser.newContext({viewport: mobile ? {width: 390, height: 844} : {width: 1440, height: 1000}, isMobile: mobile, hasTouch: mobile, reducedMotion: 'reduce'});
  const page = await ctx.newPage(), errors = [], unexpected = [], posts = [];
  page.setDefaultTimeout(6000);
  page.on('pageerror', e => errors.push(e.message));
  const state = {images: fixtures(), pins: [], delay: 40, fail: false, ...setup};
  await page.clock.install({time: now});
  await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.hostname === '127.0.0.1') return route.continue();
    if (url.hostname === 'image.test') return route.fulfill({body: svg, contentType: 'image/svg+xml'});
    if (url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') return route.fulfill({body: '', contentType: 'text/css'});
    if (url.pathname.endsWith('/ted-board')) return route.fulfill({json: url.searchParams.has('resource') ? {jobs: [], approvals: []} : {cards: []}});
    if (!url.pathname.endsWith('/ted-mockups')) { unexpected.push(request.url()); return route.abort(); }
    if (request.method() === 'GET') return route.fulfill({json: {mockups: state.images, pins: state.pins, verdicts_enabled: true, verdict_batch_enabled: true}});
    const body = request.postDataJSON(); posts.push(body);
    if (state.delay) await new Promise(resolve => setTimeout(resolve, state.delay));
    if (state.fail) return route.fulfill({status: 503, json: {error: 'test-save failed'}});
    const m = state.images.find(m => m.id === body.mockup_id);
    if (body.action === 'verdict') {
      m.before = clone({...m, before: undefined});
      Object.assign(m, {verdict: body.verdict, status: body.verdict === 'approved' ? 'picked' : 'open', verdict_change: {token: uuid(9000), at: new Date().toISOString(), undo_until: new Date(Date.now() + 5000).toISOString()}});
      return route.fulfill({json: {ok: true, mockup: m}});
    }
    if (body.action === 'undo_verdict') {
      const before = m.before; Object.keys(m).forEach(k => delete m[k]); Object.assign(m, before, {verdict_change: null});
      return route.fulfill({json: {ok: true, mockup: m}});
    }
    unexpected.push(body.action); return route.fulfill({status: 400, json: {error: 'test-unexpected action'}});
  });
  const card = n => page.locator('.mockup-card[data-mockup-id="' + uuid(n) + '"]');
  const row = n => card(n).locator('..');
  const settle = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  async function prepare() {
    await page.locator('.mockup-scrapped:not(.mockup-done) summary').click();
    await page.locator('.mockup-done summary').click();
    for (const [n, steps] of [[1, 3], [21, 2], [41, 3], [61, 2], [81, 1]]) await row(n).evaluate((r, steps) => { r.scrollLeft = (r.children[0].getBoundingClientRect().width + 16) * steps; }, steps);
    await settle();
  }
  async function positions() {
    return Promise.all([1, 21, 41, 61, 81].map(async n => [n, await row(n).evaluate(r => {
      const left = r.getBoundingClientRect().left, card = [...r.children].find(c => c.getBoundingClientRect().right > left);
      return {visible: !!r.clientWidth, left: r.scrollLeft, id: card?.dataset.mockupId, offset: card ? card.getBoundingClientRect().left - left : 0};
    })]));
  }
  async function samePositions(before, except = []) {
    for (const [n, saved] of before) if (!except.includes(n) && saved.visible) {
      const offset = await row(n).evaluate((r, id) => [...r.children].find(c => c.dataset.mockupId === id).getBoundingClientRect().left - r.getBoundingClientRect().left, saved.id);
      assert.ok(Math.abs(offset - saved.offset) < 2, 'Row anchored by test-screen ' + n + ' retains its independent horizontal card position');
    }
  }
  async function visible(n) {
    assert.equal(await card(n).isVisible(), true, 'Reviewed card stays in an open group');
    const b = await card(n).boundingBox(), r = await row(n).boundingBox();
    assert.ok(b.x + b.width > r.x && b.x < r.x + r.width, 'Reviewed card remains in its horizontal viewport');
    assert.ok(b.y + b.height > 0 && b.y < (mobile ? 844 : 1000), 'Reviewed card remains in its vertical viewport');
  }
  try {
    await page.goto('http://127.0.0.1:' + server.address().port + '/#k=test-fixture&tab=mockups');
    await card(1).waitFor(); await prepare();
    await run({page, state, posts, card, row, positions, samePositions, visible, settle});
    assert.deepEqual(errors, []); assert.deepEqual(unexpected, []);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'No page overflow');
    console.log('PASS', mobile ? 'phone' : 'desktop', name); passes++;
  } catch (e) { console.error('FAIL', mobile ? 'phone' : 'desktop', name, e.message); failures.push(name + ': ' + e.message); }
  finally { await ctx.close(); }
}
(async () => {
  server = http.createServer((q, r) => {
    const name = q.url.split('?')[0].slice(1) || 'index.html', file = path.resolve(root, name);
    if (!file.startsWith(root + path.sep)) { r.writeHead(403); return r.end(); }
    try { r.setHeader('Content-Type', name.endsWith('.js') ? 'text/javascript' : name.endsWith('.css') ? 'text/css' : 'text/html'); r.end(fs.readFileSync(file)); } catch { r.writeHead(404); r.end(); }
  }).listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve)); browser = await chromium.launch({headless: true});
  for (const mobile of [true, false]) {
    for (const [label, verdict] of [['Good to go', 'approved'], ['Needs work', 'needs_work'], ['Scrap', 'scrapped']]) {
      await scenario(label + ' saves preserve rows and keyboard focus', mobile, async ({page, card, positions, samePositions, visible}) => {
        if (verdict === 'scrapped') await page.locator('.mockup-scrapped:not(.mockup-done) summary').click();
        const action = card(4).getByRole('button', {name: label, exact: true}); await action.scrollIntoViewIfNeeded(); await action.focus();
        const before = await positions(), top = (await card(4).boundingBox()).y;
        await page.keyboard.press('Enter'); await page.waitForFunction(id => !mockups.busy.has(id), uuid(4));
        await card(4).getByText(verdict === 'approved' ? 'GOOD TO GO' : verdict === 'needs_work' ? 'NEEDS WORK' : 'SCRAPPED', {exact: true}).waitFor();
        await samePositions(before, verdict === 'scrapped' ? [1, 21] : []); await visible(4);
        assert.ok(Math.abs((await card(4).boundingBox()).y - top) < 2, 'Reviewed card retains its vertical viewport position');
        assert.equal(await action.evaluate(e => e === document.activeElement), true, 'The original verdict control regains keyboard focus');
      });
    }
    await scenario('Failed verdict and Undo preserve row positions and focus', mobile, async ({page, state, card, positions, samePositions}) => {
      state.fail = true; const action = card(4).getByRole('button', {name: 'Good to go', exact: true}); await action.scrollIntoViewIfNeeded(); await action.focus();
      const before = await positions(); await page.keyboard.press('Enter'); await page.waitForFunction(() => !mockups.busy.size); await samePositions(before);
      assert.equal(await action.evaluate(e => e === document.activeElement), true);
      state.fail = false; await page.keyboard.press('Enter'); await card(4).getByRole('button', {name: 'Undo', exact: true}).waitFor();
      const undo = card(4).getByRole('button', {name: 'Undo', exact: true}); await undo.focus(); const saved = await positions(); await page.keyboard.press('Enter');
      await page.waitForFunction(() => !mockups.busy.size); await samePositions(saved);
      assert.equal(await card(4).getByRole('button', {name: 'Good to go', exact: true}).evaluate(e => e === document.activeElement), true, 'Expired Undo focus has a useful card fallback');
    });
    await scenario('Scrap Undo follows the reviewed card back to its normal batch', mobile, async ({page, card, positions, samePositions, visible}) => {
      const action = card(4).getByRole('button', {name: 'Scrap', exact: true}); await action.click();
      await card(4).getByText('SCRAPPED', {exact: true}).waitFor();
      const before = await positions(), undo = card(4).getByRole('button', {name: 'Undo', exact: true}); await undo.focus();
      await page.keyboard.press('Enter'); await page.waitForFunction(() => !mockups.busy.size);
      await visible(4); await samePositions(before, [1, 21]);
      assert.equal(await card(4).getByRole('button', {name: 'Good to go', exact: true}).evaluate(e => e === document.activeElement), true);
    });
    await scenario('In-card Scrap Undo retains its own focus across refresh', mobile, async ({page, card}) => {
      await card(4).getByRole('button', {name: 'Scrap', exact: true}).click();
      const undo = card(4).getByRole('button', {name: 'Undo', exact: true}); await undo.waitFor(); await undo.focus();
      await page.evaluate(() => mockups.load());
      assert.equal(await undo.evaluate(e => e === document.activeElement), true, 'The card Undo must not resolve to the standalone Undo');
    });
    await scenario('Standalone Scrap Undo restores focus to the reviewed card', mobile, async ({page, card, visible}) => {
      await card(4).getByRole('button', {name: 'Scrap', exact: true}).click(); await card(4).getByText('SCRAPPED', {exact: true}).waitFor();
      const undo = page.locator('.mockup-scrap-undo[data-verdict-id="' + uuid(4) + '"]').getByRole('button', {name: 'Undo', exact: true});
      await undo.focus(); await page.keyboard.press('Enter'); await page.waitForFunction(() => !mockups.busy.size);
      await visible(4);
      assert.equal(await card(4).getByRole('button', {name: 'Good to go', exact: true}).evaluate(e => e === document.activeElement), true, 'Standalone Undo has an explicit restored-card focus fallback');
    });
    await scenario('Refresh and direct parent render retain all row positions and note selection', mobile, async ({page, card, positions, samePositions}) => {
      await card(4).getByRole('button', {name: 'Needs work', exact: true}).click(); const note = card(4).getByRole('textbox', {name: "What's off? (optional)", exact: true}); await note.waitFor();
      await note.fill('test-review this spacing'); await note.evaluate(e => { e.focus({preventScroll: true}); e.setSelectionRange(5, 11); });
      const before = await positions(); await page.evaluate(() => mockups.load()); await samePositions(before);
      assert.equal(await note.inputValue(), 'test-review this spacing');
      assert.deepEqual(await note.evaluate(e => [e === document.activeElement, e.selectionStart, e.selectionEnd]), [true, 5, 11]);
      await page.evaluate(() => render()); await samePositions(before);
      assert.deepEqual(await note.evaluate(e => [e === document.activeElement, e.selectionStart, e.selectionEnd]), [true, 5, 11]);
    });
    await scenario('Delayed verdict respects a later user focus choice', mobile, async ({page, card, positions, samePositions}) => {
      await card(4).getByRole('button', {name: 'Scrap', exact: true}).click();
      const filter = page.getByRole('combobox', {name: 'Filter mockups by project'}); await filter.focus(); const before = await positions();
      await page.waitForFunction(() => !mockups.busy.size); await samePositions(before, [1]);
      assert.equal(await filter.evaluate(e => e === document.activeElement), true);
    }, {delay: 250});
    await scenario('Pointer review follows Scrap with body focus and leaves keyboard focus alone', mobile, async ({page, card, visible}) => {
      const action = card(4).getByRole('button', {name: 'Scrap', exact: true});
      await action.evaluate(e => e.addEventListener('click', () => document.activeElement.blur(), {capture: true}));
      if (mobile) await action.tap(); else await action.click();
      await page.waitForFunction(() => !mockups.busy.size);
      await visible(4);
      assert.equal(await page.evaluate(() => document.activeElement === document.body), true, 'Pointer review does not invent keyboard focus');
    }, {delay: 250});
    await scenario('A later pointer scroll cancels following the reviewed card', mobile, async ({page, card}) => {
      await page.locator('.mockup-scrapped:not(.mockup-done) summary').click();
      const action = card(4).getByRole('button', {name: 'Scrap', exact: true});
      await action.evaluate(e => e.addEventListener('click', () => document.activeElement.blur(), {capture: true}));
      if (mobile) await action.tap(); else await action.click();
      await page.mouse.wheel(0, -5000); await page.waitForFunction(() => scrollY < 2);
      await page.waitForFunction(() => !mockups.busy.size);
      assert.equal(await page.locator('.mockup-scrapped:not(.mockup-done)').evaluate(e => e.open), false);
      assert.ok(await page.evaluate(() => scrollY) < 2, 'The later user scroll position survives the response');
    }, {delay: 250});
    await scenario('Closed rows retain their anchors through refresh and reopening', mobile, async ({page, row, positions, samePositions}) => {
      const before = await positions();
      await page.locator('.mockup-scrapped:not(.mockup-done) summary').click(); await page.locator('.mockup-done summary').click();
      await page.evaluate(() => mockups.load());
      await page.locator('.mockup-scrapped:not(.mockup-done) summary').click(); await page.locator('.mockup-done summary').click();
      await samePositions(before);
      await row(81).focus(); await page.evaluate(() => render());
      assert.equal(await row(81).evaluate(e => e === document.activeElement), true, 'Row keyboard focus survives a parent render');
      const summary = page.locator('.mockup-done summary'); await summary.focus(); await page.evaluate(() => mockups.load());
      assert.equal(await summary.evaluate(e => e === document.activeElement), true, 'Details summary keyboard focus survives refresh');
    });
    await scenario('Done deadline follows only the focused reviewed card', mobile, async ({page, state, card, positions, samePositions, visible}) => {
      state.images.find(m => m.id === uuid(4)).verdict = 'approved'; state.images.find(m => m.id === uuid(4)).verdict_change = {at: new Date(now - day + 3000).toISOString()};
      await page.evaluate(() => mockups.load());
      await page.locator('.mockup-done summary').click();
      const action = card(4).getByRole('button', {name: 'Good to go', exact: true}); await action.scrollIntoViewIfNeeded(); await action.focus();
      const before = await positions(); await page.clock.fastForward(4000); await samePositions(before, [1, 41]); await visible(4);
      assert.equal(await card(4).locator('..').locator('..').getAttribute('class'), 'mockup-scrapped mockup-done');
      assert.equal(await action.evaluate(e => e === document.activeElement), true);
    });
    await scenario('Unfocused Done deadline preserves every other row and keeps Done closed', mobile, async ({page, state, card, positions, samePositions}) => {
      state.images.find(m => m.id === uuid(4)).verdict = 'approved'; state.images.find(m => m.id === uuid(4)).verdict_change = {at: new Date(now - day + 3000).toISOString()};
      await page.evaluate(() => mockups.load()); await page.locator('.mockup-done summary').click();
      await page.getByRole('combobox', {name: 'Filter mockups by project'}).focus(); const before = await positions();
      await page.clock.fastForward(4000); await samePositions(before, [1]);
      assert.equal(await page.locator('.mockup-done').evaluate(e => e.open), false);
    });
  }
  console.log(passes + ' gallery scenarios passed; ' + failures.length + ' failed. No live API requests.');
  if (failures.length) process.exitCode = 1;
})().catch(e => { console.error(e); process.exitCode = 1; }).finally(async () => { if (browser) await browser.close(); if (server) server.close(); });
