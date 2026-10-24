import assert from 'node:assert/strict';
import {test} from 'node:test';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
const {createHandler}=await import(pathToFileURL(path.resolve(process.env.TED_RUNTIME_SOURCE!,'handler.ts')).href);
const note='[ted-runner-failure:v1:timeout] worker run finished with a timeout; ted owns recovery from the job files. one retry is queued from the job files.';

function fixture(extra:any={},race:any={}) {
 let row:any={id:'x',section:'needs_you',decision_kind:null,live_state:'blocked',updated_at:'2026-10-24T21:00:00Z',messages:[{who:'ted',at:'2026-10-24T21:00:00Z',text:note}],...extra};
 const guards:any[]=[];let saved=0;
 const db={from:()=>{
  let fields:any=null;const conditions:((r:any)=>boolean)[]=[];
  const query:any={update:(v:any)=>{fields=v;return query;},
   eq:(k:string,v:any)=>{conditions.push(r=>k==='messages'?JSON.stringify(r[k])===v:r[k]===v);return query;},
   is:(k:string,v:any)=>{guards.push(['is',k,v]);conditions.push(r=>r[k]===v);return query;},
   or:(filter:string)=>{guards.push(['or',filter]);conditions.push(r=>r.live_state===null||r.live_state!=='waiting_on_you');return query;},
   select:()=>query,maybeSingle:async()=>{
    if(fields){Object.assign(row,race);if(!conditions.every(fn=>fn(row)))return {data:null,error:null};row={...row,...fields};saved++;}
    return {data:structuredClone(row),error:null};
   }};
  return query;
 }};
 const handler=createHandler(db,'fixture-page','fixture-worker',null);
 return {guards,count:()=>saved,post:()=>handler(new Request('https://fixture.invalid',{method:'POST',body:JSON.stringify({action:'live_status',key:'fixture-worker',card_id:'x',state:'blocked',line:note,section:'up_next',expected_section:'needs_you',expected_updated_at:'2026-10-24T21:00:00Z'})}))};
}

test('only an exact latest runner failure permits guarded inbox departure',async()=>{
 const f=fixture();assert.equal((await f.post()).status,200);assert.equal(f.count(),1);
 assert.ok(f.guards.some(x=>x[0]==='is'&&x[1]==='decision_kind'&&x[2]===null));
 for(const messages of [[{who:'ted',at:'2026-10-24T21:00:00Z',text:'Export completed.'}],
                        [{who:'seb',at:'2026-10-24T21:00:00Z',text:note}],
                        [{who:'ted',at:'2026-10-24T21:00:00Z',text:note+' Confirm the spend.'}]]) {
  const blocked=fixture({messages});assert.equal((await blocked.post()).status,409);assert.equal(blocked.count(),0);
 }
});
test('decision kinds and pending approval states return 409 without moving',async()=>{
 for(const extra of [{decision_kind:'send_email'},{decision_kind:'spend_money'},{live_state:'waiting_on_you'}]) {
  const f=fixture(extra);assert.equal((await f.post()).status,409);assert.equal(f.count(),0);
 }
});
test('conditional update still rejects a kind or approval arriving after validation',async()=>{
 for(const race of [{decision_kind:'send_email'},{live_state:'waiting_on_you'},
                   {messages:[{who:'seb',at:'2026-10-24T21:01:00Z',text:'Wait for my answer.'}]}]) {
  const f=fixture({},race);assert.equal((await f.post()).status,409);assert.equal(f.count(),0);
 }
});
