import test from 'node:test';
import assert from 'node:assert/strict';
import {validateReconciliationPublish, handleReconciliationAction, readReconciliation, createSupabaseReconciliationStore} from './reconciliation.ts';
const now=Date.parse('2026-10-23T20:00:00Z');
const item={id:'card:c-example',kind:'card',card_id:'c-example',owner:'ted',next_action_due:'2026-10-23T21:00:00Z',action_started_at:'2026-10-23T19:00:00Z',status:'open',stage:'review',priority:1,summary:'Review the result',expected_updated_at:'2026-10-23T19:00:00Z'};
const packet=()=>({generated_at:'2026-10-23T20:00:00Z',items:[{...item}],banner:false,ted_queue:['card:c-example']});
test('accepts bounded typed ledger fields and strips the authentication envelope',()=>{
 assert.deepEqual(validateReconciliationPublish({...packet(),action:'reconcile_publish',key:'private-auth'},now),packet());
});
test('quarantines invalid rows and rejects invalid snapshot envelopes',()=>{
 for(const change of [{owner:''},{owner:'worker:'},{owner:'browser'},{next_action_due:null},{next_action_due:'2026-02-30T00:00:00Z'},{expected_updated_at:undefined},{priority:3},{secret:'private'},{status:'closed'}]){
  const result=validateReconciliationPublish({...packet(),items:[{...item,...change}]},now);
  assert.deepEqual(result.items,[]);assert.ok(result.coverage_defects?.includes('item_row:0'));
 }
 assert.equal(validateReconciliationPublish({...packet(),items:[item,item]},now).items.length,1);
 assert.throws(()=>validateReconciliationPublish({...packet(),generated_at:'2026-10-23T20:06:00Z'},now));
 assert.deepEqual(validateReconciliationPublish({...packet(),items:[{...item,action_started_at:'2026-10-23T20:01:00Z'}]},now).items,[]);
});
test('queue references only distinct Ted-owned published entities',()=>{
 for(const ted_queue of [['missing'],['card:c-example','card:c-example']])assert.ok(validateReconciliationPublish({...packet(),ted_queue},now).coverage_defects?.some(x=>x.startsWith('queue_row:')));
 assert.deepEqual(validateReconciliationPublish({...packet(),items:[{...item,owner:'sebastian'}]},now).ted_queue,[]);
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
test('non-retryable PT409 business guards remain HTTP409 for all reconciliation writes',async()=>{
 const store={read:async()=>null,publish:async()=>{throw {code:'PT409',message:'private guard detail'}},routeTed:async()=>{throw {code:'PT409',message:'private guard detail'}},closeVerified:async()=>{throw {code:'PT409',message:'private guard detail'}}};
 const guard={card_id:'c-example',expected_updated_at:item.expected_updated_at,expected_revision:4,expected_section:'needs_you',expected_messages:[]};
 for(const action of ['reconcile_publish','reconcile_route_ted','reconcile_close_verified']){
  const result=await handleReconciliationAction({method:'POST',principal:'worker',body:{...packet(),...guard,action}},store,now);
  assert.equal(result?.status,409);assert.equal(JSON.stringify(result).includes('private guard detail'),false);
 }
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
test('only workers can route an existing Needs you card with timestamp, revision, and messages guards',async()=>{
 let routed:unknown;
 const store={read:async()=>null,publish:async()=>({ok:true}),routeTed:async(value:unknown)=>{routed=value;return {ok:true}}};
 const body={action:'reconcile_route_ted',card_id:'c-example',expected_section:'needs_you',expected_updated_at:'2026-10-23T19:00:00Z',expected_revision:7,expected_messages:[],line:'awaiting ted review'};
 assert.equal((await handleReconciliationAction({method:'POST',principal:'page',body},store,now))?.status,403);
 assert.equal((await handleReconciliationAction({method:'POST',principal:'worker',body:{...body,expected_section:'done'}},store,now))?.status,400);
 assert.equal((await handleReconciliationAction({method:'POST',principal:'worker',body},store,now))?.status,200);
 assert.deepEqual(routed,{card_id:'c-example',expected_section:'needs_you',expected_updated_at:'2026-10-23T19:00:00Z',expected_revision:7,expected_messages:[],line:'awaiting ted review'});
});
test('routing rejects missing or malformed observation guards before the store is called',async()=>{
 let writes=0;
 const store={read:async()=>null,publish:async()=>({ok:true}),routeTed:async()=>{writes++;return {ok:true}}};
 const body={action:'reconcile_route_ted',card_id:'c-example',expected_section:'needs_you',expected_updated_at:item.expected_updated_at,expected_revision:1,expected_messages:[]};
 const changes=[...[undefined,null,0,-1,1.5,'1',Number.MAX_SAFE_INTEGER+1,Infinity].map(expected_revision=>({expected_revision})),...[undefined,null,{},'[]'].map(expected_messages=>({expected_messages}))];
 for(const change of changes){
  const response=await handleReconciliationAction({method:'POST',principal:'worker',body:{...body,...change}},store,now);
  assert.equal(response?.status,400,JSON.stringify(change));
 }
 assert.equal(writes,0);
});
test('route adapter forwards the complete observed revision and messages to the exact RPC',async()=>{
 const expected_messages=[{who:'ted',text:'Review the PR\nKeep the C:\\fixture path and 東京 text.',at:item.expected_updated_at}];
 const value={card_id:'c-example',expected_section:'needs_you' as const,expected_updated_at:item.expected_updated_at!,expected_revision:12,expected_messages,line:'review queued'};
 const calls:unknown[]=[];
 const store=createSupabaseReconciliationStore({rpc:async(name,args)=>{calls.push([name,args]);return {data:{ok:true},error:null}}});
 await store.routeTed!(value);
 assert.deepEqual(calls,[['ted_board_reconcile_route_ted',{p_card_id:value.card_id,p_expected_updated_at:value.expected_updated_at,p_expected_section:'needs_you',p_line:'review queued',p_expected_revision:12,p_expected_messages:expected_messages}]]);
});
test('route conflicts remain 409 without dropping the observation guards',async()=>{
 let seen:unknown;
 const body={action:'reconcile_route_ted',card_id:'c-example',expected_section:'needs_you',expected_updated_at:item.expected_updated_at,expected_revision:2,expected_messages:[]};
 const store={read:async()=>null,publish:async()=>({ok:true}),routeTed:async(value:unknown)=>{seen=value;throw {code:'40001',message:'private row detail'}}};
 const response=await handleReconciliationAction({method:'POST',principal:'worker',body},store,now);
 assert.equal(response?.status,409);assert.equal((seen as {expected_revision:number}).expected_revision,2);assert.equal(JSON.stringify(response).includes('private row detail'),false);
});
// The actual private handler is intentionally absent from the public repository.
// Set RECONCILIATION_HANDLER_SOURCE to the reconstructed candidate to exercise integration.
const handlerSource=process.env.RECONCILIATION_HANDLER_SOURCE;
test('private handler preserves Jobs controls and restricts reconciliation writes to the distinct worker key',{skip:!handlerSource},async()=>{
 const prior=process.env.TED_RECONCILER_ENABLED;process.env.TED_RECONCILER_ENABLED='true';
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
 const route=await handler(new Request('https://example.invalid/',{method:'POST',body:JSON.stringify({action:'reconcile_route_ted',key:'worker-test',card_id:'c-example',expected_section:'needs_you',expected_updated_at:item.expected_updated_at,expected_revision:1,expected_messages:[],line:'review queued'})}));
 assert.equal(route.status,200);assert.ok(rpcCalls.includes('ted_board_reconcile_route_ted'));
 const closed=await handler(new Request('https://example.invalid/',{method:'POST',body:JSON.stringify({action:'reconcile_close_verified',key:'worker-test',card_id:'c-example',expected_updated_at:item.expected_updated_at,expected_revision:1})}));
 assert.equal(closed.status,200);assert.ok(rpcCalls.includes('ted_board_reconcile_close_verified'));
 if(prior===undefined)delete process.env.TED_RECONCILER_ENABLED;else process.env.TED_RECONCILER_ENABLED=prior;
});
test('degraded snapshots retain explicit bounded coverage identifiers through publish and read',async()=>{
 const degraded={...packet(),coverage_defects:['mockups','github:read']};
 assert.deepEqual(validateReconciliationPublish(degraded,now),degraded);
 assert.deepEqual((await readReconciliation({read:async()=>degraded as any,publish:async()=>({ok:true})})).reconciliation,degraded);
 for(const coverage_defects of [['private token value'],['mockups','mockups'],Array.from({length:501},(_,i)=>'source'+i)])assert.throws(()=>validateReconciliationPublish({...packet(),coverage_defects},now));
});
test('verified closure requires worker credentials, a source guard, and a configured durable evidence hook',async()=>{
 const body={action:'reconcile_close_verified',card_id:'c-example',expected_updated_at:item.expected_updated_at,expected_revision:4};
 const missing={read:async()=>null,publish:async()=>({ok:true})};
 assert.equal((await handleReconciliationAction({method:'POST',principal:'page',body},missing,now))?.status,403);
 assert.equal((await handleReconciliationAction({method:'POST',principal:'worker',body},missing,now))?.status,503);
 assert.equal((await handleReconciliationAction({method:'POST',principal:'worker',body:{...body,expected_updated_at:undefined}},missing,now))?.status,400);
 const absentEvidence={...missing,closeVerified:async()=>{throw {code:'40001'}}};
 assert.equal((await handleReconciliationAction({method:'POST',principal:'worker',body},absentEvidence,now))?.status,409);
 let request:unknown;
 const configured={...missing,closeVerified:async(value:unknown)=>{request=value;return {ok:true}}};
 assert.equal((await handleReconciliationAction({method:'POST',principal:'worker',body},configured,now))?.status,200);
 assert.deepEqual(request,{card_id:'c-example',expected_updated_at:item.expected_updated_at,expected_revision:4});
});
test('verified closure rejects missing and invalid content revision before the store is called',async()=>{
 let writes=0;
 const store={read:async()=>null,publish:async()=>({ok:true}),closeVerified:async()=>{writes++;return {ok:true}}};
 for(const expected_revision of [undefined,null,0,-1,1.5,'1',Number.MAX_SAFE_INTEGER+1,Infinity]){
  const result=await handleReconciliationAction({method:'POST',principal:'worker',body:{action:'reconcile_close_verified',card_id:'c-example',expected_updated_at:item.expected_updated_at,expected_revision}},store,now);
  assert.equal(result?.status,400);
 }
 assert.equal(writes,0);
});
test('verified closure adapter forwards the exact observed content revision',async()=>{
 const calls:unknown[]=[];
 const store=createSupabaseReconciliationStore({rpc:async(name,args)=>{calls.push([name,args]);return {data:{ok:true},error:null}}});
 await store.closeVerified!({card_id:'c-example',expected_updated_at:item.expected_updated_at!,expected_revision:9} as any);
 assert.deepEqual(calls,[['ted_board_reconcile_close_verified',{p_card_id:'c-example',p_expected_updated_at:item.expected_updated_at,p_expected_revision:9}]]);
});

test('quarantines one malformed item and invalid queue entries without losing valid work',()=>{
 const worker={...item,id:'job:active',kind:'job',owner:'worker:c-example'};
 const bad={...item,id:'unsafe id?',owner:'untrusted',secret:'do-not-echo-this-row'};
 const result=validateReconciliationPublish({...packet(),items:[item,bad,worker],ted_queue:[item.id,worker.id,'missing']},now);
 assert.deepEqual(result.items.map(x=>x.id),[item.id,worker.id]);
 assert.deepEqual(result.ted_queue,[item.id]);
 assert.ok(result.coverage_defects?.includes('item_row:1'));
 assert.ok(result.coverage_defects?.includes('queue_row:1'));
 assert.ok(!JSON.stringify(result).includes('do-not-echo-this-row'));
 assert.equal(result.banner,true);
});

test('flag-off handler accepts empty or equal key configuration and preserves baseline responses',{skip:!handlerSource},async()=>{
 const before=process.env.TED_RECONCILER_ENABLED;process.env.TED_RECONCILER_ENABLED='false';
 try {
  const {pathToFileURL}=await import('node:url');
  const {createHandler}=await import(pathToFileURL(handlerSource!).href);
  const baselineURL=new URL('./legacy-handler-baseline.ts',pathToFileURL(handlerSource!));
  const legacy=await import(baselineURL.href);
  const db={from:()=>{throw Error('no read expected')}};
  for(const [page,worker] of [['',''],['same','same']]){
   const current=createHandler(db,page,worker,{enabled:false,message:'fixture'});
   const previous=legacy.createHandler(db,page,worker,{enabled:false,message:'fixture'});
   for(const request of [new Request('https://fixture.invalid',{method:'OPTIONS'}),new Request('https://fixture.invalid/?key=wrong')]){
    const a=await current(request.clone()),b=await previous(request.clone());
    assert.equal(a.status,b.status);assert.equal(await a.text(),await b.text());
   }
  }
 }finally{if(before===undefined)delete process.env.TED_RECONCILER_ENABLED;else process.env.TED_RECONCILER_ENABLED=before;}
});

test('flag-off erased assertions preserve malformed runner-failure responses',{skip:!handlerSource},async()=>{
 const prior=process.env.TED_RECONCILER_ENABLED;process.env.TED_RECONCILER_ENABLED='false';
 try {
  const {pathToFileURL}=await import('node:url');
  const {createHandler}=await import(pathToFileURL(handlerSource!).href);
  const legacy=await import(new URL('./legacy-handler-baseline.ts',pathToFileURL(handlerSource!)).href);
  const db={from:()=>{throw Error('invalid input must not reach the database')}};
  const current=createHandler(db,'page','worker',{enabled:false,message:'fixture'});
  const baseline=legacy.createHandler(db,'page','worker',{enabled:false,message:'fixture'});
  for(const [failure_kind,recovery] of [[{},'held'],[9,'held'],[{toString:'crash'},'held'],['crash',{}],['crash',{toString:'held'}]]){
   const request=new Request('https://fixture.invalid',{method:'POST',body:JSON.stringify({action:'runner_failure',key:'worker',card_id:'c',token:'fixture',failure_kind,recovery})});
   const a=await current(request.clone()),b=await baseline(request.clone());
   assert.equal(a.status,b.status);assert.equal(await a.text(),await b.text());
  }
 }finally{if(prior===undefined)delete process.env.TED_RECONCILER_ENABLED;else process.env.TED_RECONCILER_ENABLED=prior;}
});

test('managed missing approval returns Gone while conflicts and other failures retain status',{skip:!handlerSource},async()=>{
 const prior=process.env.TED_RECONCILER_ENABLED;
 try {
  const {pathToFileURL}=await import('node:url');const {createHandler}=await import(pathToFileURL(handlerSource!).href);
  for(const enabled of [true,false]){
   process.env.TED_RECONCILER_ENABLED=String(enabled);
   for(const [code,expected] of [['P0002',enabled?404:500],['22023',409],['XX000',500],[null,200]] as const){
    const calls:unknown[]=[];
    const db={rpc:async(name:string,args:unknown)=>{calls.push([name,args]);return {data:code?null:{ok:true},error:code?{code,message:'private diagnostic'}:null}}};
    const handler=createHandler(db,'page','worker',{enabled:false,message:'fixture'});
    const response=await handler(new Request('https://fixture.invalid',{method:'POST',body:JSON.stringify({action:'approval_result',key:'worker',approval_id:'test-missing-approval',status:'superseded',reason:''})}));
    assert.equal(response.status,expected);const body=await response.json();assert.equal(JSON.stringify(body).includes('private diagnostic'),false);
    if(!code)assert.deepEqual(body,{ok:true});
    assert.deepEqual(calls,[['ted_board_approval_result_with_reason',{p_id:'test-missing-approval',p_status:'superseded',p_reason:''}]]);
   }
  }
 }finally{if(prior===undefined)delete process.env.TED_RECONCILER_ENABLED;else process.env.TED_RECONCILER_ENABLED=prior;}
});
