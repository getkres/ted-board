const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../sky.js'), 'utf8');

function boot({deniedRead = false, deniedWrite = false, reduced = false, dark = false, saved = {}} = {}) {
  const nodes = [], hooks = {}, store = new Map(Object.entries(saved)), queries = {};
  class Element {
    constructor(tag) {
      this.tagName = tag; this.children = []; this.dataset = {}; this.attrs = {}; this.events = {}; this.style = {setProperty() {}};
      this.classList = {values: new Set(), toggle: (c, on) => on ? this.classList.values.add(c) : this.classList.values.delete(c)};
      nodes.push(this);
    }
    append(...xs) { for (const x of xs) { this.children.push(x); if (x && typeof x === 'object') x.parent = this; } }
    prepend(...xs) { this.children.unshift(...xs); }
    setAttribute(k, v) { this.attrs[k] = v; }
    addEventListener(k, f) { this.events[k] = f; }
    focus() { this.focused = true; }
  }
  const root = new Element('html'), host = new Element('div'), body = new Element('body'); host.className = 'ted-controls';
  const document = {documentElement: root, body, readyState: 'loading', querySelectorAll: () => [], createElement: t => new Element(t), createTextNode: t => ({textContent: t}), querySelector: s => nodes.find(n => '.' + n.className === s) || null, addEventListener: (k, f) => hooks[k] = f};
  const context = {document, window: {}, innerWidth: 1440, innerHeight: 900,
    matchMedia: q => queries[q] = {matches: q.includes('reduced-motion') ? reduced : dark, addEventListener(k, f) { this.change = f; }},
    localStorage: {getItem(k) { if (deniedRead) throw Error('denied'); return store.get(k) ?? null; }, setItem(k, v) { if (deniedWrite) throw Error('denied'); store.set(k, v); }},
    addEventListener: (k, f) => hooks[k] = f};
  vm.runInNewContext(source, context); hooks.DOMContentLoaded();
  return {nodes, context, root, hooks, store, queries, still: nodes.find(n => n.className === 'sky-still-toggle'), radios: nodes.filter(n => n.attrs.role === 'radio')};
}
function key(node, value) {
  const event = {key: value, prevented: false, stopped: false, preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; }};
  for (let current = node; current && !event.stopped; current = current.parent) current.events?.keydown?.(event);
  return event;
}

for (const denied of [{deniedRead: true, deniedWrite: true}, {deniedWrite: true}]) {
  test('Still sky works without persistence: ' + JSON.stringify(denied), () => {
    const app = boot(denied);
    app.still.events.click(); assert.equal(app.context.window.TedSky.still(), true); assert.equal(app.still.attrs['aria-pressed'], 'true');
    app.still.events.click(); assert.equal(app.context.window.TedSky.still(), false); assert.equal(app.still.attrs['aria-pressed'], 'false');
  });
}
test('stored motion and sky choices survive a fresh page instance', () => {
  const first = boot(); first.still.events.click(); first.radios[0].events.click();
  const second = boot({saved: Object.fromEntries(first.store)});
  assert.equal(second.context.window.TedSky.still(), true); assert.equal(second.context.window.TedSky.mode(), 'night');
});
test('OS reduced motion cannot be overridden by a stored animated preference', () => {
  const app = boot({reduced: true, saved: {'ted-sky-still': '0'}});
  assert.equal(app.context.window.TedSky.still(), true); assert.equal(app.still.disabled, true);
  const query = app.queries['(prefers-reduced-motion: reduce)']; query.matches = false; query.change();
  assert.equal(app.context.window.TedSky.still(), false); assert.equal(app.still.disabled, false);
});
test('sky arrows update one selected radio and stay out of board shortcuts', () => {
  const app = boot(), event = key(app.radios[1], 'ArrowRight');
  assert.equal(app.context.window.TedSky.mode(), 'night'); assert.equal(event.stopped, true);
  assert.equal(app.radios[0].attrs['aria-checked'], 'true'); assert.equal(app.radios[0].tabIndex, 0); assert.equal(app.radios[1].tabIndex, -1);
});
test('native Enter and Space activation do not reach Mockups or card shortcuts', () => {
  const app = boot();
  for (const target of [app.still, ...app.radios]) for (const value of ['Enter', ' ', 's', '1', 'Home', 'End']) {
    const event = key(target, value); assert.equal(event.stopped, true, value + ' must stay within sky controls');
    if (['Enter', ' '].includes(value)) assert.equal(event.prevented, false, 'native button activation remains available');
  }
});
test('cross-tab preferences replace local fallback values, including storage clear', () => {
  const app = boot(); app.still.events.click();
  app.store.set('ted-sky-still', '0'); app.hooks.storage({key: 'ted-sky-still', newValue: '0'});
  assert.equal(app.context.window.TedSky.still(), false);
  app.radios[0].events.click(); app.store.clear(); app.hooks.storage({key: null, newValue: null});
  assert.equal(app.context.window.TedSky.mode(), 'day');
});
