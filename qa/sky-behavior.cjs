// Actual Chrome, synthetic feeds, and no external requests. Run through qa/offline.cjs.
const assert = require('node:assert/strict');
const {test, before, after} = require('node:test');
const {chromium, fixture, clip} = require('./browser.cjs');
let browser;
before(async () => { browser = await chromium.launch({headless: true}); });
after(async () => { await browser?.close(); });
async function open({sky = 'day', denied = false, reduced = false, width = 390} = {}) {
  const page = await browser.newPage({viewport: {width, height: 900}, reducedMotion: reduced ? 'reduce' : 'no-preference', colorScheme: sky === 'day' ? 'light' : 'dark'});
  if (denied) await page.addInitScript(() => { Object.defineProperty(window, 'localStorage', {get() { throw new DOMException('Denied', 'SecurityError'); }}); });
  const posts = await fixture(page);
  await page.goto('http://127.0.0.1:8763/#k=fixture-only&tab=inbox');
  await page.waitForSelector('.v3-paper');
  await page.evaluate(() => document.fonts.ready);
  return {page, posts};
}
async function undoContrast(page, selector) {
  const result = await page.locator(selector).evaluate(toast => {
    const text = getComputedStyle(toast.matches('button') ? toast : toast.querySelector('button')).color;
    const background = getComputedStyle(toast).backgroundColor;
    const rgb = value => value.match(/[\d.]+/g).map(Number);
    const lum = value => rgb(value).slice(0, 3).map(n => n / 255).map(n => n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4).reduce((sum, n, i) => sum + n * [.2126, .7152, .0722][i], 0);
    const a = lum(text), b = lum(background);
    return {text, background, ratio: (Math.max(a, b) + .05) / (Math.min(a, b) + .05)};
  });
  assert.ok(result.ratio >= 4.5, JSON.stringify(result));
  assert.notEqual(result.text, 'rgba(0, 0, 0, 0)');
  return result;
}
test('Still sky works with denied storage and the accessible control reflects the session state', async () => {
  const {page} = await open({denied: true});
  try {
    const button = page.getByRole('button', {name: 'Still sky', exact: true});
    await button.click();
    assert.equal(await button.getAttribute('aria-pressed'), 'true');
    assert.equal(await page.locator('.sky-day').evaluate(e => getComputedStyle(e).animationName), 'none');
    await button.click();
    assert.equal(await button.getAttribute('aria-pressed'), 'false');
    assert.equal(await page.locator('.sky-day').evaluate(e => getComputedStyle(e).animationName), 'sky-drift');
  } finally { await page.close(); }
});
test('Sky keyboard controls do not activate Mockups shortcuts and persist the selected sky', async () => {
  const {page, posts} = await open();
  try {
    await page.evaluate(() => { selectProject('Mockups'); mockups.openBatch(mockups.batches().find(b => b.kind === 'round')); });
    const radio = page.getByRole('radio', {name: 'Day', exact: true});
    await radio.focus(); await page.keyboard.press('Enter');
    assert.equal(await page.locator('dialog[open]').count(), 0);
    await page.keyboard.press('ArrowLeft');
    assert.equal(await page.getByRole('radio', {name: 'Night', exact: true}).getAttribute('aria-checked'), 'true');
    await page.keyboard.press('End');
    assert.equal(await radio.getAttribute('aria-checked'), 'true');
    await page.keyboard.press('Home');
    await page.reload(); await page.waitForSelector('.sky-controls');
    assert.equal(await page.locator('html').getAttribute('data-sky'), 'night');
    assert.equal(await page.locator('.sky-controls').count(), 1);
    assert.equal(posts.length, 0);
  } finally { await page.close(); }
});
test('reduced motion stops both skies and crossfade without permitting an override', async () => {
  const {page} = await open({reduced: true});
  try {
    assert.equal(await page.getByRole('button', {name: 'Still sky', exact: true}).isDisabled(), true);
    assert.deepEqual(await page.locator('.sky-day,.sky-stars i').evaluateAll(nodes => [...new Set(nodes.map(e => getComputedStyle(e).animationName))]), ['none']);
    assert.deepEqual(await page.locator('.sky-art').evaluateAll(nodes => [...new Set(nodes.map(e => getComputedStyle(e).transitionDuration))]), ['0s']);
  } finally { await page.close(); }
});
for (const sky of ['day', 'night']) test(sky + ' Undo remains readable and cancels Decide and archive before any write', async () => {
  const {page, posts} = await open({sky});
  try {
    await page.clock.install(); await page.clock.pauseAt(new Date(Date.now() + 50));
    await page.evaluate(() => decide.view('decide'));
    await page.locator('.decide-card').getByRole('button', {name: 'Not yet', exact: true}).click();
    await undoContrast(page, '.decide-toast');
    await page.locator('.decide-toast').getByRole('button', {name: 'Undo', exact: true}).click();
    await page.clock.runFor(5300); assert.equal(posts.length, 0);
    await page.evaluate(() => { decide.view('list'); selectProject('Mockups'); mockups.capabilities.archive = true; render(); });
    await page.locator('.mk3-cover').first().getByRole('button', {name: 'Archive', exact: true}).click();
    await undoContrast(page, '.mockup-archive-toast');
    await page.locator('.mockup-archive-toast').getByRole('button', {name: 'Undo', exact: true}).click();
    await page.clock.runFor(5300); assert.equal(posts.length, 0);
    assert.equal(await page.locator('.mk3-cover').count(), 3);
  } finally { await page.close(); }
});
for (const sky of ['day', 'night']) test(sky + ' current Business Patch keeps every group, exact card navigation, and focus', async () => {
  const {page, posts} = await open({sky});
  try {
    await page.evaluate(() => { state.cards.push({id:'patch-next',section:'up_next',project:'Fixture',title:'Next handoff'},{id:'patch-ted',section:'ted_doing',project:'Fixture',title:'Assigned work'},{id:'patch-alert',section:'up_next',live_state:'blocked',project:'Fixture',title:'Blocked fixture'}); render(); });
    await page.locator('.v3-business-patch>summary').click();
    assert.equal(await page.locator('.bp-group').count(), 4);
    assert.equal(await page.locator('.bp-open').count(), 6);
    await page.getByRole('button', {name: 'Open card: Next handoff', exact: true}).click();
    assert.equal(await page.evaluate(() => v3.item), 'patch-next');
    assert.equal(await page.locator('.v3-detail').evaluate(e => e === document.activeElement), true);
    assert.deepEqual((await clip(page)).clips, []);
    assert.equal(posts.length, 0);
  } finally { await page.close(); }
});
for (const sky of ['day', 'night']) test(sky + ' Veto hover has contrasting opaque colors and keyboard focus stays visible', async () => {
  const {page, posts} = await open({sky});
  try {
    const veto = page.locator('.v3-decision button').first();
    await veto.hover();
    const hover = await undoContrast(page, '.v3-decision button');
    assert.ok(!hover.background.startsWith('rgba'), 'hover background is opaque');
    await page.mouse.move(1, 1); await veto.focus();
    await page.keyboard.press('Tab'); await page.keyboard.press('Shift+Tab');
    const focus = await veto.evaluate(e => ({focused: e.matches(':focus-visible'), outline: getComputedStyle(e).outlineWidth, style: getComputedStyle(e).outlineStyle}));
    assert.equal(focus.focused, true); assert.ok(parseFloat(focus.outline) >= 3); assert.equal(focus.style, 'solid');
    assert.equal(posts.length, 0);
    console.log(sky + ' Veto hover ' + JSON.stringify(hover));
  } finally { await page.close(); }
});
for (const sky of ['day', 'night']) test(sky + ' Decide empty and recovery states retain sky ink and working navigation', async () => {
  const {page, posts} = await open({sky});
  try {
    await page.evaluate(() => { state.cards = []; state.approvals = []; decide.view('decide'); });
    assert.equal(await page.locator('.decide-empty').isVisible(), true);
    const ink = sky === 'day' ? 'rgb(255, 255, 255)' : 'rgb(243, 245, 250)';
    assert.equal(await page.locator('.decide-empty h1').evaluate(e => getComputedStyle(e).color), ink);
    await page.getByRole('button', {name:'Open list', exact:true}).click();
    assert.equal(await page.locator('.v3-paper').isVisible(), true);
    await page.evaluate(() => { state.loadError = 'Fixture feed unavailable. Try again.'; decide.view('decide'); });
    assert.equal(await page.locator('.decide-recovery').isVisible(), true);
    assert.equal(await page.locator('.decide-recovery [role=alert]').evaluate(e => getComputedStyle(e).color), ink);
    assert.deepEqual((await clip(page)).clips, []);
    assert.equal(posts.length, 0);
  } finally { await page.close(); }
});
