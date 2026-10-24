import {test} from 'node:test';
import assert from 'node:assert/strict';
import {handleMockupBatchNote} from './mockup-batch-comments.ts';
const id='52e541ec-9e88-40da-9f57-f7273736b652';
const pinId='37c37f4b-00a8-4d46-85e5-f420f6f13914';
const body={action:'pin',mockup_id:id,batch_note:true,text:'  Shorter headline across the batch.  '};
const receipt={pin:{id:pinId,mockup_id:id,batch_note:true,resolved:false,created_at:'2026-10-24T00:00:00Z',thread:[{who:'seb',text:'Shorter headline across the batch.',at:'2026-10-24T00:00:00Z'}]},decision_id:10};
test('batch pin writes require authenticated page identity, bounded text, and a single mockup anchor',async()=>{
 const calls:any[]=[];const store={post:async(...args:any[])=>{calls.push(args);return receipt;}};
 for(const principal of [null,'worker'] as const)assert.equal((await handleMockupBatchNote(body,principal,store))?.status,403);
 for(const bad of [{batch_note:false},{batch_note:'true'},{mockup_id:'bad'},{text:' '},{text:'x'.repeat(1201)},{text:17},{project:'forged'},{x:.5},{whole_image:true},{verdict:'approved'}])assert.equal((await handleMockupBatchNote({...body,...bad},'page',store))?.status,400);
 assert.equal(calls.length,0);
 const r=await handleMockupBatchNote(body,'page',store);assert.equal(r?.status,200);assert.deepEqual(calls,[[{mockup_id:id,text:'Shorter headline across the batch.'}]]);assert.deepEqual(r?.body,{ok:true,...receipt});
 assert.equal(await handleMockupBatchNote({action:'reply',pin_id:pinId,text:'reply'},'page',store),null);
 assert.equal(await handleMockupBatchNote({action:'pin',mockup_id:id,x:.5,y:.5,text:'point'},'page',store),null);
});
test('batch pin routing never acknowledges a missing receipt, wrong image, missing scope marker, or missing saved message',async()=>{
 for(const result of [{...receipt,decision_id:null},{...receipt,pin:{...receipt.pin,batch_note:false}},{...receipt,pin:{...receipt.pin,mockup_id:pinId}},{...receipt,pin:{...receipt.pin,thread:[]}}]){
  const r=await handleMockupBatchNote(body,'page',{post:async()=>result});assert.equal(r?.status,503);assert.equal(r?.body.ok,undefined);
 }
 const r=await handleMockupBatchNote(body,'page',{post:async()=>{throw Error('private secret details');}});assert.equal(r?.status,503);assert.equal(JSON.stringify(r).includes('private secret details'),false);
});
