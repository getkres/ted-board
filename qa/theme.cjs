const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium, fixture, clip} = require('./browser.cjs');

const out = process.env.QA_OUT || 'qa/pr7/theme';
const cases = [
  {name: 'system-light', system: 'light', override: null, mode: 'light'},
  {name: 'system-dark', system: 'dark', override: null, mode: 'dark'},
  {name: 'override-light', system: 'dark', override: 'light', mode: 'light'},
  {name: 'override-dark', system: 'light', override: 'dark', mode: 'dark'},
];

// Catch lost system preferences, ineffective overrides, stale Take B artwork,
// and font fallbacks while checking the real rendered fixture views.
(async () => {
  fs.mkdirSync(out, {recursive: true});
  const browser = await chromium.launch({headless: true});
  const report = [];
  try {
    for (const width of [390, 1440]) {
      for (const test of cases) {
        const page = await browser.newPage({viewport: {width, height: width === 390 ? 844 : 960}, reducedMotion: 'reduce'});
        const errors = [];
        const externalRequests = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
        // Keep the theme test independent of Google Fonts and other remote assets.
        // The fixture's later routes still intercept the synthetic backend calls.
        await page.route('**/*', route => {
          const url = new URL(route.request().url());
          if (url.origin === 'http://127.0.0.1:8763') return route.continue();
          externalRequests.push(url.href);
          return route.abort();
        });
        await fixture(page);
        await page.emulateMedia({colorScheme: test.system});
        await page.goto('http://127.0.0.1:8763/#k=fixture-only&tab=inbox');
        await page.waitForSelector('.v3-paper');
        if (test.override) await page.evaluate(mode => { document.documentElement.dataset.theme = mode; }, test.override);
        await page.evaluate(() => document.fonts.ready);
        const appearance = await page.evaluate(() => {
          const style = selector => getComputedStyle(document.querySelector(selector));
          const stamp = style('.v3-scrawl');
          const headline = style('.v3-headline');
          return {
            background: style('body').backgroundColor,
            text: style('body').color,
            colorScheme: style('html').colorScheme,
            bodyFont: style('body').fontFamily,
            guideFont: style('.step-text').fontFamily,
            displayFont: headline.fontFamily,
            displayWeight: headline.fontWeight,
            displayStretch: headline.fontStretch,
            displayCase: headline.textTransform,
            stampFont: stamp.fontFamily,
            metadataFont: style('.v3-tag').fontFamily,
            stampColor: stamp.color,
            stampBorder: stamp.borderTopStyle,
            stampBorderWidth: stamp.borderTopWidth,
            stampText: document.querySelector('.v3-scrawl').textContent,
            selectedTabBackground: style('.tab[aria-selected=true]').backgroundColor,
            selectedTabCount: style('.tab[aria-selected=true] .tab-count').color,
            loadedFonts: [...document.fonts].filter(font => font.status === 'loaded').map(font => font.family.replace(/["']/g, '')),
            oldBackgrounds: [...document.querySelectorAll('*')].filter(element => element.getClientRects().length).flatMap(element => ['', '::before', '::after'].map(pseudo => getComputedStyle(element, pseudo || null).backgroundImage)).filter(image => /lair-(paper|velvet)\.webp/.test(image)),
          };
        });
        const label = test.name + ' at ' + width;
        assert.equal(appearance.background, test.mode === 'light' ? 'rgb(255, 255, 255)' : 'rgb(17, 17, 17)', label + ' body background');
        assert.equal(appearance.text, test.mode === 'light' ? 'rgb(17, 17, 17)' : 'rgb(255, 255, 255)', label + ' body text');
        assert.equal(appearance.colorScheme, test.mode, label + ' native control scheme');
        assert.notEqual(appearance.selectedTabCount, appearance.selectedTabBackground, label + ' selected tab count stays visible');
        assert.match(appearance.bodyFont, /^['"]?Archivo['"]?(?:,|$)/, label + ' body font');
        assert.match(appearance.guideFont, /^['"]?Archivo['"]?(?:,|$)/, label + ' guided instructions font');
        assert.match(appearance.displayFont, /^['"]?Archivo['"]?(?:,|$)/, label + ' display font');
        assert.ok(Number(appearance.displayWeight) >= 800, label + ' bold display');
        assert.ok(parseFloat(appearance.displayStretch) <= 75 || /^(extra-)?condensed$/.test(appearance.displayStretch), label + ' condensed display');
        assert.equal(appearance.displayCase, 'uppercase', label + ' uppercase display');
        assert.match(appearance.stampFont, /^['"]?Archivo['"]?(?:,|$)/, label + ' stamp font');
        assert.match(appearance.metadataFont, /^['"]?Courier Prime['"]?(?:,|$)/, label + ' metadata font');
        assert.equal(appearance.stampColor, 'rgb(226, 64, 42)', label + ' exact Kres red');
        assert.equal(appearance.stampBorder, 'double', label + ' stamp border');
        assert.ok(parseFloat(appearance.stampBorderWidth) >= 3, label + ' visible double border');
        assert.equal(appearance.stampText, 'TED HANDLED 1', label + ' confirmed decision count');
        assert.ok(appearance.loadedFonts.includes('Archivo'), label + ' loaded Archivo');
        assert.ok(appearance.loadedFonts.includes('Courier Prime'), label + ' loaded Courier Prime');
        assert.deepEqual(appearance.oldBackgrounds, [], label + ' no Take B backgrounds');
        assert.equal(await page.locator('.v3-counter circle').count(), 0, label + ' flat count artwork');
        assert.ok(await page.locator('.v3-counter rect').evaluateAll(rectangles => rectangles.some(rectangle => getComputedStyle(rectangle).fill === 'rgb(226, 64, 42)')), label + ' red count artwork');
        assert.equal(await page.locator('.v3-counter svg text').textContent(), '3', label + ' needs-you count');
        assert.deepEqual(externalRequests, [], label + ' self-hosted theme assets');
        const qa = await clip(page);
        assert.deepEqual(errors, [], label + ' console');
        assert.equal(qa.scrollWidth, width, label + ' horizontal overflow');
        assert.deepEqual(qa.clips, [], label + ' clipped text');
        assert.deepEqual(qa.gradients, [], label + ' gradients');
        assert.equal(qa.emDash, false, label + ' copy punctuation');
        await page.screenshot({path: path.join(out, 'home-' + test.name + '-' + width + '.png'), fullPage: true});
        report.push({name: test.name, width, mode: test.mode, ...appearance, ...qa, errors});
        await page.evaluate(() => {
          v3.snapshots.find(snapshot => snapshot.kind === 'decisions').payload.items.push({id: 'theme-done', status: 'done', title: 'One more completed decision'});
          render();
        });
        assert.equal(await page.locator('.v3-scrawl').textContent(), 'TED HANDLED 2', label + ' updated decision count');
        await page.close();
      }
    }
    fs.writeFileSync(path.join(out, 'theme-results.json'), JSON.stringify(report, null, 2));
    console.log('Kres theme: ' + report.length + ' screenshots, system modes, explicit overrides, local fonts, and live counts pass.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
