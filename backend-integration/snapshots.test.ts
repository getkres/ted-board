import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateSnapshotPush, validateReviewChoice, handleSnapshotAction } from './snapshots.ts';

const generated_at = '2026-10-21T12:00:00.000Z';
const row = {kind:'routines', key:'daily', generated_at, payload:{routines:[],review_items:[]}};
const now = Date.parse('2026-10-21T12:01:00.000Z');
test('accepts bounded snapshots and strips unknown envelope fields', () => {
  assert.deepEqual(validateSnapshotPush({snapshots:[row], key:'do not retain'}, now), [row]);
});
test('rejects unknown kinds, duplicate keys, secrets, malformed rows, and oversized payloads', () => {
  for (const bad of [
    {...row,kind:'other'}, {...row,generated_at:'tomorrow'},
    {...row,generated_at:'2099-01-01T00:00:00Z'},
    {...row,payload:{routines:'not rows'}},
    {...row,payload:{routines:[],review_items:[{api_key:'private'}]}},
    {...row,payload:{routines:[],padding:'x'.repeat(300000)}},
  ]) assert.throws(()=>validateSnapshotPush({snapshots:[bad]},now));
  assert.throws(()=>validateSnapshotPush({snapshots:[row,row]},now));
});
test('prevents money, sends, and database writes from appearing as automatic decisions', () => {
  for (const kind of ['money_out','send','database_write']) {
    assert.throws(()=>validateSnapshotPush({snapshots:[{...row,kind:'decisions',payload:{decisions:[{id:'d1',status:'proposed',decision_kind:kind}]}}]},now));
  }
});
test('review choices require an idempotency UUID and an exact allowed choice', () => {
  const choice={item_id:'bookmark-1',choice:'keep',operation_id:'0a25893a-926c-4c3d-9f92-f15c7785146d'};
  assert.deepEqual(validateReviewChoice(choice),choice);
  assert.throws(()=>validateReviewChoice({...choice,choice:'delete'}));
  assert.throws(()=>validateReviewChoice({...choice,operation_id:'retry'}));
});
test('accepts the frontend items contract for line-keyed feeds', () => {
  const snapshots=['routines','pods','roadmap','decisions'].map(kind=>({...row,kind,key:'luvo',payload:{items:[]}}));
  assert.equal(validateSnapshotPush({snapshots},now).length,4);
});
test('resource snapshots exposes capabilities without accepting a body-supplied role', async () => {
  const store={read:async()=>[row],push:async()=>{}};
  const result=await handleSnapshotAction({method:'GET',resource:'snapshots',principal:'page'},store);
  assert.equal(result.status,200);
  assert.deepEqual(result.body.capabilities,{snapshots:true,review_choice:false});
  const forged=await handleSnapshotAction({method:'POST',body:{action:'snapshot_push',principal:'worker',snapshots:[row]},principal:'page'},store);
  assert.equal(forged.status,403);
});
test('page keys cannot push snapshots and workers cannot submit page review choices', async () => {
  const forbiddenStore={read:async()=>{throw Error('must not read')},push:async()=>{throw Error('must not write')}};
  const push=await handleSnapshotAction({method:'POST',body:{action:'snapshot_push',snapshots:[row]},principal:'page'},forbiddenStore);
  assert.equal(push.status,403);
  const review=await handleSnapshotAction({method:'POST',body:{action:'review_choice'},principal:'worker'},forbiddenStore);
  assert.equal(review.status,403);
  const unauth=await handleSnapshotAction({method:'GET',scope:'snapshots',principal:null},forbiddenStore);
  assert.equal(unauth.status,401);
});
test('missing schema degrades to an empty feed, but operational database errors stay visible', async () => {
  const missing={read:async()=>{throw {code:'42P01'}},push:async()=>{}};
  const result=await handleSnapshotAction({method:'GET',scope:'snapshots',principal:'page'},missing);
  assert.equal(result.status,200);
  assert.deepEqual(result.body,{snapshots:[],capabilities:{snapshots:false,review_choice:false}});
  const broken={read:async()=>{throw {code:'08006',message:'private connection detail'}},push:async()=>{}};
  const failure=await handleSnapshotAction({method:'GET',scope:'snapshots',principal:'page'},broken);
  assert.equal(failure.status,503);
  assert.equal(JSON.stringify(failure).includes('private connection'),false);
});
