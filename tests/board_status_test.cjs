const assert = require('node:assert/strict');
const {doingCounts} = require('../board-status.js');

const now = Date.parse('2026-10-21T20:00:00Z');
const fresh = new Date(now - 30000).toISOString();
const old = new Date(now - 180000).toISOString();
const cards = ['running', 'queued', 'old', 'missing'].map(id => ({id, section: 'ted_doing'}));
const jobs = [
  {card_id: 'running', status: 'running', pid: 123, heartbeat_at: fresh},
  {card_id: 'queued', status: 'queued', pid: null, heartbeat_at: fresh},
  {card_id: 'old', status: 'running', pid: 456, heartbeat_at: old},
  {card_id: 'elsewhere', status: 'running', pid: 789, heartbeat_at: fresh},
];
assert.deepEqual(doingCounts(cards, jobs, true, now), {running: 1, queued: 1, stale: 2});
assert.equal(doingCounts(cards, jobs, false, now), null);
assert.deepEqual(doingCounts([{id: 'missing', section: 'ted_doing'}], [{card_id: 'missing', status: 'running', pid: null, heartbeat_at: fresh}], true, now), {running: 0, queued: 0, stale: 1});
console.log('PASS board status counts');
