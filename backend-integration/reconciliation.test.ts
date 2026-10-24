import test from 'node:test';
import assert from 'node:assert/strict';
import {validateReconciliationPublish, handleReconciliationAction, readReconciliation, createSupabaseReconciliationStore} from './reconciliation.ts';
const now=Date.parse('2026-10-23T20:00:00Z');
const item={id:'card:c-example',kind:'card',card_id:'c-example',owner:'ted',next_action_due:'2026-10-23T21:00:00Z',action_started_at:'2026-10-23T19:00:00Z',status:'open',stage:'review',priority:1,summary:'Review the result',expected_updated_at:'2026-10-23T19:00:00Z'};
const packet=()=>({generated_at:'2026-10-23T20:00:00Z',items:[{...item}],banner:false,ted_queue:['card:c-example']});
test('accepts bounded typed ledger fields and strips the authentication envelope',()=>{
 assert.deepEqual(validateReconciliationPublish({...packet(),action:'reconcile_publish',key:'private-auth'},now),packet());
});
test('rejects invalid owners, unguarded card metadata, impossible dates, unknown fields, and duplicate identities',()=>{
 for(const change of [{owner:''},{owner:'worker:'},{owner:'browser'},{next_action_due:null},{next_action_due:'2026-02-30T00:00:00Z'},{expected_updated_at:undefined},{priority:3},{secret:'private'},{status:'closed'}]){
  assert.throws(()=>validateReconciliationPublish({...packet(),items:[{...item,...change}]},now));
 }
 assert.throws(()=>validateReconciliationPublish({...packet(),items:[item,item]},now));
 assert.throws(()=>validateReconciliationPublish({...packet(),generated_at:'2026-10-23T20:06:00Z'},now));
 assert.throws(()=>validateReconciliationPublish({...packet(),items:[{...item,action_started_at:'2026-10-23T20:01:00Z'}]},now));
});
test('queue references only distinct Ted-owned published entities',()=>{
 for(const ted_queue of [['missing'],['card:c-example','card:c-example']])assert.throws(()=>validateReconciliationPublish({...packet(),ted_queue},now));
 assert.throws(()=>validateReconciliationPublish({...packet(),items:[{...item,owner:'sebastian'}]},now));
});
test('links from non-card items do not require metadata mutation guards',()=>{
 const {expected_updated_at,...job}={...item,id:'job:j1',kind:'job',owner:'worker:j1'};
 assert.equal(validateReconciliationPublish({...packet(),items:[job],ted_queue:[]},now).items[0].kind,'job');
});
test('page and absent credentials cannot publish, even with a forged body principal',async()=>{
 const store={read:async()=>null,publish:async()=>{throw Error('must not write')}};
 for(const principal of ['page',null] as const){
  const response=await handleReconciliationAction({method:'POST',principal,body:{...packet(),action:'reconcile_publish',principal:'worker'}},store,now);
  assert.equal(response?.status,403);
 }
});
test('worker publish sends a complete validated snapshot through the atomic store',async()=>{
 let persisted:unknown;
 const store={read:async()=>null,publish:async(value:unknown)=>{persisted=value;return {ok:true,applied:true}}};
 const response=await handleReconciliationAction({method:'POST',principal:'worker',body:{...packet(),action:'reconcile_publish'}},store,now);
 assert.equal(response?.status,200);assert.deepEqual(persisted,packet());
 assert.equal(await handleReconciliationAction({method:'PUT',principal:'worker',body:{action:'reconcile_publish'}},store,now),null);
});
test('schema absence, connection failures, and CAS conflicts remain explicit without private error details',async()=>{
 for(const [code,want] of [['42P01',503],['PGRST202',503],['40001',409],['22023',409],['08006',503]] as const){
  const store={read:async()=>{throw {code,message:'private database detail'}},publish:async()=>{throw {code,message:'private database detail'}}};
  const read=await readReconciliation(store);
  assert.equal(read.reconciliation,null);assert.ok(read.reconciliation_error);assert.equal(JSON.stringify(read).includes('private database'),false);
  const result=await handleReconciliationAction({method:'POST',principal:'worker',body:{...packet(),action:'reconcile_publish'}},store,now);
  assert.equal(result?.status,want);assert.equal(JSON.stringify(result).includes('private database'),false);
 }
 const empty=await readReconciliation({read:async()=>null,publish:async()=>({ok:true})});
 assert.equal(empty.reconciliation_error,'not_published');
});
test('malformed stored payload is not advertised as a healthy reconciliation',async()=>{
 const result=await readReconciliation({read:async()=>({generated_at:'invalid',items:[],ted_queue:[],banner:false}) as any,publish:async()=>({ok:true})});
 assert.equal(result.reconciliation,null);assert.equal(result.reconciliation_error,'invalid_snapshot');
});
test('adapter uses single RPC publish and one consistent read rather than per-card writes',async()=>{
 const calls:unknown[]=[];
 const client={rpc:async(name:string,args?:unknown)=>{calls.push([name,args]);return {data:name.endsWith('_read')?packet():{ok:true,applied:true},error:null}}};
 const store=createSupabaseReconciliationStore(client);
 assert.deepEqual(await store.read(),packet());await store.publish(packet() as any);
 assert.deepEqual(calls,[['ted_board_reconciliation_read',undefined],['ted_board_reconcile_publish',{p_generated_at:packet().generated_at,p_items:packet().items,p_banner:false,p_ted_queue:packet().ted_queue,p_coverage_defects:[]}]]);
});
test('only workers can route an existing Needs you card to Ted with a timestamp guard',async()=>{
 let routed:unknown;
 const store={read:async()=>null,publish:async()=>({ok:true}),routeTed:async(value:unknown)=>{routed=value;return {ok:true}}};
 const body={action:'reconcile_route_ted',card_id:'c-example',expected_section:'needs_you',expected_updated_at:'2026-10-23T19:00:00Z',line:'awaiting ted review'};
 assert.equal((await handleReconciliationAction({method:'POST',principal:'page',body},store,now))?.status,403);
 assert.equal((await handleReconciliationAction({method:'POST',principal:'worker',body:{...body,expected_section:'done'}},store,now))?.status,400);
 assert.equal((await handleReconciliationAction({method:'POST',principal:'worker',body},store,now))?.status,200);
 assert.deepEqual(routed,{card_id:'c-example',expected_section:'needs_you',expected_updated_at:'2026-10-23T19:00:00Z',line:'awaiting ted review'});
});
// The actual private handler is intentionally absent from the public repository.
// Set RECONCILIATION_HANDLER_SOURCE to the reconstructed candidate to exercise integration.
const handlerSource=process.env.RECONCILIATION_HANDLER_SOURCE;
test('private handler preserves Jobs controls and restricts reconciliation writes to the distinct worker key',{skip:!handlerSource},async()=>{
 const {pathToFileURL}=await import('node:url');
 const {createHandler}=await import(pathToFileURL(handlerSource!).href);
 const rpcCalls:string[]=[];
 const db={from:()=>{throw Error('unexpected table access')},rpc:async(name:string)=>{
  rpcCalls.push(name);
  const values:Record<string,unknown>={ted_board_jobs:{jobs:[],approvals:[],server_time:'2026-10-23T20:00:00Z'},ted_board_fresh_control:{state:'idle'},ted_board_reconciliation_read:packet(),ted_board_reconcile_publish:{ok:true,applied:true},ted_board_reconcile_route_ted:{ok:true},ted_board_reconcile_close_verified:{ok:true}};
  if(!(name in values))throw Error('unexpected RPC');
  return {data:values[name],error:null};
 }};
 assert.throws(()=>createHandler(db,'shared','shared',{enabled:false,message:'disabled'}),/Separate page and worker keys/);
 const handler=createHandler(db,'page-test','worker-test',{enabled:false,message:'disabled'});
 const read=await handler(new Request('https://example.invalid/?resource=jobs&key=page-test'));
 assert.equal(read.status,200);const jobs=await read.json();assert.deepEqual(jobs.jobs,[]);assert.equal(jobs.fresh_ted.state,'idle');assert.deepEqual(jobs.reconciliation,packet());
 const count=rpcCalls.length;
 const denied=await handler(new Request('https://example.invalid/',{method:'POST',body:JSON.stringify({...packet(),action:'reconcile_publish',key:'page-test'})}));
 assert.equal(denied.status,403);assert.equal(rpcCalls.length,count);
 const written=await handler(new Request('https://example.invalid/',{method:'POST',body:JSON.stringify({...packet(),action:'reconcile_publish',key:'worker-test'})}));
 assert.equal(written.status,200);assert.ok(rpcCalls.includes('ted_board_reconcile_publish'));
 const route=await handler(new Request('https://example.invalid/',{method:'POST',body:JSON.stringify({action:'reconcile_route_ted',key:'worker-test',card_id:'c-example',expected_section:'needs_you',expected_updated_at:item.expected_updated_at,line:'review queued'})}));
 assert.equal(route.status,200);assert.ok(rpcCalls.includes('ted_board_reconcile_route_ted'));
 const closed=await handler(new Request('https://example.invalid/',{method:'POST',body:JSON.stringify({action:'reconcile_close_verified',key:'worker-test',card_id:'c-example',expected_updated_at:item.expected_updated_at})}));
 assert.equal(closed.status,200);assert.ok(rpcCalls.includes('ted_board_reconcile_close_verified'));
});
test('degraded snapshots retain explicit bounded coverage identifiers through publish and read',async()=>{
 const degraded={...packet(),coverage_defects:['mockups','github:read']};
 assert.deepEqual(validateReconciliationPublish(degraded,now),degraded);
 assert.deepEqual((await readReconciliation({read:async()=>degraded as any,publish:async()=>({ok:true})})).reconciliation,degraded);
 for(const coverage_defects of [['private token value'],['mockups','mockups'],Array.from({length:501},(_,i)=>'source'+i)])assert.throws(()=>validateReconciliationPublish({...packet(),coverage_defects},now));
});
test('verified closure requires worker credentials, a source guard, and a configured durable evidence hook',async()=>{
 const body={action:'reconcile_close_verified',card_id:'c-example',expected_updated_at:item.expected_updated_at};
 const missing={read:async()=>null,publish:async()=>({ok:true})};
 assert.equal((await handleReconciliationAction({method:'POST',principal:'page',body},missing,now))?.status,403);
 assert.equal((await handleReconciliationAction({method:'POST',principal:'worker',body},missing,now))?.status,503);
 assert.equal((await handleReconciliationAction({method:'POST',principal:'worker',body:{...body,expected_updated_at:undefined}},missing,now))?.status,400);
 const absentEvidence={...missing,closeVerified:async()=>{throw {code:'40001'}}};
 assert.equal((await handleReconciliationAction({method:'POST',principal:'worker',body},absentEvidence,now))?.status,409);
 let request:unknown;
 const configured={...missing,closeVerified:async(value:unknown)=>{request=value;return {ok:true}}};
 assert.equal((await handleReconciliationAction({method:'POST',principal:'worker',body},configured,now))?.status,200);
 assert.deepEqual(request,{card_id:'c-example',expected_updated_at:item.expected_updated_at});
});
