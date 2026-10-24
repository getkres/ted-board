import assert from 'node:assert/strict';
import {test} from 'node:test';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
const {createHandler}=await import(pathToFileURL(path.resolve(process.env.TED_RUNTIME_SOURCE!, 'handler.ts')).href);

function fixture() {
 const writes:any[]=[],filters:any[]=[];let data:any={id:'x',section:'up_next'};
 const query:any={update:(fields:any)=>{writes.push(fields);return query;},eq:(...args:any[])=>{filters.push(args);return query;},select:()=>query,maybeSingle:async()=>({data,error:null})};
 const handler=createHandler({from:()=>query},'fixture-page','fixture-worker',null);
 const post=(extra={})=>handler(new Request('https://fixture.invalid',{method:'POST',body:JSON.stringify({action:'live_status',key:'fixture-worker',card_id:'x',state:'blocked',line:'ted review',section:'up_next',...extra})}));
 return {writes,filters,post,missing:()=>{data=null;}};
}
test('failure handoff uses worker auth and the existing doing guard',async()=>{
 const f=fixture();
 assert.equal((await f.post({key:'fixture-page'})).status,403);
 assert.equal(f.writes.length,0);
 assert.equal((await f.post()).status,200);
 assert.deepEqual(f.filters,[['id','x'],['section','ted_doing']]);
 assert.equal(f.writes[0].section,'up_next');assert.equal(f.writes[0].live_state,'blocked');
});
test('steward cleanup is conditional on inbox section and exact snapshot time',async()=>{
 const f=fixture();
 assert.equal((await f.post({expected_section:'needs_you'})).status,400);
 assert.equal((await f.post({expected_section:'needs_you',expected_updated_at:'2026-10-23T00:00:00Z'})).status,200);
 assert.deepEqual(f.filters,[['id','x'],['section','needs_you'],['updated_at','2026-10-23T00:00:00Z']]);
 f.missing();assert.equal((await f.post({expected_section:'needs_you',expected_updated_at:'2026-10-23T00:00:00Z'})).status,409);
});
test('retry may resume only from up next into running doing',async()=>{
 const f=fixture();
 assert.equal((await f.post({state:'running',section:'ted_doing',expected_section:'up_next'})).status,200);
 assert.deepEqual(f.filters,[['id','x'],['section','up_next']]);
 for (const extra of [{expected_section:'done'},{expected_section:'needs_you',state:'running',section:'ted_doing',expected_updated_at:'2026-10-23T00:00:00Z'},
                       {expected_section:'up_next',section:'done'},{state:'waiting_on_you',section:'up_next'},{state:'waiting_on_you',section:undefined}]) {
  assert.equal((await f.post(extra)).status,400);
 }
});
