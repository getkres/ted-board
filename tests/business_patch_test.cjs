const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const modulePath = path.join(__dirname, '../business-patch.js');
const BusinessPatch = fs.existsSync(modulePath) ? require(modulePath) : {};
const card = (id, section, extra = {}) => ({id, section, project: 'Example', title: id, ...extra});
const prepare = (cards, extra = {}) => BusinessPatch.prepare({cards, loaded: true, approvals: [], approvalsLoaded: true, ...extra});
const ids = view => Object.fromEntries(view.groups.map(group => [group.id, group.rows.map(row => row.id)]));

test('current cards group by recorded state, with no completed cards or invented history', () => {
  const cards = [card('choice', 'needs_you'), card('next', 'up_next'), card('pending', 'ted_doing'), card('warning', 'ted_doing', {live_state: 'blocked'}), card('done', 'done'), card('killed', 'killed')];
  const before = JSON.stringify(cards);
  const view = prepare(cards);
  assert.deepEqual(ids(view), {review: ['choice'], handoff: ['next'], ted: ['pending'], alert: ['warning']});
  assert.equal(view.total, 4);
  assert.equal(view.groups[2].rows[0].status, 'Assigned to Ted');
  assert.equal(JSON.stringify(cards), before);
  assert.equal(view.warnings.length, 0);
  assert.equal('baseline' in view, false);
});

test('pending approvals take review precedence without reviving closed cards', () => {
  const view = prepare([card('pending', 'up_next', {live_state: 'blocked'}), card('closed', 'done'), card('old', 'up_next')], {
    approvals: [{card_id: 'pending', status: 'pending'}, {card_id: 'closed', status: 'pending'}, {card_id: 'old', status: 'approved'}],
  });
  assert.deepEqual(ids(view), {review: ['pending'], handoff: ['old'], ted: [], alert: []});
  assert.match(view.groups[0].rows[0].status, /Approval pending.*Blocked/);
});

test('unknown state remains visible, while prose never invents a blocker or completion', () => {
  const view = prepare([card('unknown', 'future_lane'), card('prose', 'ted_doing', {body: 'Blocked yesterday. PR merged.'}), card('legacy', 'yours')]);
  assert.deepEqual(ids(view), {review: ['legacy'], handoff: [], ted: ['prose'], alert: ['unknown']});
  assert.match(view.groups[3].rows[0].status, /Unrecognized card section/);
  assert.equal(view.groups[2].rows[0].status, 'Assigned to Ted');
});

test('duplicate and malformed identities cannot produce ambiguous actions or inflated counts', () => {
  const view = prepare([card('duplicate', 'needs_you'), card('duplicate', 'done'), null, card('', 'ted_doing'), card('valid', 'up_next')]);
  assert.equal(view.total, 1);
  assert.deepEqual(ids(view).handoff, ['valid']);
  assert.match(view.warnings.join(' '), /duplicate.*invalid/i);
});

test('missing, failed, and potentially truncated feeds cannot claim a complete snapshot', () => {
  assert.equal(BusinessPatch.prepare({cards: [], loaded: false}).available, false);
  assert.equal(BusinessPatch.prepare({cards: {}, loaded: true}).available, false);
  assert.match(prepare([], {error: 'Refresh failed.'}).warnings.join(' '), /Refresh failed.*last loaded/i);
  assert.match(prepare([], {approvalsLoaded: false}).warnings.join(' '), /Approvals.*not loaded/);
  assert.match(prepare([], {approvalsError: 'Unavailable'}).warnings.join(' '), /Approval.*refresh failed/);
  assert.match(prepare(Array.from({length: 500}, (_, i) => card('card-' + i, 'up_next'))).warnings.join(' '), /500.*incomplete/);
});

test('group order and card order stay stable across refreshes, with no retained account state', () => {
  const first = prepare([card('a', 'up_next'), card('b', 'up_next')]);
  assert.deepEqual(ids(first).handoff, ['a', 'b']);
  const other = prepare([card('new-account', 'needs_you')]);
  assert.deepEqual(ids(other), {review: ['new-account'], handoff: [], ted: [], alert: []});
});

// A small DOM contract checks text-only rendering and explicit card navigation.
// Native Chrome visual and responsive verification is a separate release check.
class Element {
  constructor(tag, doc) { this.tagName = tag; this.ownerDocument = doc; this.children = []; this.attributes = {}; this.dataset = {}; this.events = {}; this.textContent = ''; }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(key, value) { this.events[key] = value; }
  set innerHTML(_) { throw new Error('Card content must never be parsed as HTML'); }
}
const doc = {createElement(tag) { return new Element(tag, doc); }};
const all = node => [node, ...node.children.flatMap(all)];
const content = node => all(node).map(row => row.textContent).join(' ');

test('patch renders every group, states its baseline limits, and only opens the exact card', () => {
  const root = doc.createElement('div'), opened = [];
  const title = '<img src=x onerror=alert(1)>';
  BusinessPatch.render(root, prepare([card('safe-id', 'up_next', {title, body: '<script>bad()</script>'})]), {onOpenCard: id => opened.push(id)});
  const nodes = all(root);
  assert.equal(nodes.filter(node => node.tagName === 'h3').length, 4);
  assert.ok(nodes.some(node => node.textContent === title));
  assert.match(content(root), /No recorded last-visit baseline/);
  assert.match(content(root), /No completion claimed for pending handoffs/);
  const buttons = nodes.filter(node => node.tagName === 'button');
  assert.equal(buttons.length, 1);
  assert.equal(buttons[0].attributes['aria-label'], 'Open card: ' + title);
  buttons[0].events.click();
  assert.deepEqual(opened, ['safe-id']);
});

test('unavailable and empty snapshots use distinct messages', () => {
  const unavailable = doc.createElement('div'), empty = doc.createElement('div');
  BusinessPatch.render(unavailable, BusinessPatch.prepare({loaded: false, loading: true}));
  BusinessPatch.render(empty, prepare([]));
  assert.match(content(unavailable), /Loading current cards/);
  assert.doesNotMatch(content(unavailable), /No open cards/);
  assert.match(content(empty), /No open cards in the loaded snapshot/);
});

test('v3 integration reads refreshed card and approval state and opens existing card details', () => {
  const context = vm.createContext({BusinessPatch, window: {}, sessionStorage: {getItem() { return null; }}});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../v3.js'), 'utf8') + '\nthis.V3 = ControlCenterV3;', context);
  let state = {cards: [card('first', 'needs_you')], approvals: [], loaded: true, jobsLoaded: true};
  const routes = [], v3 = new context.V3({getState: () => state, getKey: () => '', select: route => routes.push(route)});
  const root = doc.createElement('div');
  const detailEvents = [], detail = {focus() { detailEvents.push('focus'); }, scrollIntoView() { detailEvents.push('scroll'); }};
  doc.querySelector = selector => selector === '.v3-detail' ? detail : null;
  v3.businessPatch(root);
  all(root).find(node => node.tagName === 'button').events.click();
  assert.equal(v3.item, 'first');
  assert.equal(v3.split, 'yours');
  assert.deepEqual(routes, ['inbox']);
  assert.equal(detail.tabIndex, -1);
  assert.deepEqual(detailEvents, ['focus', 'scroll']);
  state = {cards: [card('second', 'ted_doing')], approvals: [{card_id: 'second', status: 'pending'}], loaded: true, jobsLoaded: true};
  const refreshed = doc.createElement('div');
  v3.businessPatch(refreshed);
  assert.doesNotMatch(content(refreshed), /first/);
  assert.match(content(refreshed), /second.*Approval pending/);
  state = {cards: [], approvals: [], loaded: false, jobsLoaded: false};
  const loggedOut = doc.createElement('div');
  v3.businessPatch(loggedOut);
  assert.doesNotMatch(content(loggedOut), /second/);
});
