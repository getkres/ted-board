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
const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1000"><rect width="800" height="1000" fill="#091d2b"/><rect x="54" y="70" width="692" height="860" rx="30" fill="#f1e9da"/><text x="105" y="175" font-family="Georgia" font-size="48" fill="#193548">A good chapter.</text><rect x="105" y="230" width="590" height="300" rx="15" fill="#bed2c4"/><path d="M145 470L300 290L430 430L540 340L660 470" fill="#427165"/><rect x="105" y="590" width="430" height="22" fill="#87958b"/><rect x="105" y="640" width="530" height="15" fill="#ccd0c6"/><rect x="105" y="680" width="480" height="15" fill="#ccd0c6"/><rect x="105" y="770" width="590" height="80" rx="14" fill="#193548"/><text x="290" y="820" font-family="sans-serif" font-size="26" fill="white">Keep reading</text></svg>';
let server, browser, passes = 0, failures = [];
async function scenario(name, mobile, run, setup = {}) {
  if (process.env.SCENARIO && !name.includes(process.env.SCENARIO)) return;
  const ctx = await browser.newContext({viewport: mobile ? {width: 390, height: 844} : {width: 1440, height: 1000}, isMobile: mobile, hasTouch: mobile, reducedMotion: 'reduce'});
  const page = await ctx.newPage(), errors = [], unexpected = [], posts = [];
  page.setDefaultTimeout(6000);
  page.on('pageerror', e => errors.push(e.message));
  const state = {images: fixtures(), pins: [], delay: 40, fail: false, enabled:true, ...setup};
  await page.clock.install({time: now});
  await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.hostname === '127.0.0.1') return route.continue();
    if (url.hostname === 'image.test') return route.fulfill({body: svg, contentType: 'image/svg+xml'});
    if (url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') return route.fulfill({body: '', contentType: 'text/css'});
    if (url.pathname.endsWith('/ted-board')) return route.fulfill({json: url.searchParams.has('resource') ? {jobs: [], approvals: []} : {cards: []}});
    if (!url.pathname.endsWith('/ted-mockups')) { unexpected.push(request.url()); return route.abort(); }
    if (request.method() === 'GET') return route.fulfill({json: {mockups: state.images, pins: state.pins, verdicts_enabled: true, verdict_batch_enabled: true, verdict_project_enabled:true, whole_image_comments_enabled:state.enabled}});
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
    if (body.action === 'pin') { const pin = {id:uuid(1000 + posts.length),mockup_id:body.mockup_id,whole_image:body.whole_image === true,x:.5,y:.5,resolved:false,thread:[{who:'seb',text:body.text,at:new Date().toISOString()}]}; state.pins.push(pin); return route.fulfill({json:{ok:true,pin}}); }
    if (body.action === 'reply') { const pin=state.pins.find(p=>p.id===body.pin_id); pin.thread.push({who:'seb',text:body.text,at:new Date().toISOString()}); return route.fulfill({json:{ok:true,pin}}); }
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
    await scenario('Enter sends semantic whole-image comment without a point marker', mobile, async ({page,card,posts}) => {
      const input = card(4).getByRole('textbox', {name:'Comment on whole image'});
      await input.fill('test-spacing looks off'); await input.press('Shift+Enter'); await input.press('a');
      assert.equal(await input.inputValue(), 'test-spacing looks off\na');
      await input.dispatchEvent('keydown',{key:'Enter',isComposing:true}); assert.equal(posts.length,0);
      await input.dispatchEvent('compositionstart'); await input.dispatchEvent('keydown',{key:'Enter'}); assert.equal(posts.length,0); await input.dispatchEvent('compositionend');
      await input.press('Enter'); await page.waitForFunction(() => !mockups.busy.size);
      assert.equal(posts.length,1); assert.equal(posts[0].whole_image,true); assert.equal('x' in posts[0],false); assert.equal('y' in posts[0],false);
      assert.equal(await input.inputValue(),''); assert.equal(await card(4).locator('.mockup-pin').count(),0);
      await card(4).locator('.mockup-quick-thread').getByText('test-spacing looks off\na',{exact:true}).waitFor();
      await card(4).getByRole('button',{name:'Open whole-image thread'}).click();
      assert.equal(await page.locator('.mockup-canvas .mockup-pin').count(),0);
      await page.getByRole('heading',{name:/Whole image/}).waitFor();
      await page.locator('.mockup-panel textarea').fill('test-another thought in this thread'); await page.getByRole('button',{name:'Send reply',exact:true}).click(); await page.waitForFunction(()=>!mockups.busy.size);
      assert.equal(posts[1].action,'reply'); assert.equal(posts[1].pin_id,uuid(1001));
    });
    await scenario('Draft isolation refresh focus selection and verdict independence', mobile, async ({page,card,positions,samePositions}) => {
      const input=card(4).getByRole('textbox',{name:'Comment on whole image'});
      await input.fill('test-retain quick draft'); await card(4).getByRole('button',{name:'Needs work',exact:true}).click();
      const note=card(4).getByRole('textbox',{name:"What's off? (optional)",exact:true}); await note.fill('test-verdict note');
      await input.evaluate(e=>{e.focus({preventScroll:true});e.setSelectionRange(5,10);}); const before=await positions();
      await page.evaluate(()=>mockups.load()); await samePositions(before);
      assert.equal(await input.inputValue(),'test-retain quick draft'); assert.equal(await note.inputValue(),'test-verdict note');
      assert.deepEqual(await input.evaluate(e=>[e===document.activeElement,e.selectionStart,e.selectionEnd]),[true,5,10]);
      assert.equal(await card(5).getByRole('textbox',{name:'Comment on whole image'}).inputValue(),'');
      await card(4).getByRole('button',{name:'Undo',exact:true}).click(); await page.waitForFunction(()=>!mockups.busy.size);
      assert.equal(await input.inputValue(),'test-retain quick draft');
    });
    await scenario('Failure late edits and single busy block All clear', mobile, async ({page,state,card,posts}) => {
      state.delay=350; state.fail=true; const input=card(4).getByRole('textbox',{name:'Comment on whole image'});
      await input.fill('test-keep failure'); await input.press('Enter');
      assert.equal(await card(4).getByRole('button',{name:'Send',exact:true}).isDisabled(),true);
      assert.equal(await page.locator('.mockup-all-clear').first().isDisabled(),true);
      await input.press('Enter'); await page.waitForFunction(()=>!mockups.busy.size); assert.equal(posts.length,1);
      assert.equal(await input.inputValue(),'test-keep failure'); await card(4).locator('.mockup-quick-status').getByText(/test-save failed/).waitFor();
      state.fail=false; await input.press('Enter'); await input.fill('test-newer draft'); await input.evaluate(e=>e.setSelectionRange(5,10)); const top=await page.evaluate(()=>scrollY); await page.waitForFunction(()=>!mockups.busy.size);
      assert.deepEqual(await input.evaluate(e=>[e===document.activeElement,e.selectionStart,e.selectionEnd]),[true,5,10]); assert.ok(Math.abs(await page.evaluate(()=>scrollY)-top)<2);
      assert.equal(await input.inputValue(),'test-newer draft'); assert.equal(posts.length,2);
    });

    await scenario('Whole comments participate in Open pins and both All clear scopes', mobile, async ({page,state,card}) => {
      state.pins=[{id:uuid(2001),mockup_id:uuid(4),whole_image:true,x:.5,y:.5,resolved:false,thread:[{who:'seb',text:'test-review this image',at:new Date().toISOString()}]}];
      await page.evaluate(()=>mockups.load()); await card(4).getByText('1 open pin',{exact:true}).waitFor();
      await page.getByRole('combobox',{name:'Filter mockups by project'}).selectOption('Bookish');
      await page.getByRole('button',{name:/Open pins/}).click(); assert.equal(await page.locator('.mockup-card').count(),1);
      const snapshot=await page.evaluate(()=>({batch:mockups.batchSnapshot('Bookish','test-shared batch').eligible.map(m=>m.id),project:mockups.batchSnapshot('Bookish').eligible.map(m=>m.id)}));
      assert.equal(snapshot.batch.includes(uuid(4)),false); assert.equal(snapshot.project.includes(uuid(4)),false);
      await page.getByRole('button',{name:'Project All clear',exact:true}).click(); await page.locator('.mockup-batch-confirm').getByText('1 with open pins stay put.',{exact:true}).waitFor(); await page.getByRole('button',{name:'Cancel',exact:true}).click();
      await page.locator('.mockup-all-clear').click(); await page.locator('.mockup-batch-confirm').getByText('1 with open pins stay put.',{exact:true}).waitFor(); await page.getByRole('button',{name:'Cancel',exact:true}).click();
      state.pins[0].resolved=true; await page.evaluate(()=>mockups.load()); assert.equal(await page.locator('.mockup-card').count(),0);
      await page.getByRole('button',{name:/Open pins/}).click(); await card(4).getByText('Whole image · Resolved',{exact:true}).waitFor();
      const eligible=await page.evaluate(()=>mockups.batchSnapshot('Bookish').eligible.map(m=>m.id)); assert.equal(eligible.includes(uuid(4)),true);
      state.images.find(m=>m.id===uuid(4)).status='archived'; await page.evaluate(()=>mockups.load()); assert.equal(await card(4).count(),0);
    });
    await scenario('Missing capability fails closed and pending verdict keeps quick draft', mobile, async ({page,state,card,posts}) => {
      const input=card(4).getByRole('textbox',{name:'Comment on whole image'}); await input.fill('test-keep while verdict pending');
      state.delay=350; await card(4).getByRole('button',{name:'Good to go',exact:true}).click(); await input.press('Enter');
      await page.waitForFunction(()=>!mockups.busy.size); assert.equal(posts.length,1); assert.equal(await input.inputValue(),'test-keep while verdict pending');
      await input.press('Enter'); await page.waitForFunction(()=>!mockups.busy.size); await card(4).getByRole('button',{name:'Undo',exact:true}).click(); await page.waitForFunction(()=>!mockups.busy.size);
      assert.equal(await card(4).locator('.mockup-quick-thread').count(),1);
      state.enabled=undefined; await page.evaluate(()=>mockups.load()); await input.fill('test-do not send old setup'); await input.press('Enter');
      assert.equal(posts.length,3); assert.equal(await card(4).getByRole('button',{name:'Send',exact:true}).isDisabled(),true);
    });
    await scenario('Character bounds capability gate and compact safe thread preview', mobile, async ({page,state,card,posts,settle}) => {
      const input=card(4).getByRole('textbox',{name:'Comment on whole image'}); await input.fill('test-'+ 'x'.repeat(1195)); await input.press('End'); await input.press('a'); assert.equal((await input.inputValue()).length,1200); await input.press('Enter'); await page.waitForFunction(()=>!mockups.busy.size); assert.equal(posts[0].text.length,1200);
      await input.evaluate(e=>{e.value='test-'+ 'x'.repeat(1196);e.dispatchEvent(new Event('input',{bubbles:true}));});
      await input.press('Enter'); assert.equal(posts.length,1); await card(4).locator('.mockup-quick-status').getByText(/1,200/).waitFor();
      state.enabled=false; await page.evaluate(()=>mockups.load()); assert.equal(await card(4).getByRole('button',{name:'Send',exact:true}).isDisabled(),true);
      assert.equal((await input.inputValue()).length,1201);
      state.enabled=true; state.pins[0].thread.push({who:'ted',text:'test-<img src=x onerror=alert(1)> Fixed spacing.',at:new Date().toISOString()},{who:'seb',text:'test-Thanks, one more thought.',at:new Date().toISOString()}); await page.evaluate(()=>mockups.load());
      assert.equal(await card(4).locator('.mockup-quick-thread img').count(),0); await card(4).getByText('test-<img src=x onerror=alert(1)> Fixed spacing.',{exact:true}).waitFor();
      state.pins[0].thread=[{who:'seb',text:'test-Give the title more breathing room.',at:new Date().toISOString()},{who:'ted',text:'test-Updated the spacing. Ready for another look.',at:new Date().toISOString()}]; await page.evaluate(()=>mockups.load());
      await input.fill('test-A little more room around the title.'); await input.scrollIntoViewIfNeeded();
      const dir=path.join(__dirname,'screenshots'); fs.mkdirSync(dir,{recursive:true}); await page.screenshot({path:path.join(dir,'quick-comment-'+(mobile?'phone':'desktop')+'.png')});
      await input.fill(''); await input.evaluate(e=>e.blur()); await card(4).locator('.mockup-quick-comment').evaluate((e,mobile)=>scrollBy(0,e.getBoundingClientRect().top-(mobile?280:430)),mobile); await settle(); await page.screenshot({path:path.join(dir,'quick-thread-'+(mobile?'phone':'desktop')+'.png')});
    });
  }
  console.log(passes+' quick comment scenarios passed; '+failures.length+' failed. No live API requests.');
  if(failures.length)process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)server.close();});
