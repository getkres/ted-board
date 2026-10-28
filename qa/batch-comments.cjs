const {test}=require('node:test');
const assert=require('node:assert/strict'),path=require('node:path');
const {chromium,fixture,clip}=require('./browser.cjs');
const {mockups:seed}=require('./fixtures.cjs');
async function setup(width=1440,{enabled=true,archived=false}={}){
 const browser=await chromium.launch(),page=await browser.newPage({viewport:{width,height:width<=390?844:900}});
 page.setDefaultTimeout(2500);await fixture(page);
 const rows=structuredClone(seed),posts=[],errors=[],pins=[
  {id:'batch-thread',mockup_id:'frame1',batch_note:true,resolved:false,created_at:'2026-10-20T12:00:00Z',thread:[{who:'seb',text:'Keep the shorter headline for this batch.',at:'2026-10-20T12:00:00Z'},{who:'ted',text:'I will use the shorter headline in the next pass.',at:'2026-10-20T12:01:00Z'}]},
  {id:'image-pin',mockup_id:'frame1',x:.5,y:.5,resolved:false,created_at:'2026-10-20T12:00:00Z',thread:[{who:'seb',text:'Image-only spacing feedback',at:'2026-10-20T12:00:00Z'}]},
  {id:'other-batch',mockup_id:'v2',batch_note:true,resolved:false,created_at:'2026-10-20T12:00:00Z',thread:[{who:'ted',text:'Different batch history',at:'2026-10-20T12:00:00Z'}]},
  {id:'other-project',mockup_id:'outside',batch_note:true,resolved:false,created_at:'2026-10-20T12:00:00Z',thread:[{who:'ted',text:'Different project history',at:'2026-10-20T12:00:00Z'}]}
 ];
 rows.push({...rows.find(m=>m.id==='frame1'),id:'outside',project:'Other project'});
 if(archived)rows.find(m=>m.id==='frame1').status='archived';
 page.on('pageerror',e=>errors.push(e.message));let fail=false,malformed=false,missingReceipt=false,hold=null,capability=enabled;
 await page.route('**/functions/v1/ted-mockups*',async route=>{
  if(route.request().method()==='GET')return route.fulfill({json:{mockups:rows,pins,verdicts_enabled:true,approve_batch_enabled:true,archive_enabled:true,capabilities:{batch_comments:capability},batch_comments_enabled:true}});
  const {key,...body}=route.request().postDataJSON();posts.push(body);
  if(hold)await hold;
  if(fail)return route.fulfill({status:503,json:{error:'Comment could not be sent. Refresh before trying again.'}});
  const pin={id:'new-note-'+posts.length,mockup_id:body.mockup_id,batch_note:!malformed,resolved:false,created_at:new Date().toISOString(),thread:[{who:'seb',text:body.text,at:new Date().toISOString()}]};
  pins.push(pin);return route.fulfill({json:{ok:true,pin,decision_id:missingReceipt?null:posts.length+100}});
 });
 await page.goto('http://127.0.0.1:8763/#k=fixture-only&tab=mockups');await page.waitForSelector('.mk3-wall');
 if(archived)await page.getByRole('button',{name:'Archived',exact:true}).click();
 await page.evaluate(()=>mockups.openBatch(mockups.batches().find(b=>b.kind==='set'&&b.project==='Test line 1')));
 return {browser,page,rows,pins,posts,errors,fail:()=>fail=true,malformed:()=>malformed=true,missingReceipt:()=>missingReceipt=true,hold:p=>hold=p,setCapability:value=>capability=value};
}
// A wrong batch selector, leaking image pins, or textContent replaced by HTML must fail here.
test('batch conversation shows only exact-batch notes and Ted replies, and never becomes image pins',async()=>{
 const f=await setup();try{const p=f.page,thread=p.getByRole('list',{name:'Batch conversation'});
  assert.equal(await thread.getByRole('listitem').count(),2);
  assert.match(await thread.innerText(),/Keep the shorter headline/);assert.match(await thread.innerText(),/I will use the shorter headline/);
  assert.doesNotMatch(await thread.innerText(),/Image-only|Different batch|Different project/);
  f.pins[0].thread.push({who:'ted',text:'<img data-exploit src=x> Keep this as text.',at:'2026-10-20T12:02:00Z'});await p.evaluate(()=>mockups.load());
  assert.equal(await thread.locator('img').count(),0);assert.match(await thread.innerText(),/<img data-exploit/);
  await p.getByRole('button',{name:'Open frame1',exact:true}).click();assert.equal(await p.locator('.mockup-canvas .mockup-pin').count(),1);
  assert.doesNotMatch(await p.locator('.mockup-pin-index').innerText(),/shorter headline/);assert.deepEqual(f.errors,[]);
 }finally{await f.browser.close();}
});
// Wrong action, missing marker, missing receipt acknowledgement, or erased history breaks this.
test('Send posts a batch-scoped pin through feedback, displays it, clears its draft, and creates no approval request',async()=>{
 const f=await setup(375);try{const p=f.page,input=p.getByRole('textbox',{name:'Comment on this batch'});
  await input.fill('Use this headline across every frame.');await p.getByRole('button',{name:'Send',exact:true}).click();
  await p.waitForFunction(()=>mockups.pins.some(p=>p.id==='new-note-1'));
  assert.deepEqual(f.posts,[{action:'pin',mockup_id:'frame1',batch_note:true,text:'Use this headline across every frame.'}]);
  assert.match(await p.getByRole('list',{name:'Batch conversation'}).innerText(),/Use this headline/);assert.equal(await input.inputValue(),'');
  assert.equal(f.posts.some(b=>/approve|verdict|pick|build/.test(b.action)),false);assert.match(await p.locator('#notice').innerText(),/Sent to Ted/);
  await p.evaluate(()=>mockups.load());assert.match(await p.getByRole('list',{name:'Batch conversation'}).innerText(),/Use this headline/);
 }finally{await f.browser.close();}
});
test('composer is absent without capabilities.batch_comments, even with the legacy flag present',async()=>{
 for(const width of [375,1440]){const f=await setup(width,{enabled:false});try{const p=f.page;
  for(const kind of ['set','round','stack']){await p.evaluate(kind=>mockups.openBatch(mockups.batches().find(b=>b.kind===kind)),kind);assert.equal(await p.locator('.mk3-batch-comments').count(),0);}
  await p.evaluate(()=>mockups.load());assert.equal(await p.getByRole('button',{name:'Send',exact:true}).count(),0);assert.equal(f.posts.length,0);
  await p.evaluate(()=>mockups.openBatch(mockups.batches().find(b=>b.kind==='set'&&b.project==='Test line 1')));await p.evaluate(()=>document.fonts.ready);
  await p.screenshot({path:path.join(process.env.QA_BATCH_OUT||path.join(__dirname,'../docs/mockup-batch-comments-review'),'unsupported-'+width+'.png'),fullPage:true});
 }finally{await f.browser.close();}}
});
test('a rollout capability change hides the composer and preserves its existing session draft',async()=>{
 const f=await setup();try{const p=f.page;await p.getByRole('textbox',{name:'Comment on this batch'}).fill('Keep this draft through a rollout');
  f.setCapability(false);await p.evaluate(()=>mockups.load());assert.equal(await p.locator('.mk3-batch-comments').count(),0);
  f.setCapability(true);await p.evaluate(()=>mockups.load());assert.equal(await p.getByRole('textbox',{name:'Comment on this batch'}).inputValue(),'Keep this draft through a rollout');
 }finally{await f.browser.close();}
});
test('failed or unconfirmed saves retain the draft and do not claim delivery',async()=>{
 for(const mode of ['fail','malformed','missingReceipt']){const f=await setup();try{const p=f.page;f[mode]();
  await p.getByRole('textbox',{name:'Comment on this batch'}).fill('Keep this draft');await p.getByRole('button',{name:'Send',exact:true}).click();
  await p.waitForFunction(()=>!mockups.batchComments.pending.size);
  assert.equal(await p.getByRole('textbox',{name:'Comment on this batch'}).inputValue(),'Keep this draft');assert.doesNotMatch(await p.locator('#notice').innerText(),/Sent to Ted/);
 }finally{await f.browser.close();}}
});
test('polling preserves the composer, focus, caret, and per-batch draft isolation',async()=>{
 const f=await setup();try{const p=f.page,input=p.getByRole('textbox',{name:'Comment on this batch'});
  await input.fill('Keep editing here');await input.evaluate(e=>{e.focus();e.setSelectionRange(5,5);e.dispatchEvent(new Event('select'));});
  await p.evaluate(()=>mockups.load());await p.waitForFunction(()=>document.activeElement?.getAttribute('aria-label')==='Comment on this batch');
  assert.equal(await input.inputValue(),'Keep editing here');assert.equal(await input.evaluate(e=>e.selectionStart),5);
  await p.evaluate(()=>mockups.openBatch(mockups.batches().find(b=>b.kind==='stack')));assert.equal(await input.inputValue(),'');
  await input.fill('Stack draft');await p.evaluate(()=>mockups.openBatch(mockups.batches().find(b=>b.kind==='set'&&b.project==='Test line 1')));assert.equal(await input.inputValue(),'Keep editing here');
 }finally{await f.browser.close();}
});
test('all batch layouts include the composer, and archived batches keep read-only history',async()=>{
 const f=await setup(375);try{for(const kind of ['set','round','stack']){await f.page.evaluate(kind=>mockups.openBatch(mockups.batches().find(b=>b.kind===kind)),kind);assert.equal(await f.page.getByRole('textbox',{name:'Comment on this batch'}).count(),1);}}finally{await f.browser.close();}
 const a=await setup(375,{archived:true});try{assert.match(await a.page.getByRole('list',{name:'Batch conversation'}).innerText(),/shorter headline/);assert.equal(await a.page.getByRole('button',{name:'Send',exact:true}).isDisabled(),true);assert.equal(a.posts.length,0);}finally{await a.browser.close();}
});
test('in-flight saves block double submits and ignore old-key acknowledgements',async()=>{
 const f=await setup();let release;try{const p=f.page;f.hold(new Promise(r=>release=r));
  await p.getByRole('textbox',{name:'Comment on this batch'}).fill('Old owner text');await p.getByRole('button',{name:'Send',exact:true}).click();await p.waitForFunction(()=>mockups.batchComments.pending.size===1);
  assert.equal(await p.getByRole('button',{name:'Send',exact:true}).isDisabled(),true);
  await p.evaluate(()=>{key='changed-fixture';resetForKeyChange();mockups.reset();});release();await p.waitForTimeout(80);
  assert.equal(await p.evaluate(()=>mockups.pins.length),0);assert.equal(await p.evaluate(()=>mockups.drafts.size),0);assert.equal(f.posts.length,1);assert.doesNotMatch(await p.locator('#notice').innerText(),/Sent to Ted/);
 }finally{release?.();await f.browser.close();}
});
test('batch comments fit 375, 390, and 1440 pixels with the compact viewer unchanged',async()=>{
 const out=process.env.QA_BATCH_OUT||path.join(__dirname,'../docs/mockup-batch-comments-review');
 for(const width of [375,390,1440]){const f=await setup(width);try{const p=f.page;await p.evaluate(()=>document.fonts.ready);
  const qa=await clip(p);assert.equal(qa.scrollWidth,width);assert.deepEqual(qa.clips,[]);assert.deepEqual(qa.gradients,[]);assert.equal(qa.emDash,false);assert.deepEqual(f.errors,[]);
  await p.screenshot({path:path.join(out,'after-'+width+'.png'),fullPage:true});
  await p.getByRole('button',{name:'Open frame1',exact:true}).click();const head=await p.locator('.mockup-dialog-head').boundingBox();assert.ok(head.height<= (width<=390?100:56));
  assert.equal(await p.locator('.mockup-dialog .mk3-batch-comments').count(),0);await p.screenshot({path:path.join(out,'viewer-'+width+'.png'),fullPage:true});
 }finally{await f.browser.close();}}
});

test('batch history sorts real instants across timezone offsets and keeps notes on archived anchors',async()=>{
 const f=await setup();try{
  f.pins[0].thread=[{who:'seb',text:'Second in time',at:'2026-10-20T12:00:00Z'},{who:'ted',text:'First in time',at:'2026-10-20T12:02:00+01:00'}];
  f.rows.push({...f.rows.find(m=>m.id==='frame1'),id:'active-sibling'});f.rows.find(m=>m.id==='frame1').status='archived';
  await f.page.evaluate(()=>mockups.load());const entries=await f.page.getByRole('list',{name:'Batch conversation'}).locator('.message p').allTextContents();
  assert.deepEqual(entries,['First in time','Second in time']);
 }finally{await f.browser.close();}
});
test('a poll started before Send cannot erase the acknowledged batch note',async()=>{
 const f=await setup();let release;try{const p=f.page;let started;const ready=new Promise(r=>started=r),hold=new Promise(r=>release=r);const stale=structuredClone(f.pins);
  await p.route('**/functions/v1/ted-mockups*',async route=>{if(route.request().method()!=='GET')return route.fallback();started();await hold;return route.fulfill({json:{mockups:f.rows,pins:stale,capabilities:{batch_comments:true}}});});
  await p.evaluate(()=>void mockups.load());await ready;await p.getByRole('textbox',{name:'Comment on this batch'}).fill('Keep the acknowledged note');await p.getByRole('button',{name:'Send',exact:true}).click();
  await p.waitForFunction(()=>mockups.pins.some(p=>p.id==='new-note-1'));release();await p.waitForFunction(()=>!mockups.loading);
  assert.match(await p.getByRole('list',{name:'Batch conversation'}).innerText(),/Keep the acknowledged note/);
 }finally{release?.();await f.browser.close();}
});

test('unchanged Ted read markers are not rewritten by batch polling',async()=>{
 const f=await setup();try{const p=f.page;await p.evaluate(()=>{const set=mockups.storage.set.bind(mockups.storage);window.batchReadWrites=0;mockups.storage.set=(key,value)=>{if(key.startsWith('ted-mockup-read:'))window.batchReadWrites++;return set(key,value);};});
  await p.evaluate(()=>mockups.load());await p.evaluate(()=>mockups.load());assert.equal(await p.evaluate(()=>window.batchReadWrites),0);
  f.pins[0].thread.push({who:'ted',text:'A new reply for the batch.',at:'2026-10-21T12:00:00Z'});await p.evaluate(()=>mockups.load());assert.equal(await p.evaluate(()=>window.batchReadWrites),1);
  await p.evaluate(()=>mockups.load());assert.equal(await p.evaluate(()=>window.batchReadWrites),1);
 }finally{await f.browser.close();}
});
