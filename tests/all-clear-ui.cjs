/* Run with node tests/all-clear-ui.cjs. All remote requests are intercepted. */
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
const {chromium} = playwright();
const root = process.env.ROOT || path.resolve(__dirname, '..');
const uuid = n => '00000000-0000-4000-8000-' + String(n).padStart(12, '0');
const clone = value => JSON.parse(JSON.stringify(value));
const image = (n, extra = {}) => ({
  id: uuid(n), project: 'Bookish', batch: 'Bookish full app', title: 'test-screen ' + n,
  status: 'open', verdict: null, sort: n, width: 800, height: 1000,
  created_at: new Date(Date.now() - n * 1000).toISOString(), preview_url: 'https://image.test/' + n + '.svg',
  full_url: 'https://image.test/full-' + n + '.svg', full_width: 1600, full_height: 2000, ...extra,
});
const pin = (n, imageId, resolved = false) => ({
  id: uuid(1000 + n), mockup_id: uuid(imageId), x: .25, y: .3, resolved,
  created_at: '2026-10-16T12:00:00Z', thread: [{who: 'seb', text: 'test-pin ' + n, at: '2026-10-16T12:00:00Z'}],
});
function fixtures() {
  return {
    images: [image(1), image(2), image(3), image(4, {status: 'picked'}), image(5, {verdict: 'needs_work'}),
      image(6, {status: 'picked', verdict: 'approved', verdict_change: {at: new Date(Date.now() - 172800000).toISOString()}}),
      image(7, {verdict: 'scrapped'}), image(8, {status: 'archived'}), image(9, {project: 'Fictora'}),
      image(10, {batch: 'Cover options'}), image(11, {batch: 'Cover options'})],
    pins: [pin(1, 2, true), pin(2, 3), pin(3, 3), pin(4, 5), pin(5, 6), pin(6, 7), pin(7, 8), pin(8, 9), pin(9, 11)],
  };
}
const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1000"><rect width="800" height="1000" fill="#091d2b"/><rect x="54" y="70" width="692" height="860" rx="30" fill="#f1e9da"/><text x="105" y="175" font-family="Georgia" font-size="48" fill="#193548">A good chapter.</text><rect x="105" y="230" width="590" height="300" rx="15" fill="#bed2c4"/><path d="M145 470L300 290L430 430L540 340L660 470" fill="#427165"/><rect x="105" y="590" width="430" height="22" fill="#87958b"/><rect x="105" y="640" width="530" height="15" fill="#ccd0c6"/><rect x="105" y="680" width="480" height="15" fill="#ccd0c6"/><rect x="105" y="770" width="590" height="80" rx="14" fill="#193548"/><text x="290" y="820" font-family="sans-serif" font-size="26" fill="white">Keep reading</text></svg>';
let server, browser, count = 0;
async function scenario(name, mobile, run, setup = {}) {
  if (process.env.SCENARIO && !name.includes(process.env.SCENARIO)) return;
  const ctx = await browser.newContext({viewport: mobile ? {width: 390, height: 844} : {width: 1440, height: 1000}, isMobile: mobile, hasTouch: mobile, reducedMotion: 'reduce'});
  const page = await ctx.newPage(), errors = [], unexpected = [], posts = [], operations = new Map();
  page.setDefaultTimeout(8000);
  page.on('pageerror', e => errors.push(e.message));
  const data = fixtures();
  const state = {enabled: true, fail: false, lose: false, delay: 0, undoDeadline: 30000, ...data, ...setup};
  if (setup.storageThrows) await page.addInitScript(() => {
    Storage.prototype.getItem = Storage.prototype.setItem = () => { throw Error('test-storage blocked'); };
  });
  await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.hostname === '127.0.0.1') return route.continue();
    if (url.hostname === 'image.test') return route.fulfill({contentType: 'image/svg+xml', body: svg});
    if (url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') return route.fulfill({body: '', contentType: 'text/css'});
    if (url.pathname.endsWith('/ted-board')) return route.fulfill({json: url.searchParams.has('resource') ? {jobs: [], approvals: []} : {cards: []}});
    if (!url.pathname.endsWith('/ted-mockups')) { unexpected.push(request.url()); return route.abort(); }
    if (request.method() === 'GET') {
      if (state.failRefresh && posts.length) return route.fulfill({status: 503, json: {error: 'test-refresh unavailable'}});
      if (state.holdRefresh && posts.length) {
        const snapshot = clone({mockups: state.images, pins: state.pins, verdicts_enabled: true, verdict_batch_enabled: state.enabled});
        await new Promise(resolve => { state.releaseRefresh = () => { state.holdRefresh = false; resolve(); }; state.onRefreshHeld?.(); });
        return route.fulfill({json: snapshot});
      }
      return route.fulfill({json: {mockups: state.images, pins: state.pins, verdicts_enabled: true, verdict_batch_enabled: state.enabled}});
    }
    const body = request.postDataJSON(); posts.push(body);
    if (state.delay) await new Promise(resolve => setTimeout(resolve, state.delay));
    if (state.fail) return route.fulfill({status: 503, json: {error: 'test-save unavailable. Try again.'}});
    if (body.action === 'verdict_batch') {
      assert.ok(body.ids.length > 0 && body.ids.length <= 200);
      assert.equal(new Set(body.ids).size, body.ids.length);
      let operation = operations.get(body.operation_id);
      if (!operation) {
        const before = [], changed = [], skipped = [], deadline = new Date(Date.now() + state.undoDeadline).toISOString();
        for (const id of body.ids) {
          const m = state.images.find(row => row.id === id);
          if (!m || m.project !== body.project || m.batch !== body.batch || m.status !== 'open' || m.verdict || state.pins.some(p => p.mockup_id === id && !p.resolved)) { skipped.push({id, reason: 'unresolved_pins'}); continue; }
          before.push(clone(m));
          Object.assign(m, {status: 'picked', verdict: 'approved', verdict_change: {token: uuid(2001 + changed.length), batch_operation_id: body.operation_id, at: new Date().toISOString(), undo_until: deadline}});
          changed.push(id);
        }
        operation = {before, changed, skipped, token: uuid(9000), undo_until: deadline, undone: false};
        operations.set(body.operation_id, operation);
      }
      if (state.lose) { state.lose = false; return route.abort('failed'); }
      const mockups = operation.changed.map(id => { const row = clone(state.images.find(m => m.id === id)); delete row.full_url; delete row.full_width; delete row.full_height; return row; });
      return route.fulfill({json: {ok: true, operation_id: body.operation_id, token: operation.token, undo_until: operation.undo_until, skipped: operation.skipped, mockups, duplicate: posts.length > 1, undone: operation.undone}});
    }
    if (body.action === 'undo_verdict_batch') {
      const op = operations.get(body.operation_id);
      assert.ok(op); assert.equal(body.token, op.token);
      if (op.undone) return route.fulfill({json: {ok: true, operation_id: body.operation_id, token: op.token, undo_until: op.undo_until, mockups: op.before.map(m => clone(state.images.find(row => row.id === m.id))), skipped: [], conflicts: [], undone: true, duplicate: true}});
      const restored = [], conflicts = [];
      for (const before of op.before) {
        const index = state.images.findIndex(m => m.id === before.id);
        if (state.images[index].status === 'archived' || state.images[index].verdict !== 'approved') { conflicts.push({id: before.id, reason: 'newer_change'}); continue; }
        state.images[index] = clone(before); restored.push(clone(before));
      }
      op.undone = true;
      if (state.loseUndo) { state.loseUndo = false; return route.abort('failed'); }
      return route.fulfill({json: {ok: true, operation_id: body.operation_id, token: op.token, undo_until: op.undo_until, mockups: restored, skipped: [], conflicts, undone: true}});
    }
    unexpected.push(body.action); return route.fulfill({status: 400, json: {error: 'test-unexpected action'}});
  });
  const card = n => page.locator('.mockup-card[data-mockup-id="' + uuid(n) + '"]');
  const batch = title => page.locator('.mockup-batch').filter({has: page.getByRole('heading', {name: title, exact: true})})
    .filter({has: page.locator('.mockup-batch-head p').filter({hasText: /^Bookish · /})});
  try {
    await page.goto('http://127.0.0.1:' + server.address().port + '/#k=test-fixture&tab=mockups');
    await card(1).waitFor();
    await run({page, ctx, state, posts, operations, card, batch});
    assert.deepEqual(errors, []); assert.deepEqual(unexpected, []);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'No page overflow');
    console.log('PASS', mobile ? 'phone' : 'desktop', name); count++;
  } finally { state.releaseRefresh?.(); await ctx.close(); }
}
async function confirmBatch(page, batch) {
  await batch('Bookish full app').getByRole('button', {name: 'All clear', exact: true}).click();
  const sheet = page.getByRole('dialog', {name: 'All clear?', exact: true});
  await sheet.waitFor();
  return sheet;
}
(async () => {
  server = http.createServer((q, r) => {
    const name = q.url.split('?')[0].slice(1) || 'index.html';
    const file = path.resolve(root, name);
    if (!file.startsWith(root + path.sep)) { r.writeHead(403); return r.end(); }
    try { r.setHeader('Content-Type', name.endsWith('.js') ? 'text/javascript' : name.endsWith('.css') ? 'text/css' : 'text/html'); r.end(fs.readFileSync(file)); }
    catch { r.writeHead(404); r.end(); }
  }).listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  browser = await chromium.launch({headless: true});
  for (const mobile of [true, false]) {
    await scenario('Open pins includes hidden groups, respects project, and persists', mobile, async ({page, card}) => {
      await page.getByRole('combobox', {name: 'Filter mockups by project'}).selectOption('Bookish');
      const toggle = page.getByRole('button', {name: 'Open pins (6)', exact: true});
      await toggle.click(); assert.equal(await toggle.getAttribute('aria-pressed'), 'true');
      assert.equal(await card(1).count(), 0); assert.equal(await card(2).count(), 0); assert.equal(await card(8).count(), 0); assert.equal(await card(9).count(), 0);
      await card(3).getByText('2 open pins', {exact: true}).waitFor(); await card(11).waitFor();
      await page.locator('.mockup-done summary').click(); await card(6).waitFor({state: 'visible'});
      await page.locator('.mockup-scrapped:not(.mockup-done) summary').click(); await card(7).waitFor({state: 'visible'});
      await page.getByRole('combobox', {name: 'Filter mockups by project'}).selectOption('Fictora');
      await card(9).waitFor(); assert.equal(await card(3).count(), 0);
      await page.reload(); await page.getByRole('button', {name: 'Open pins (7)', exact: true}).waitFor();
      assert.equal(await page.getByRole('button', {name: 'Open pins (7)', exact: true}).getAttribute('aria-pressed'), 'true');
      assert.equal(await card(1).count(), 0);
    });
    await scenario('All clear confirms full exact batch under filter, skips pins, and has one Undo', mobile, async ({page, state, posts, card, batch}) => {
      await page.clock.install();
      await page.getByRole('combobox', {name: 'Filter mockups by project'}).selectOption('Bookish');
      await page.getByRole('button', {name: 'Open pins (6)', exact: true}).click();
      let sheet = await confirmBatch(page, batch);
      await sheet.getByText('Mark 2 images good to go?', {exact: true}).waitFor();
      await sheet.getByText('4 with open pins stay put.', {exact: true}).waitFor();
      assert.equal(await sheet.getByRole('button', {name: 'Cancel', exact: true}).evaluate(e => e === document.activeElement), true);
      for (const b of await sheet.getByRole('button').all()) {
        const box = await b.boundingBox(); assert.ok(box.width >= 44 && box.height >= 44);
      }
      await page.keyboard.press('Escape'); assert.equal(await sheet.isVisible(), false);
      assert.equal(await batch('Bookish full app').getByRole('button', {name: 'All clear', exact: true}).evaluate(e => e === document.activeElement), true);
      sheet = await confirmBatch(page, batch);
      await sheet.getByRole('button', {name: 'Mark 2 good to go', exact: true}).focus();
      await page.keyboard.press('Enter');
      const toast = page.locator('.mockup-batch-toast'); await toast.getByRole('button', {name: 'Undo', exact: true}).waitFor();
      assert.equal(await toast.getByRole('button', {name: 'Undo', exact: true}).evaluate(e => e === document.activeElement), true, 'Keyboard focus reaches the batch Undo after saving');
      assert.equal(posts.length, 1); assert.equal(posts[0].action, 'verdict_batch'); assert.equal(posts[0].project, 'Bookish'); assert.equal(posts[0].batch, 'Bookish full app');
      assert.deepEqual(posts[0].ids, [uuid(1), uuid(2)]); assert.match(posts[0].operation_id, /^[\da-f-]{36}$/i);
      assert.equal(state.images.find(m => m.id === uuid(3)).verdict, null);
      assert.equal(await page.evaluate(() => mockups.mockups.find(m => m.title === 'test-screen 1').full_width), 1600);
      await page.getByRole('button', {name: 'Open pins (6)', exact: true}).click();
      await card(1).getByText('GOOD TO GO', {exact: true}).waitFor();
      assert.equal(await page.getByRole('button', {name: 'Undo', exact: true}).count(), 1, 'Batch rows never get separate Undo controls');
      await page.clock.fastForward(6000);
      assert.equal(await toast.getByRole('button', {name: 'Undo', exact: true}).isVisible(), true, 'The batch Undo survives the former five-second deadline');
      await toast.getByRole('button', {name: 'Undo', exact: true}).click();
      await page.waitForFunction(() => !mockups.batchOperation?.busy);
      assert.equal(await card(1).getByText('GOOD TO GO', {exact: true}).count(), 0);
      assert.equal(posts[1].action, 'undo_verdict_batch'); assert.equal(posts[1].operation_id, posts[0].operation_id);
    });
    await scenario('Unavailable capability fails closed, and unavailable storage is safe', mobile, async ({page, batch, state}) => {
      assert.equal(await batch('Bookish full app').getByRole('button', {name: 'All clear', exact: true}).isDisabled(), true);
      await page.getByRole('button', {name: 'Open pins (7)', exact: true}).click();
      assert.equal(await page.getByRole('button', {name: 'Open pins (7)', exact: true}).getAttribute('aria-pressed'), 'true');
      state.enabled = undefined;
      await page.evaluate(() => mockups.load());
      assert.equal(await batch('Bookish full app').getByRole('button', {name: 'All clear', exact: true}).isDisabled(), true);
    }, {enabled: false, storageThrows: true});
    await scenario('Lost response retry reuses operation and retains server deadline', mobile, async ({page, posts, batch, state}) => {
      const sheet = await confirmBatch(page, batch);
      await sheet.getByRole('button', {name: 'Mark 2 good to go', exact: true}).click();
      const toast = page.locator('.mockup-batch-toast');
      await toast.getByRole('button', {name: 'Retry', exact: true}).waitFor();
      const original = state.images.find(m => m.id === uuid(1)).verdict_change.undo_until;
      await toast.getByRole('button', {name: 'Retry', exact: true}).click();
      await toast.getByRole('button', {name: 'Undo', exact: true}).waitFor();
      assert.equal(posts.length, 2); assert.deepEqual(posts[1], posts[0]);
      assert.equal(await page.evaluate(() => mockups.batchOperation.undo_until), original);
    }, {lose: true});
    await scenario('A held refresh cannot consume Undo or overwrite a completed Undo', mobile, async ({page, state, batch, card}) => {
      const held = new Promise(resolve => { state.onRefreshHeld = resolve; });
      const sheet = await confirmBatch(page, batch);
      await sheet.getByRole('button', {name: 'Mark 2 good to go', exact: true}).click();
      await held;
      const toast = page.locator('.mockup-batch-toast');
      await toast.getByRole('button', {name: 'Undo', exact: true}).waitFor();
      assert.equal(await page.evaluate(() => mockups.loading), true, 'Refresh is still held while Undo is usable');
      await toast.getByRole('button', {name: 'Undo', exact: true}).click();
      await page.waitForFunction(() => mockups.batchOperation?.undone === true && !mockups.batchOperation.busy);
      state.releaseRefresh();
      await page.waitForFunction(() => !mockups.loading);
      assert.equal(await card(1).getByText('GOOD TO GO', {exact: true}).count(), 0, 'The older refresh cannot overwrite Undo');
    }, {holdRefresh: true});
    await scenario('Saving keeps focus where the user moved it', mobile, async ({page, batch}) => {
      const sheet = await confirmBatch(page, batch);
      await sheet.getByRole('button', {name: 'Mark 2 good to go', exact: true}).click();
      const filter = page.getByRole('combobox', {name: 'Filter mockups by project'});
      await filter.focus();
      await page.locator('.mockup-batch-toast').getByRole('button', {name: 'Undo', exact: true}).waitFor();
      await page.waitForFunction(() => !mockups.loading);
      assert.equal(await filter.evaluate(e => e === document.activeElement), true, 'A later user focus choice survives the save and refresh');
    }, {delay: 150});
    await scenario('Lost Undo response can reconcile after expiry and preserves a newer verdict', mobile, async ({page, state, posts, batch, card}) => {
      await page.clock.install();
      const sheet = await confirmBatch(page, batch);
      await sheet.getByRole('button', {name: 'Mark 2 good to go', exact: true}).click();
      const toast = page.locator('.mockup-batch-toast');
      await toast.getByRole('button', {name: 'Undo', exact: true}).click();
      await toast.getByRole('button', {name: 'Retry', exact: true}).waitFor();
      state.images.find(m => m.id === uuid(1)).verdict = 'needs_work';
      await page.clock.fastForward(31000);
      await toast.getByRole('button', {name: 'Retry', exact: true}).click();
      await page.waitForFunction(() => !mockups.batchOperation?.busy);
      assert.equal(posts.length, 3, 'Expired reconciliation reaches the server');
      assert.deepEqual(posts[2], posts[1]);
      await card(1).getByText('NEEDS WORK', {exact: true}).waitFor();
      assert.equal(await page.evaluate(() => mockups.batchOperation.undone), true);
      assert.equal(await toast.getByRole('button', {name: 'Undo', exact: true}).count(), 0);
    }, {loseUndo: true});
    await scenario('Pins added after confirmation are refreshed and reported as skipped', mobile, async ({page, state, batch, card}) => {
      const sheet = await confirmBatch(page, batch);
      state.pins.push(pin(30, 2));
      await sheet.getByRole('button', {name: 'Mark 2 good to go', exact: true}).click();
      const toast = page.locator('.mockup-batch-toast');
      await toast.getByText(/1 image skipped/).waitFor();
      await card(1).getByText('GOOD TO GO', {exact: true}).waitFor();
      assert.equal(await card(2).getByText('GOOD TO GO', {exact: true}).count(), 0);
      await card(2).getByText('1 open pin', {exact: true}).waitFor();
    });
    await scenario('Failed save reports progress and retry without optimistic approvals', mobile, async ({page, state, posts, batch, card}) => {
      const sheet = await confirmBatch(page, batch);
      await sheet.getByRole('button', {name: 'Mark 2 good to go', exact: true}).click();
      const toast = page.locator('.mockup-batch-toast');
      assert.equal(await toast.getAttribute('aria-busy'), 'true');
      await toast.getByRole('button', {name: 'Retry', exact: true}).waitFor();
      assert.equal(await card(1).getByText('GOOD TO GO', {exact: true}).count(), 0);
      state.fail = false;
      await toast.getByRole('button', {name: 'Retry', exact: true}).click();
      await toast.getByRole('button', {name: 'Undo', exact: true}).waitFor();
      assert.deepEqual(posts[1], posts[0]);
      assert.equal(await page.evaluate(() => mockups.mockups.find(m => m.title === 'test-screen 1').full_width), 1600, 'Raw rows preserve detail when refresh fails');
    }, {fail: true, delay: 100, failRefresh: true});
    await scenario('Dismissing a failed operation restores batch controls', mobile, async ({page, batch}) => {
      const sheet = await confirmBatch(page, batch);
      await sheet.getByRole('button', {name: 'Mark 2 good to go', exact: true}).click();
      const toast = page.locator('.mockup-batch-toast');
      await toast.getByRole('button', {name: 'Retry', exact: true}).waitFor();
      assert.equal(await batch('Bookish full app').getByRole('button', {name: 'All clear', exact: true}).isDisabled(), true);
      await toast.getByRole('button', {name: 'Dismiss', exact: true}).click();
      assert.equal(await batch('Bookish full app').getByRole('button', {name: 'All clear', exact: true}).isDisabled(), false);
    }, {fail: true});
    await scenario('Expired duplicate replay keeps newer verdict and cannot reopen Undo', mobile, async ({page, state, posts, batch, card}) => {
      const sheet = await confirmBatch(page, batch);
      await sheet.getByRole('button', {name: 'Mark 2 good to go', exact: true}).click();
      const toast = page.locator('.mockup-batch-toast');
      await toast.getByRole('button', {name: 'Retry', exact: true}).waitFor();
      state.images.find(m => m.id === uuid(1)).verdict = 'needs_work';
      await page.waitForTimeout(400);
      await toast.getByRole('button', {name: 'Retry', exact: true}).click();
      await page.waitForFunction(() => !mockups.batchOperation?.busy);
      await card(1).getByText('NEEDS WORK', {exact: true}).waitFor();
      assert.equal(await toast.getByRole('button', {name: 'Undo', exact: true}).count(), 0);
      assert.equal(await toast.getByText(/images marked good to go/).count(), 0, 'Reconciliation does not claim a newer verdict was approved');
      assert.deepEqual(posts[1], posts[0]);
    }, {lose: true, undoDeadline: 250});
    await scenario('An already undone replay never offers Undo or restores approvals', mobile, async ({page, state, operations, batch, card}) => {
      const sheet = await confirmBatch(page, batch);
      await sheet.getByRole('button', {name: 'Mark 2 good to go', exact: true}).click();
      const toast = page.locator('.mockup-batch-toast');
      await toast.getByRole('button', {name: 'Retry', exact: true}).waitFor();
      const op = [...operations.values()][0]; op.undone = true;
      op.before.forEach(before => { state.images[state.images.findIndex(m => m.id === before.id)] = clone(before); });
      await toast.getByRole('button', {name: 'Retry', exact: true}).click();
      await page.waitForFunction(() => !mockups.batchOperation?.busy);
      assert.equal(await card(1).getByText('GOOD TO GO', {exact: true}).count(), 0);
      assert.equal(await toast.getByRole('button', {name: 'Undo', exact: true}).count(), 0);
    }, {lose: true});
    await scenario('Oversized batch stays bounded, and stale responses cannot restore reset state', mobile, async ({page, posts, batch, state}) => {
      state.images = Array.from({length: 201}, (_, i) => image(i + 20)); state.pins = [];
      await page.evaluate(() => mockups.load());
      let sheet = await confirmBatch(page, batch);
      assert.equal(await sheet.getByRole('button', {name: /Mark .* good to go/}).isDisabled(), true);
      await sheet.getByText(/ask Ted to split the batch/).waitFor();
      await sheet.getByRole('button', {name: 'Cancel', exact: true}).click(); assert.equal(posts.length, 0);
      state.images = Array.from({length: 200}, (_, i) => image(i + 20));
      await page.evaluate(() => mockups.load()); sheet = await confirmBatch(page, batch);
      await sheet.getByRole('button', {name: 'Mark 200 good to go', exact: true}).click();
      await page.locator('.mockup-batch-toast').getByRole('button', {name: 'Undo', exact: true}).waitFor();
      assert.equal(posts.length, 1); assert.equal(posts[0].ids.length, 200);
      await page.waitForFunction(() => !mockups.loading);
      state.images = [image(1)]; state.delay = 500;
      await page.evaluate(() => mockups.load()); sheet = await confirmBatch(page, batch);
      await sheet.getByRole('button', {name: 'Mark 1 good to go', exact: true}).click();
      await page.waitForFunction(() => mockups.batchOperation?.busy);
      await page.evaluate(() => { mockups.reset(); mockups.onChange(); });
      await page.waitForTimeout(650);
      assert.equal(await page.locator('.mockup-batch-toast').isVisible(), false);
      assert.equal(await page.evaluate(() => mockups.mockups.length), 0);
    });
    await scenario('Undo reports newer verdict conflicts and expires at server deadline', mobile, async ({page, state, batch, card}) => {
      const sheet = await confirmBatch(page, batch);
      await sheet.getByRole('button', {name: 'Mark 2 good to go', exact: true}).click();
      const toast = page.locator('.mockup-batch-toast'); await toast.getByRole('button', {name: 'Undo', exact: true}).waitFor();
      state.images.find(m => m.id === uuid(1)).verdict = 'needs_work';
      await toast.getByRole('button', {name: 'Undo', exact: true}).click();
      await toast.getByText(/1 newer change kept/).waitFor();
      await card(1).getByText('NEEDS WORK', {exact: true}).waitFor();
      assert.equal(await card(2).getByText('GOOD TO GO', {exact: true}).count(), 0);
    });
    await scenario('Server Undo expiry and screenshot layouts', mobile, async ({page, batch}) => {
      const sheet = await confirmBatch(page, batch);
      const dir = path.join(__dirname, 'screenshots'); fs.mkdirSync(dir, {recursive: true});
      await page.screenshot({path: path.join(dir, mobile ? 'all-clear-phone.png' : 'all-clear-desktop.png')});
      await sheet.getByRole('button', {name: 'Mark 2 good to go', exact: true}).click();
      const toast = page.locator('.mockup-batch-toast'); await toast.getByRole('button', {name: 'Undo', exact: true}).waitFor();
      await page.waitForTimeout(900); assert.equal(await toast.getByRole('button', {name: 'Undo', exact: true}).count(), 0);
      assert.equal(await toast.getByText(/Undo is available/).count(), 0, 'Expiry removes the stale availability claim');
      await toast.getByRole('button', {name: 'Dismiss', exact: true}).click();
      await page.getByRole('combobox', {name: 'Filter mockups by project'}).selectOption('Bookish');
      await page.getByRole('button', {name: 'Open pins (6)', exact: true}).click();
      await page.screenshot({path: path.join(dir, mobile ? 'open-pins-phone.png' : 'open-pins-desktop.png'), fullPage: true});
    }, {undoDeadline: 650});
  }
  console.log(count + ' scenarios passed. No live API requests.');
})().catch(e => { console.error(e); process.exitCode = 1; }).finally(async () => { if (browser) await browser.close(); if (server) server.close(); });
