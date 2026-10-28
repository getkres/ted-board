import assert from 'node:assert/strict';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import test from 'node:test';

if (!process.env.TED_STEWARD_FEED_RUNTIME) {
  throw new Error('Set TED_STEWARD_FEED_RUNTIME to the prepared private feed candidate. This suite does not run in CI.');
}
const { createHandler } = await import(pathToFileURL(path.join(process.env.TED_STEWARD_FEED_RUNTIME, 'handler.ts')));

function fixture(rows, { cardError = null, pulseError = null } = {}) {
  const reads = [];
  const db = {
    from(table) {
      reads.push(table);
      if (table === 'ted_board_pod_pulse') {
        return { select() { return this; }, eq() { return this; },
          async maybeSingle() { return { data: { pods: [] }, error: pulseError }; } };
      }
      assert.equal(table, 'ted_board_cards');
      const filters = [];
      let cap = Infinity;
      return {
        select() { return this; },
        eq(key, value) { filters.push([key, value]); return this; },
        order() { return this; },
        limit(value) { cap = value; return this; },
        then(resolve, reject) {
          const selected = rows.filter(row => filters.every(([key, value]) => row[key] === value));
          return Promise.resolve({ data: selected.slice(0, cap), error: cardError }).then(resolve, reject);
        },
      };
    },
  };
  const handler = createHandler(db, 'fixture-page', 'fixture-worker', { enabled: false, message: 'fixture' });
  const get = suffix => handler(new Request('https://board.invalid/?key=fixture-page'+suffix));
  return { get, reads };
}

const row = (id, section) => ({ id, section, project: 'Test' });

test('default GET keeps the real cards and pod_pulse contract without a POST success field', async () => {
  const rows = [row('history', 'done'), row('report', 'needs_you')];
  const response = await fixture(rows).get('');
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { cards: rows, pod_pulse: [] });
});

test('needs_you scope is applied before the cap despite more than 500 historical cards', async () => {
  const history = Array.from({ length: 600 }, (_, i) => row('done-'+i, 'done'));
  const inbox = [row('report', 'needs_you'), row('decision', 'needs_you')];
  const response = await fixture([...history, ...inbox, row('queued', 'up_next')]).get('&section=needs_you');
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { cards: inbox, pod_pulse: [] });
});

test('unscoped legacy feed still has its existing 500-row cap', async () => {
  const rows = Array.from({ length: 600 }, (_, i) => row('done-'+i, 'done'));
  const response = await fixture(rows).get('');
  assert.equal((await response.json()).cards.length, 500);
});

test('unknown or empty section filters fail explicitly without a database read', async () => {
  for (const scope of ['done', 'typo', '']) {
    const source = fixture([]);
    const response = await source.get('&section='+scope);
    assert.equal(response.status, 400);
    assert.deepEqual(source.reads, []);
  }
});

test('scoped card read errors preserve the error envelope and HTTP failure', async () => {
  const response = await fixture([], { cardError: { code: 'fixture' } }).get('&section=needs_you');
  assert.equal(response.status, 500);
  assert.deepEqual(await response.json(), { error: 'Could not load cards' });
});

test('scoped pulse degradation retains the explicit error flag for client rejection', async () => {
  const response = await fixture([row('report', 'needs_you')], { pulseError: { code: 'fixture' } }).get('&section=needs_you');
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { cards: [row('report', 'needs_you')], pod_pulse: [], pod_pulse_error: true });
});
