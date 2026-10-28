// WCAG AA contrast for every visible text run, measured against the real rendered glass and sky.
// Method from the reference lock: hide the text, screenshot the backdrop, then take the 1st percentile
// contrast inside each run's box (single star pixels are ignored). The sky is fixed, so each view is
// measured at several scroll positions and the worst position counts.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium, fixture} = require('./browser.cjs');

const out = process.env.QA_OUT || '../qa-evidence/pr8/sky-contrast';
const views = [['inbox', 'inbox'], ['business-patch', 'inbox', 'patch'], ['decided', 'inbox', 'decided'], ['routines', 'inbox', 'routines'], ['woke', 'inbox', 'woke'], ['item', 'inbox', 'item'], ['spaces', 'spaces'], ['space', 'space:line3'], ['pod', 'pod:line3/media'], ['agent', 'agent:line3/meta-media-buyer'], ['roadmap', 'roadmap'], ['roadbiz', 'roadmap:line1'], ['mockups', 'Mockups'], ['jobs', 'Jobs'], ['decide', null]];

function runs() {
  const list = [], walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walk.nextNode())) {
    const text = node.textContent.trim();
    if (!text) continue;
    const el = node.parentElement, style = getComputedStyle(el);
    if (el.closest('script,style,svg,.sr-only,[hidden],dialog:not([open]),.priv,[aria-hidden=true]') || !el.checkVisibility({opacityProperty: true, visibilityProperty: true, contentVisibilityAuto: true})) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    for (const r of range.getClientRects()) {
      if (r.width < 2 || r.height < 4) continue;
      const size = parseFloat(style.fontSize), weight = Number(style.fontWeight) || 400;
      let path = [], a = el;
      for (let i = 0; a && i < 3; i++, a = a.parentElement) path.push(a.tagName.toLowerCase() + (a.className && typeof a.className === 'string' ? '.' + a.className.trim().split(/\s+/).join('.') : ''));
      list.push({text: text.slice(0, 60), color: style.color, size, weight, large: size >= 24 || (size >= 18.66 && weight >= 700), x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height, path: path.join(' < ')});
    }
  }
  return list;
}

async function measure(page, b64, boxes) {
  return page.evaluate(async ({b64, boxes}) => {
    const img = new Image();
    img.src = 'data:image/png;base64,' + b64;
    await img.decode();
    const canvas = document.createElement('canvas');
    canvas.width = img.width; canvas.height = img.height;
    const ctx = canvas.getContext('2d', {willReadFrequently: true});
    ctx.drawImage(img, 0, 0);
    const lin = c => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
    const lum = (r, g, b) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
    return boxes.map(box => {
      const [r, g, b, a = 1] = box.color.match(/[\d.]+/g).map(Number);
      const x0 = Math.max(0, Math.floor(box.vx)), y0 = Math.max(0, Math.floor(box.vy));
      const w = Math.min(canvas.width - x0, Math.ceil(box.w)), h = Math.min(canvas.height - y0, Math.ceil(box.h));
      if (w <= 0 || h <= 0) return null;
      const data = ctx.getImageData(x0, y0, w, h).data, ratios = [];
      for (let i = 0; i < data.length; i += 4) {
        const br = data[i], bg = data[i + 1], bb = data[i + 2];
        const lt = lum(r * a + br * (1 - a), g * a + bg * (1 - a), b * a + bb * (1 - a)), lb = lum(br, bg, bb);
        ratios.push((Math.max(lt, lb) + 0.05) / (Math.min(lt, lb) + 0.05));
      }
      ratios.sort((p, q) => p - q);
      return ratios[Math.floor(ratios.length * 0.01)];
    });
  }, {b64, boxes});
}

(async () => {
  fs.mkdirSync(out, {recursive: true});
  const browser = await chromium.launch({headless: true});
  const report = [];
  let failures = [];
  try {
    for (const sky of ['night', 'day']) for (const width of [390, 1440]) for (const [name, tab, split] of views) {
      const height = width === 390 ? 844 : 960;
      const page = await browser.newPage({viewport: {width, height}, reducedMotion: 'reduce'});
      await page.addInitScript(mode => { try { localStorage.setItem('ted-sky', mode); } catch {} }, sky);
      await fixture(page);
      await page.goto('http://127.0.0.1:8763/' + (tab === null ? '?view=decide' : '') + '#k=fixture-only&tab=inbox');
      await page.waitForSelector('.v3-paper,.decide-shell');
      if (tab !== null) {
        await page.evaluate(route => selectProject(route), tab);
        if (split === 'patch') { await page.evaluate(() => { state.cards.push({id:'patch-next',section:'up_next',project:'Fixture',title:'Next handoff'},{id:'patch-ted',section:'ted_doing',project:'Fixture',title:'Assigned work'},{id:'patch-alert',section:'up_next',live_state:'blocked',project:'Fixture',title:'Blocked fixture'}); render(); }); await page.locator('.v3-business-patch>summary').click(); }
        else if (split === 'item') { await page.locator('[data-split="yours"]').click(); await page.locator('[data-open-card="money"]').click(); }
        else if (split) await page.locator('[data-split="' + split + '"]').click();
      }
      await page.evaluate(() => document.fonts.ready);
      // Keep scrolling from moving controls under a stationary pointer and changing hover colors mid-measurement.
      await page.mouse.move(1, 1);
      await page.waitForTimeout(150);
      const text = await page.evaluate(runs);
      await page.addStyleTag({content: '*,*::placeholder{color:transparent!important;text-shadow:none!important;-webkit-text-stroke:0!important;caret-color:transparent!important;text-decoration-color:transparent!important}'});
      const docHeight = await page.evaluate(() => document.documentElement.scrollHeight);
      const worst = new Map();
      for (let y = 0; y < docHeight; y += height / 2) {
        const scrollY = await page.evaluate(top => { scrollTo(0, top); return scrollY; }, y);
        await page.waitForTimeout(40);
        const shot = (await page.screenshot()).toString('base64');
        const inView = text.map((t, i) => ({...t, i, vx: t.x, vy: t.y - scrollY})).filter(t => t.vy >= 0 && t.vy + t.h <= height);
        const ratios = await measure(page, shot, inView);
        inView.forEach((t, k) => { if (ratios[k] != null) worst.set(t.i, Math.min(worst.get(t.i) ?? Infinity, ratios[k])); });
        if (scrollY + height >= docHeight) break;
      }
      const rows = text.map((t, i) => ({...t, ratio: worst.has(i) ? Number(worst.get(i).toFixed(2)) : null, need: t.large ? 3 : 4.5})).filter(r => r.ratio != null);
      const fails = rows.filter(r => r.ratio < r.need);
      const min = rows.reduce((m, r) => Math.min(m, r.ratio / r.need), Infinity);
      report.push({view: name, sky, width, checked: rows.length, fails: fails.length, worstSmall: Math.min(...rows.filter(r => !r.large).map(r => r.ratio)), worstLarge: Math.min(...rows.filter(r => r.large).map(r => r.ratio)), margin: Number(min.toFixed(2)), failRows: fails.map(({text, ratio, need, path, color}) => ({text, ratio, need, color, path}))});
      failures = failures.concat(fails.map(f => `${name} ${sky} ${width}: "${f.text}" ${f.ratio} < ${f.need} (${f.path})`));
      await page.close();
    }
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(out, 'sky-contrast.json'), JSON.stringify(report, null, 1));
  }
  const checked = report.reduce((n, r) => n + r.checked, 0);
  if (failures.length) console.log(failures.slice(0, 80).join('\n'));
  assert.deepEqual(failures, [], failures.length + ' text runs fail WCAG AA');
  console.log(`Sky contrast: ${checked} text runs across ${report.length} views, both skies, 390 and 1440, 0 below AA. Worst small ${Math.min(...report.map(r => r.worstSmall)).toFixed(2)}:1, worst large ${Math.min(...report.map(r => r.worstLarge)).toFixed(2)}:1.`);
})().catch(error => { console.error(error.message || error); process.exit(1); });
