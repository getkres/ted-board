const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {chromium,fixture,clip}=require('./browser.cjs');
const {mockups:seed}=require('./fixtures.cjs');
async function setup(width=1440,{enabled=true}={}){
 const browser=await chromium.launch({headless:true}),page=await browser.newPage({viewport:{width,height:900}});
 page.setDefaultTimeout(3000);await fixture(page);const posts=[],rows=structuredClone(seed),errors=[];
 rows[0].verdict='needs_work';rows[0].verdict_note='Keep spacing feedback';
 page.on('pageerror',e=>errors.push(e.message));let fail=false,hold=null;
 await page.route('**/functions/v1/ted-mockups*',async route=>{
  const req=route.request();if(req.method()==='GET')return route.fulfill({json:{mockups:rows,pins:[],verdicts_enabled:true,approve_batch_enabled:true,archive_enabled:enabled}});
  const {key,...body}=req.postDataJSON();posts.push(body);
  if(hold){await hold;hold=null;}
  if(fail)return route.fulfill({status:503,json:{error:'Archive unavailable. Try again.'}});
  if(!['archive','unarchive'].includes(body.action))throw Error('Archive sent an unrelated action');
  const targets=rows.filter(m=>m.project===body.project&&(body.mockup_id?m.id===body.mockup_id:m.batch===body.batch));
  for(const m of targets)m.status=body.action==='archive'?'archived':m.verdict==='approved'?'picked':'open';
  return route.fulfill({json:{ok:true,mockups:targets}});
 });
 await page.goto('http://127.0.0.1:8763/#k=fixture-only&tab=mockups');await page.waitForSelector('.mk3-wall');await page.clock.install();await page.clock.pauseAt(new Date(Date.now()+50));
 return {browser,page,posts,rows,errors,fail:()=>fail=true,hold:p=>hold=p};
}
test('batch archive disappears immediately, Undo lasts five seconds, and polling cannot revive it',async()=>{
 const f=await setup();try{const {page:p,posts}=f;
  await p.locator('.mk3-cover').filter({hasText:'Lander looks'}).getByRole('button',{name:'Archive',exact:true}).click();
  assert.equal(await p.locator('.mk3-cover').count(),2);assert.equal(posts.length,0);
  await p.evaluate(()=>mockups.load());assert.equal(await p.locator('.mk3-cover').count(),2);
  await p.clock.runFor(4999);await p.locator('.mockup-archive-toast').getByRole('button',{name:'Undo',exact:true}).click();
  assert.equal(await p.locator('.mk3-cover').count(),3);await p.clock.runFor(2);assert.equal(posts.length,0);
  await p.locator('.mk3-cover').filter({hasText:'Lander looks'}).getByRole('button',{name:'Archive',exact:true}).click();
  await p.clock.runFor(5001);await p.waitForFunction(()=>!mockups.archives.pending.size);
  assert.deepEqual(posts,[{action:'archive',project:'Test line 1',batch:'Lander looks'}]);
  await p.reload();await p.waitForSelector('.mk3-wall');assert.equal(await p.locator('.mk3-cover').count(),2);
  await p.getByRole('button',{name:'Archived',exact:true}).click();assert.equal(await p.locator('.mk3-cover').count(),1);
  await p.getByRole('button',{name:'Restore',exact:true}).click();await p.waitForFunction(()=>!mockups.archives.restoring.size);
  await p.getByRole('button',{name:'Browse all',exact:true}).click();assert.equal(await p.locator('.mk3-cover').count(),3);
  assert.equal(f.rows[0].verdict,'needs_work');assert.equal(f.rows[0].verdict_note,'Keep spacing feedback');assert.deepEqual(f.errors,[]);
 }finally{await f.browser.close();}
});
test('every batch mode and the frame viewer expose archive, and single-frame archive keeps siblings',async()=>{
 const f=await setup(375);try{const p=f.page;
  for(const kind of ['round','stack','set']){await p.evaluate(kind=>mockups.openBatch(mockups.batches().find(b=>b.kind===kind)),kind);assert.equal(await p.getByRole('button',{name:'Archive batch',exact:true}).count(),1);}
  await p.evaluate(()=>mockups.open(mockups.mockups.find(m=>m.id==='look1')));await p.getByRole('button',{name:'Archive frame',exact:true}).click();
  assert.equal(await p.locator('.mockup-dialog[open]').count(),0);assert.equal(await p.locator('.mockup-archive-toast').getByRole('button',{name:'Undo'}).isVisible(),true);
  await p.clock.runFor(5001);await p.waitForFunction(()=>!mockups.archives.pending.size);
  assert.deepEqual(f.posts,[{action:'archive',project:'Test line 1',mockup_id:'look1'}]);
  assert.equal(f.rows.find(m=>m.id==='look2').status,'pending');
  await p.evaluate(()=>{mockups.reviewView='home';selectProject('Mockups');});await p.getByRole('button',{name:'Archived',exact:true}).click();
  await p.getByRole('button',{name:'Open batch',exact:true}).click();assert.equal(await p.locator('.mk3-frame-card').count(),1);
  await p.getByRole('button',{name:'Open look1',exact:true}).click();await p.getByRole('button',{name:'Restore frame',exact:true}).click();
  await p.waitForFunction(()=>!mockups.archives.restoring.size);assert.equal(f.rows[0].status,'open');assert.equal(f.rows[0].verdict,'needs_work');
 }finally{await f.browser.close();}
});
test('failed archive restores the card, and changing keys cancels queued writes',async()=>{
 const f=await setup();try{const p=f.page;f.fail();
  await p.locator('.mk3-cover').first().getByRole('button',{name:'Archive',exact:true}).click();await p.clock.runFor(5001);await p.waitForFunction(()=>!mockups.archives.pending.size);
  assert.equal(await p.locator('.mk3-cover').count(),3);assert.match(await p.locator('#notice').innerText(),/unavailable/);
  await p.locator('.mk3-cover').first().getByRole('button',{name:'Archive',exact:true}).click();
  await p.evaluate(()=>{key='changed-fixture';resetForKeyChange();mockups.reset();});await p.clock.runFor(6000);assert.equal(f.posts.length,1);
  assert.equal(await p.locator('.mockup-archive-toast').count(),0);
 }finally{await f.browser.close();}
});
test('unsupported backend disables writes, while the Archived filter stays usable',async()=>{
 const f=await setup(1440,{enabled:false});try{assert.equal(await f.page.locator('.mk3-cover').first().getByRole('button',{name:'Archive',exact:true}).isDisabled(),true);assert.equal(f.posts.length,0);await f.page.getByRole('button',{name:'Archived',exact:true}).click();assert.equal(await f.page.locator('.mk3-cover').count(),0);}finally{await f.browser.close();}
});
test('multiple queued archives undo together, and a toast stays operable inside another frame viewer',async()=>{
 const f=await setup();try{const p=f.page;
  await p.locator('.mk3-cover').first().getByRole('button',{name:'Archive',exact:true}).click();
  await p.locator('.mk3-cover').first().getByRole('button',{name:'Archive',exact:true}).click();
  assert.equal(await p.locator('.mk3-cover').count(),1);
  await p.locator('.mockup-archive-toast button').focus();await p.clock.runFor(1000);
  assert.equal(await p.locator('.mockup-archive-toast button').evaluate(b=>document.activeElement===b),true,'countdown preserves keyboard focus');
  await p.evaluate(()=>mockups.open(mockups.mockups.find(m=>m.id==='frame1')));
  await p.locator('.mockup-dialog .mockup-archive-toast').getByRole('button',{name:'Undo all',exact:true}).click();
  await p.getByRole('button',{name:'Close mockup'}).click();assert.equal(await p.locator('.mk3-cover').count(),3);
  await p.clock.runFor(6000);assert.equal(f.posts.length,0);
 }finally{await f.browser.close();}
});
test('stale polls and old-key archive acknowledgements cannot overwrite current data',async()=>{
 const f=await setup();try{const p=f.page;let release;
  const gate=new Promise(r=>release=r);let received;
  const started=new Promise(r=>received=r);
  const stale=structuredClone(f.rows);
  await p.route('**/functions/v1/ted-mockups*',async route=>{
   if(route.request().method()!=='GET')return route.fallback();
   received();await gate;return route.fulfill({json:{mockups:stale,pins:[],archive_enabled:true}});
  });
  await p.evaluate(()=>void mockups.load());await started;
  await p.locator('.mk3-cover').first().getByRole('button',{name:'Archive',exact:true}).click();
  await p.clock.runFor(5001);await p.waitForFunction(()=>!mockups.archives.pending.size);
  release();await p.waitForFunction(()=>!mockups.loading);assert.equal(await p.locator('.mk3-cover').count(),2);
  let finish;f.hold(new Promise(r=>finish=r));
  await p.locator('.mk3-cover').first().getByRole('button',{name:'Archive',exact:true}).click();await p.clock.runFor(5001);
  await p.waitForFunction(()=>[...mockups.archives.pending.values()].some(e=>e.phase==='saving'));
  await p.evaluate(()=>{key='new-fixture-key';resetForKeyChange();mockups.reset();});finish();await p.waitForTimeout(50);
  assert.equal(await p.evaluate(()=>mockups.mockups.length),0);assert.equal(await p.locator('.mockup-archive-toast').count(),0);
 }finally{await f.browser.close();}
});
test('restore failures keep the archived frame available for retry',async()=>{
 const f=await setup();try{const p=f.page;
  await p.locator('.mk3-cover').first().getByRole('button',{name:'Archive',exact:true}).click();await p.clock.runFor(5001);await p.waitForFunction(()=>!mockups.archives.pending.size);
  await p.getByRole('button',{name:'Archived',exact:true}).click();f.fail();await p.getByRole('button',{name:'Restore',exact:true}).click();await p.waitForFunction(()=>!mockups.archives.restoring.size);
  assert.equal(await p.locator('.mk3-cover').count(),1);assert.match(await p.locator('#notice').innerText(),/unavailable/);
 }finally{await f.browser.close();}
});
test('page exit saves a queued archive once using keepalive',async()=>{
 const f=await setup();try{const p=f.page;
  await p.locator('.mk3-cover').first().getByRole('button',{name:'Archive',exact:true}).click();
  await p.evaluate(()=>{const original=window.fetch;window.fetch=(url,options)=>{window.archiveKeepalive=options.keepalive;return original(url,options);};window.dispatchEvent(new Event('pagehide'));window.dispatchEvent(new Event('pagehide'));});
  await p.waitForFunction(()=>!mockups.archives.pending.size);assert.equal(await p.evaluate(()=>window.archiveKeepalive),true);
  await p.clock.runFor(6000);assert.equal(f.posts.length,1);assert.equal(f.posts[0].action,'archive');
 }finally{await f.browser.close();}
});
test('archive controls and toast fit 375, 1440, and 2560 pixel screens',async()=>{
 const out=process.env.QA_OUT||'../screenshots';fs.mkdirSync(out,{recursive:true});
 for(const width of [375,1440,2560]){const f=await setup(width);try{const p=f.page;await p.evaluate(()=>document.fonts.ready);
  const shot=async(name)=>{const check=await clip(p);assert.equal(check.scrollWidth,width,name);assert.deepEqual(check.clips,[],name);assert.equal(check.emDash,false);assert.deepEqual(f.errors,[]);await p.screenshot({path:path.join(out,name+'-'+width+'.png'),fullPage:true});};
  await shot('list');await p.evaluate(()=>mockups.openBatch(mockups.batches().find(b=>b.kind==='set')));await shot('batch');
  await p.getByRole('button',{name:'Open frame1',exact:true}).click();await shot('viewer');await p.getByRole('button',{name:'Archive frame',exact:true}).click();await shot('undo');
  await p.clock.runFor(5001);await p.waitForFunction(()=>!mockups.archives.pending.size);await p.getByRole('button',{name:'Archived',exact:true}).click();assert.equal(await p.getByRole('heading',{name:'ARCHIVED BATCHES.',exact:true}).count(),1);await shot('archived');
 }finally{await f.browser.close();}}
});
