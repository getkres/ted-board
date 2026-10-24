import {describe,test,before,beforeEach,after} from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
const require=createRequire(import.meta.url);
const handlerPath=new URL('../mockups-backend/supabase/functions/ted-mockups/handler.ts',import.meta.url);
const legacyPath=new URL('../mockups-backend/fixtures/legacy_mockup_act.sql',import.meta.url);
const configured=!!process.env.PGLITE_MODULE&&existsSync(handlerPath)&&existsSync(legacyPath);
describe('private handler and real local PostgreSQL feedback routing',{skip:configured?false:'Set PGLITE_MODULE and prepare the private handler candidate and legacy RPC fixture.'},()=>{
 let pg:any,handler:any;
 const id='52e541ec-9e88-40da-9f57-f7273736b652';
 const send=(body:any)=>handler(new Request('https://fixture.invalid/',{method:'POST',body:JSON.stringify({key:'fixture-page',...body})}));
 before(async()=>{
  const {PGlite}=require(process.env.PGLITE_MODULE!);pg=new PGlite();
  await pg.exec(`create role service_role;create role anon;create role authenticated;
   create table public.ted_mockups(id uuid primary key,project text,title text,batch text,status text default 'open',verdict text,verdict_change jsonb,created_at timestamptz default now());
   create table public.ted_mockup_pins(id uuid primary key default gen_random_uuid(),mockup_id uuid not null references public.ted_mockups(id),x_pct double precision not null,y_pct double precision not null,thread jsonb not null default '[]',resolved boolean not null default false,created_at timestamptz not null default now());
   create table public.ted_decisions(id bigserial primary key,page text,item_id text,choice text,note text check(char_length(note)<=2000),created_at timestamptz default now());`);
  await pg.exec(readFileSync(legacyPath,'utf8'));
  const apply=readFileSync(new URL('../../apply.sql',import.meta.url),'utf8');
  await pg.exec(apply.split('\\if :do_backup')[1].split('\\elif :do_apply')[0]);
  await pg.exec(readFileSync(new URL('../migrations/20261023020000_mockup_batch_feedback.sql',import.meta.url),'utf8'));
  const rpc=async(name:string,args:any)=>{
   if(!['ted_mockup_act','ted_mockup_batch_note'].includes(name))return {data:{enabled:false}};
   try{const keys=Object.keys(args),query=`select public.${name}(${keys.map((k,i)=>`${k}=>$${i+1}`).join(',')}) as data`;
    return {data:(await pg.query(query,Object.values(args))).rows[0].data};
   }catch(e:any){return {error:{code:e.code,message:'Database detail is private'}};}
  };
  const client={rpc,from(table:string){assert.ok(['ted_mockups','ted_mockup_pins','ted_decisions'].includes(table));let filter:any[]=[],start=0,end=999;
   const q:any={select:()=>q,order:()=>q,limit:(n:number)=>{end=n-1;return q;},range:(a:number,b:number)=>{start=a;end=b;return q;},eq:(k:string,v:unknown)=>{filter.push([k,v]);return q;},in:()=>q,then:async(resolve:any)=>{
    const clauses=filter.map(([key],i)=>{assert.match(key,/^[a-z_]+$/);return `${key}=$${i+1}`;});
    const result=await pg.query(`select * from public.${table}${clauses.length?' where '+clauses.join(' and '):''} order by created_at,id limit ${end-start+1} offset ${start}`,filter.map((f:any)=>f[1]));resolve({data:result.rows});
   }};return q;
  }};
  const {createHandler}=await import(handlerPath.href);handler=createHandler(client,'fixture-page','fixture-worker');
 });
 beforeEach(async()=>{await pg.exec('truncate public.ted_mockup_pins,public.ted_decisions,public.ted_mockups restart identity cascade');await pg.query("insert into public.ted_mockups(id,project,title,batch) values($1,'Test project','Frame one','Whole batch')",[id]);});
 after(async()=>{await pg?.close();});
 test('batch note and image pin enter the same existing worker queue, with whole-batch scope committed',async()=>{
  const image=await send({action:'pin',mockup_id:id,x:.2,y:.3,text:'Image detail'});assert.equal(image.status,200);
  const batch=await send({action:'pin',mockup_id:id,batch_note:true,text:'Use the shorter headline across this batch.'});assert.equal(batch.status,200);const saved:any=await batch.json();
  assert.equal(saved.pin.batch_note,true);assert.equal(saved.pin.mockup_id,id);assert.equal(saved.pin.thread[0].text,'Use the shorter headline across this batch.');
  const queue=(await pg.query("select * from public.ted_decisions where page='mockups' order by id")).rows;
  assert.equal(queue.length,2);assert.deepEqual(queue.map((r:any)=>r.choice),['pin','pin']);assert.equal(queue[1].item_id,saved.pin.id);assert.match(queue[1].note,/Feedback scope: whole-batch/);assert.match(queue[1].note,/Pin coords: n\/a \(whole batch\)/);assert.doesNotMatch(queue[1].note,/20%, 30%|50%, 50%/);
  assert.equal((await pg.query("select count(*)::int as n from public.ted_decisions where choice in ('approved','approve_batch','pick')")).rows[0].n,0);
  assert.ok(process.env.MOCKUP_WORKER_PATH,'Provide the private watcher path for isolated routing verification.');
  const worker=execFileSync('python3',[new URL('./mockup-batch-worker.test.py',import.meta.url).pathname,process.env.MOCKUP_WORKER_PATH!],{encoding:'utf8',input:JSON.stringify({mockups:(await pg.query('select * from public.ted_mockups')).rows,pins:(await pg.query('select * from public.ted_mockup_pins')).rows,receipts:queue,batch_pin_id:saved.pin.id})});
  assert.match(worker,/same isolated design queue/);

  const reply=await send({key:'fixture-worker',action:'ted_reply',pin_id:saved.pin.id,text:'I will update the whole batch.',decision_id:saved.decision_id});assert.equal(reply.status,200);assert.equal((await reply.json()).pin.thread.at(-1).who,'ted');
 });
 test('batch feedback on an approved anchor reaches Ted without changing final-art or build approval',async()=>{
  await pg.exec("update public.ted_mockups set verdict='approved',status='picked'");
  const response=await send({action:'pin',mockup_id:id,batch_note:true,text:'A note about the whole batch.'});assert.equal(response.status,200);const saved:any=await response.json();
  const state=(await pg.query('select * from public.ted_mockups')).rows;assert.equal(state[0].verdict,'approved');assert.equal(state[0].status,'picked');
  const worker=execFileSync('python3',[new URL('./mockup-batch-worker.test.py',import.meta.url).pathname,process.env.MOCKUP_WORKER_PATH!],{encoding:'utf8',input:JSON.stringify({mockups:state,pins:(await pg.query('select * from public.ted_mockup_pins')).rows,receipts:(await pg.query('select * from public.ted_decisions order by id')).rows,batch_pin_id:saved.pin.id,batch_only:true})});assert.match(worker,/same isolated design queue/);
 });
 test('GET advertises the private capability, and invalid markers never fall through to image pins',async()=>{
  const response=await handler(new Request('https://fixture.invalid/?key=fixture-page'));assert.equal(response.status,200);assert.equal((await response.json()).capabilities.batch_comments,true);
  for(const marker of [false,'true',null])assert.equal((await send({action:'pin',mockup_id:id,batch_note:marker,text:'Wrong marker',x:.5,y:.5})).status,400);
  assert.equal((await pg.query('select count(*)::int as n from public.ted_decisions')).rows[0].n,0);
 });
 test('the proposed check rejects 1201-character Sebastian batch messages and preserves 2000-character Ted replies',async()=>{
  const response=await send({action:'pin',mockup_id:id,batch_note:true,text:'x'.repeat(1200)});assert.equal(response.status,200);const saved:any=await response.json();
  await assert.rejects(pg.query('update public.ted_mockup_pins set thread=$1 where id=$2',[JSON.stringify([{who:'seb',text:'x'.repeat(1201)}]),saved.pin.id]),(e:any)=>e.code==='23514');
  const reply=await send({key:'fixture-worker',action:'ted_reply',pin_id:saved.pin.id,text:'t'.repeat(2000)});assert.equal(reply.status,200);
  assert.equal((await send({action:'pin',mockup_id:id,batch_note:true,text:'x'.repeat(1201)})).status,400);
 });
 test('a missing batch RPC fails closed without creating an image pin or exposing a capability',async()=>{
  await pg.exec('alter function public.ted_mockup_batch_note(text,uuid,text) rename to held_batch_note');
  try{const response=await send({action:'pin',mockup_id:id,batch_note:true,text:'Hold this'});assert.equal(response.status,503);assert.equal((await pg.query('select count(*)::int as n from public.ted_mockup_pins')).rows[0].n,0);
   const get=await handler(new Request('https://fixture.invalid/?key=fixture-page'));assert.equal((await get.json()).capabilities.batch_comments,false);
  }finally{await pg.exec('alter function public.held_batch_note(text,uuid,text) rename to ted_mockup_batch_note');}
 });
 test('rate limiting rolls back both a batch pin and its routing receipt',async()=>{
  await pg.exec("insert into public.ted_decisions(page,item_id,choice,note) select 'mockups','fixture','pin','rate fixture' from generate_series(1,90)");
  const response=await send({action:'pin',mockup_id:id,batch_note:true,text:'Over capacity'});assert.equal(response.status,503);
  assert.equal((await pg.query('select count(*)::int as n from public.ted_mockup_pins')).rows[0].n,0);assert.equal((await pg.query('select count(*)::int as n from public.ted_decisions')).rows[0].n,90);
 });
 test('batch SQL functions allow service-role execution only',async()=>{
  for(const role of ['anon','authenticated','service_role']){
   const allowed=(await pg.query("select has_function_privilege($1,'public.ted_mockup_batch_note(text,uuid,text)','execute') as wrapper,has_function_privilege($1,'public.ted_mockup_batch_text_valid(jsonb)','execute') as helper",[role])).rows[0];
   assert.equal(allowed.wrapper,role==='service_role');assert.equal(allowed.helper,role==='service_role');
  }
 });
 test('manual rollback refuses to lose batch notes and retains the private backup',async()=>{
  assert.equal((await send({action:'pin',mockup_id:id,batch_note:true,text:'Preserve this batch note'})).status,200);
  const apply=readFileSync(new URL('../../apply.sql',import.meta.url),'utf8'),rollback=apply.split('\\elif :do_rollback')[1].split('\\else')[0];
  await assert.rejects(pg.exec(rollback),/Batch notes exist/);await pg.exec('rollback');
  assert.equal((await pg.query('select count(*)::int as n from public.ted_mockup_pins where batch_note')).rows[0].n,1);
  await pg.exec('delete from public.ted_mockup_pins');await pg.exec(rollback);
  assert.equal((await pg.query("select to_regprocedure('public.ted_mockup_batch_note(text,uuid,text)') is null as removed,to_regclass('ted_board_backup_batch_notes_r2_1024.pins') is not null as backup")).rows[0].removed,true);
  assert.equal((await pg.query("select to_regclass('ted_board_backup_batch_notes_r2_1024.pins') is not null as backup")).rows[0].backup,true);
  await pg.exec(readFileSync(new URL('../migrations/20261023020000_mockup_batch_feedback.sql',import.meta.url),'utf8'));
 });

});
