import assert from 'node:assert/strict';
import {test} from 'node:test';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
const {createHandler}=await import(pathToFileURL(path.resolve(process.env.TED_RUNTIME_SOURCE!, 'handler.ts')).href);

function fixture() {
 const note='[ted-runner-failure:v1:startup_failure] worker run finished with a startup failure; ted owns recovery from the job files. no automatic retry remains.';
 const writes:any[]=[],filters:any[]=[];let data:any={id:'x',section:'needs_you',decision_kind:null,live_state:'blocked',live_status_at:null,messages:[{who:'ted',runner_failure:true,at:'2026-10-23T00:00:00Z',text:note}]};
 const query:any={update:(fields:any)=>{writes.push(fields);return query;},eq:(...args:any[])=>{filters.push(args);return query;},is:(...args:any[])=>{filters.push(['is',...args]);return query;},or:(filter:string)=>{filters.push(['or',filter]);return query;},select:()=>query,maybeSingle:async()=>({data,error:null})};
 const handler=createHandler({from:()=>query},'fixture-page','fixture-worker',null);
 const post=(extra={})=>handler(new Request('https://fixture.invalid',{method:'POST',body:JSON.stringify({action:'live_status',key:'fixture-worker',card_id:'x',state:'blocked',line:note,section:'up_next',...extra})}));
 return {writes,filters,post,messages:data.messages,missing:()=>{data=null;}};
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
 assert.deepEqual(f.filters,[['id','x'],['id','x'],['section','needs_you'],['updated_at','2026-10-23T00:00:00Z'],['is','decision_kind',null],['or','live_state.is.null,live_state.neq.waiting_on_you'],['messages',JSON.stringify(f.messages)],['is','live_status_at',null]]);
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
