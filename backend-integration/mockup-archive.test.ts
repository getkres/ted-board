import {test} from 'node:test';
import assert from 'node:assert/strict';
import {handleMockupArchive, createMockupArchiveStore} from './mockup-archive.ts';

const id='52e541ec-9e88-40da-9f57-f7273736b652';
test('archive requires an authenticated page principal and an exact bounded selector', async()=>{
 const calls:unknown[]=[];
 const store={setArchived:async(...args:unknown[])=>{calls.push(args);return [{id,status:'archived'}];}};
 const body={action:'archive',project:'Test',batch:'Frames'};
 for(const principal of [null,'worker'] as const) assert.equal((await handleMockupArchive(body,principal,store))?.status,403);
 for(const bad of [{},{project:''},{batch:' '},{project:'x'.repeat(101)},{batch:'x'.repeat(201)},{mockup_id:'bad',batch:undefined},{mockup_id:id},{ids:[id]},{verdict:'approved'},{status:'picked'},{scope:'all'},{principal:'page'}]){
  const input={...body,...bad};if(Object.keys(bad).length===0)delete (input as any).project;
  assert.equal((await handleMockupArchive(input,'page',store))?.status,400,JSON.stringify(bad));
 }
 assert.equal(calls.length,0);
 assert.equal((await handleMockupArchive(body,'page',store))?.status,200);
 assert.deepEqual(calls,[[{project:'Test',batch:'Frames'},true]]);
 assert.equal((await handleMockupArchive({action:'unarchive',project:'Test',mockup_id:id},'page',store))?.status,200);
 assert.deepEqual(calls[1],[{project:'Test',mockup_id:id},false]);
 assert.equal(await handleMockupArchive({action:'verdict'},'page',store),null);
});
test('archive errors never expose private details or claim success',async()=>{
 const store={setArchived:async()=>{throw Error('private database detail');}};
 const r=await handleMockupArchive({action:'archive',project:'Test',batch:'Frames'},'page',store);
 assert.equal(r?.status,503);assert.equal(JSON.stringify(r).includes('private database detail'),false);
});

// Records the actual adapter queries at the service-role boundary, without a database.
function database(rows:any[],receipts:any[]=[]){
 const writes:any[]=[];
 const db={from(table:string){let values:any,filters:any[]=[],start=0,end=Infinity;
  const q:any={select:()=>q,eq:(...a:any[])=>{filters.push(['eq',...a]);return q;},in:(...a:any[])=>{filters.push(['in',...a]);return q;},limit:()=>q,
   order:()=>q,range:(a:number,b:number)=>{start=a;end=b;return q;},update:(v:any)=>{values=v;return q;},then:(resolve:any)=>{
    const selected=(table==='ted_decisions'?receipts:rows).filter(row=>filters.every(([op,k,v])=>op==='eq'?row[k]===v:v.includes(row[k]))).slice(start,end+1);
    if(values){writes.push({table,values,filters});for(const row of selected)Object.assign(row,values);}
    resolve({data:selected.map(row=>({...row})),error:null});
   }};return q;
 }};return {db,writes};
}
test('service-role adapter archives and restores only status, preserving explicit and legacy verdicts',async()=>{
 const rows=[{id,project:'Test',batch:'Frames',status:'open',verdict:'needs_work',verdict_note:'spacing'},
  {id:'legacy',project:'Test',batch:'Frames',status:'picked',verdict:null},
  {id:'other',project:'Elsewhere',batch:'Frames',status:'open',verdict:'scrapped'}];
 const {db,writes}=database(rows,[{page:'mockups',choice:'pick',item_id:'legacy'}]);
 const store=createMockupArchiveStore(db);
 await store.setArchived({project:'Test',batch:'Frames'},true);
 assert.deepEqual(rows.map(r=>r.status),['archived','archived','open']);
 await store.setArchived({project:'Test',batch:'Frames'},false);
 assert.deepEqual(rows.map(r=>r.status),['open','picked','open']);
 assert.deepEqual(rows.map(r=>r.verdict),['needs_work',null,'scrapped']);
 assert.equal(rows[0].verdict_note,'spacing');
 for(const write of writes){assert.equal(write.table,'ted_mockups');assert.deepEqual(Object.keys(write.values),['status']);assert.ok(write.filters.some(f=>f[1]==='project'&&f[2]==='Test'));}
});
test('frame scopes cannot change a matching id in a different project',async()=>{
 const rows=[{id,project:'Elsewhere',batch:'Frames',status:'open',verdict:null}];
 const {db,writes}=database(rows);
 assert.deepEqual(await createMockupArchiveStore(db).setArchived({project:'Test',mockup_id:id},true),[]);
 assert.equal(writes.length,0);assert.equal(rows[0].status,'open');
});

test('large batches paginate reads and update every frame without touching other projects',async()=>{
 const rows=Array.from({length:1001},(_,i)=>({id:String(i),project:'Test',batch:'Frames',status:'open',verdict:'needs_work'}));
 rows.push({id:'outside',project:'Other',batch:'Frames',status:'open',verdict:'scrapped'});
 const {db,writes}=database(rows);await createMockupArchiveStore(db).setArchived({project:'Test',batch:'Frames'},true);
 assert.equal(rows.filter(r=>r.status==='archived').length,1001);assert.equal(rows.at(-1)?.status,'open');
 assert.equal(writes.length,3);assert.equal(rows[500].verdict,'needs_work');
});
