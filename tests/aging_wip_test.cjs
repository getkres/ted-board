const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const AgingWip = fs.existsSync(require('node:path').join(__dirname, '../aging-wip.js')) ? require('../aging-wip.js') : {};

const now = Date.parse('2026-10-23T20:00:00Z');
const at = hours => new Date(now - hours * 3600000).toISOString();
const item = (id, extra = {}) => ({id, kind: 'card', card_id: id, owner: 'ted', next_action_due: at(-1), action_started_at: at(1), status: 'open', stage: 'review', priority: 1, summary: id, ...extra});
const prepare = (items, extra = {}) => AgingWip.prepare({reconciliation: {generated_at: at(0), items, ted_queue: [], banner: null}, loaded: true, now, ...extra});

test('a current empty ledger is distinct from unavailable reconciliation', () => {
  assert.equal(typeof AgingWip.prepare, 'function', 'AgingWip must expose the reconciliation view model');
  const view = prepare([]);
  assert.equal(view.available, true);
  assert.equal(view.stale, false);
  assert.deepEqual(view.items, []);
  assert.deepEqual(view.warnings, []);
});

test('every open and dead-letter item is grouped by owner, then oldest action first', () => {
  const rows = [item('new', {action_started_at: at(1)}), item('worker', {owner: 'worker:w1', action_started_at: at(4)}), item('old', {action_started_at: at(8)}), item('dead', {owner: 'external', status: 'dead_letter'}), item('closed', {status: 'done'})];
  assert.deepEqual(prepare(rows).items.map(row => row.id), ['dead', 'old', 'new', 'worker']);
  assert.equal(prepare(rows).items.find(row => row.id === 'dead').status, 'dead_letter');
});

test('action age ignores updated timestamps and worker heartbeats', () => {
  const row = prepare([item('old', {action_started_at: at(9), updated_at: at(0), heartbeat_at: at(0)})]).items[0];
  assert.equal(row.ageMs, 9 * 3600000);
  assert.equal(row.ageLabel, '9h');
  assert.equal(prepare([item('old', {action_started_at: at(9), heartbeat_at: at(-1)})]).items[0].ageMs, row.ageMs);
});

test('overdue state uses the next-action deadline, with explicit text', () => {
  const rows = prepare([item('late', {next_action_due: at(2)}), item('later')]).items;
  assert.equal(rows.find(row => row.id === 'late').overdue, true);
  assert.equal(rows.find(row => row.id === 'late').dueLabel, 'Overdue by 2h');
  assert.equal(rows.find(row => row.id === 'later').overdue, false);
});

test('missing, invalid, and future metadata stays visible as defects', () => {
  const view = prepare([item('bad', {owner: 'nobody', next_action_due: 'bad', action_started_at: at(-2)})]);
  assert.equal(view.items[0].owner, 'unknown');
  assert.equal(view.items[0].ageMs, null);
  assert.match(view.items[0].defects.join(' '), /owner.*deadline.*action start/i);
  assert.match(view.warnings.join(' '), /metadata defects/i);
});

test('stale, missing, and future reconciliation timestamps fail visibly', () => {
  for (const stamp of [at(1), null, at(-1)]) {
    const view = prepare([], {reconciliation: {generated_at: stamp, items: [], ted_queue: []}});
    assert.equal(view.stale, true);
    assert.match(view.warnings.join(' '), /reconciliation.*(stale|timestamp)/i);
  }
  assert.equal(prepare([], {reconciliation: {generated_at: new Date(now - 300000).toISOString(), items: [], ted_queue: []}}).stale, false);
  assert.equal(prepare([], {reconciliation: {generated_at: new Date(now - 300001).toISOString(), items: [], ted_queue: []}}).stale, true);
});

test('a failed refresh retains its rows but clearly reports failure', () => {
  const view = prepare([item('retained')], {loaded: false, error: 'Could not connect.'});
  assert.equal(view.items.length, 1);
  assert.match(view.warnings.join(' '), /Could not connect/);
});

test('legacy fallback includes open cards and workers without inventing deadlines', () => {
  const view = AgingWip.prepare({now, loaded: true, reconciliation: null, cards: [
    {id: 'open', title: 'Open card', section: 'up_next', updated_at: at(0)},
    {id: 'done', section: 'done'},
    {id: 'killed', section: 'killed'},
  ], jobs: [
    {id: 'w1', card_id: 'open', title: 'Worker', status: 'running', started_at: (now - 3600000) / 1000, heartbeat_at: at(0)},
    {id: 'lane', lane_summary: true, status: 'running'},
    {id: 'fresh-ted-health', status: 'running'},
    {id: 'finished', status: 'done'},
  ]});
  assert.deepEqual(view.items.map(row => row.id).sort(), ['card:open', 'job:w1']);
  assert.equal(view.items.find(row => row.kind === 'card').owner, 'unknown');
  assert.equal(view.items.find(row => row.kind === 'card').ageMs, null);
  assert.equal(view.items.find(row => row.kind === 'job').ageMs, 3600000);
  assert.ok(view.items.every(row => row.defects.includes('Missing or invalid deadline')));
  assert.match(view.warnings.join(' '), /unavailable.*coverage/i);
});

test('a missing item feed uses fallback and reports incomplete coverage', () => {
  const view = AgingWip.prepare({now, loaded: true, reconciliation: {generated_at: at(0)}, cards: [{id: 'open', section: 'ted_doing'}]});
  assert.equal(view.available, false);
  assert.equal(view.items.length, 1);
  assert.match(view.warnings.join(' '), /coverage/i);
});

test('Ted review queue resolves IDs, sorts oldest first, and has a six-hour SLA', () => {
  const view = prepare([item('new', {action_started_at: at(2)}), item('old', {action_started_at: at(7)}), item('worker', {owner: 'worker:w1'})], {
    reconciliation: {generated_at: at(0), items: [item('new', {action_started_at: at(2)}), item('old', {action_started_at: at(7)})], ted_queue: ['new', 'old'], banner: null},
  });
  assert.deepEqual(view.tedQueue.map(row => row.id), ['old', 'new']);
  assert.equal(view.tedQueue[0].reviewOverdue, true);
  assert.equal(view.tedQueue[1].reviewOverdue, false);
  assert.equal(view.tedQueue[0].reviewLabel, 'Review overdue by 1h');
});

test('unresolvable queue entries stay visible as coverage defects', () => {
  const view = prepare([], {reconciliation: {generated_at: at(0), items: [], ted_queue: ['missing']}});
  assert.equal(view.tedQueue.length, 1);
  assert.equal(view.tedQueue[0].id, 'missing');
  assert.match(view.warnings.join(' '), /queue.*missing/i);
});

test('12-hour work raises a board-wide banner without hiding publisher text', () => {
  assert.match(prepare([item('stuck', {action_started_at: at(12)})]).banner, /12 hours|12h/);
  assert.equal(prepare([item('new')]).banner, '');
  assert.equal(prepare([], {reconciliation: {generated_at: at(0), items: [], ted_queue: [], banner: {active: true, message: 'Ted review is overdue.'}}}).banner, 'Ted review is overdue.');
});

test('source data is not mutated, and text remains plain data', () => {
  const rows = [item('<img src=x onerror=alert(1)>')];
  const before = JSON.stringify(rows);
  const view = prepare(rows);
  assert.equal(view.items[0].summary, rows[0].summary);
  assert.equal(JSON.stringify(rows), before);
});

test('an out-of-range legacy worker start becomes an explicit age defect', () => {
  const view = AgingWip.prepare({now, loaded: true, jobs: [{id: 'bad-start', status: 'running', started_at: 1e30}]});
  assert.equal(view.items[0].ageMs, null);
  assert.ok(view.items[0].defects.includes('Missing or invalid action start'));
});

test('timestamps without a time zone are metadata defects', () => {
  const view = prepare([item('ambiguous', {action_started_at: '2026-10-23T19:00:00', next_action_due: '2026-10-23T21:00:00'})]);
  assert.equal(view.items[0].ageMs, null);
  assert.equal(view.items[0].dueAt, null);
});

test('fresh partial reconciliation explicitly reports incomplete feed coverage', () => {
  const view = prepare([], {reconciliation: {generated_at: at(0), items: [], ted_queue: [], coverage_defects: ['sessions', 'github']}});
  assert.equal(view.stale, false);
  assert.match(view.warnings.join(' '), /Incomplete reconciliation coverage.*sessions.*github/);
});
