import assert from 'node:assert/strict';
import {test} from 'node:test';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
const {createHandler}=await import(pathToFileURL(path.resolve(process.env.TED_RUNTIME_SOURCE!,'handler.ts')).href);
const note='[ted-runner-failure:v1:timeout] worker run finished with a timeout; ted owns recovery from the job files. one retry is queued from the job files.';
function fixture() {
 let row:any={id:'x',project:'Fixture',section:'ted_doing',decision_kind:null,live_state:'blocked',live_status_at:null,updated_at:'2026-10-24T21:00:00Z',messages:[]};
 let race:any=null;
 const db:any={from:()=>{
  let fields:any=null;const checks:((r:any)=>boolean)[]=[];
  const q:any={select:()=>q,eq:(k:string,v:any)=>{checks.push(r=>k==='messages'?JSON.stringify(r[k])===v:r[k]===v);return q;},
   is:(k:string,v:any)=>{checks.push(r=>r[k]===v);return q;},or:()=>{checks.push(r=>r.live_state!=='waiting_on_you');return q;},
   update:(v:any)=>{fields=v;return q;},maybeSingle:async()=>{
    if(fields){if(race){Object.assign(row,race);race=null;}if(!checks.every(fn=>fn(row)))return {data:null,error:null};Object.assign(row,fields);}
    return {data:structuredClone(row),error:null};
   }};return q;
 },rpc:async(_name:string,args:any)=>{
  row.messages.push({who:'ted',text:args.p_text,at:new Date().toISOString()});
  return {data:{card:structuredClone(row)},error:null};
 }};
 const handler=createHandler(db,'page','worker',null);
 const post=(body:any)=>handler(new Request('https://fixture.invalid',{method:'POST',body:JSON.stringify({key:'worker',card_id:'x',...body})}));
 return {post,row:()=>row,race:(v:any)=>{race=v;},publish:(extra:any={})=>post({action:'runner_failure',failure_kind:'timeout',recovery:'retry',token:'failure-chain-1',...extra}),
  cleanup:()=>post({action:'live_status',state:'blocked',section:'up_next',line:note,expected_section:'needs_you',expected_updated_at:row.updated_at})};
}
test('ordinary Ted replies cannot supply server provenance even with the exact text',async()=>{
 const f=fixture();assert.equal((await f.post({action:'ted_reply',text:note,runner_failure:true})).status,200);
 assert.equal(f.row().messages[0].runner_failure,undefined);
 f.row().section='needs_you';assert.equal((await f.cleanup()).status,409);
});
test('structured failure publication stamps provenance and is idempotent',async()=>{
 const f=fixture();assert.equal((await f.publish()).status,200);assert.equal((await f.publish()).status,200);
 assert.equal(f.row().messages.length,1);assert.equal(f.row().messages[0].runner_failure,true);
 assert.equal(f.row().messages[0].text,note);
 f.row().section='needs_you';assert.equal((await f.cleanup()).status,200);assert.equal(f.row().section,'up_next');
});
test('server publication rejects invalid types, supplied text, page auth, and stale message writes',async()=>{
 for(const extra of [{failure_kind:'unknown'},{recovery:'unknown'},{text:'Confirm the spend.'},{runner_failure:true}]) {
  const f=fixture();assert.equal((await f.publish(extra)).status,400);assert.equal(f.row().messages.length,0);
 }
 const denied=fixture();assert.equal((await denied.publish({key:'page'})).status,403);
 const race=fixture();race.race({messages:[{who:'seb',text:'Wait.',at:'2026-10-24T21:01:00Z'}]});
 assert.equal((await race.publish()).status,409);assert.equal(race.row().messages[0].who,'seb');
});
