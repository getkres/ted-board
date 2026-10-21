const {chromium}=require('playwright');
const assert=require('node:assert/strict'),http=require('node:http'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const root=path.resolve(__dirname,'..');const server=http.createServer((req,res)=>{const file=path.join(root,req.url==='/'?'index.html':req.url);res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file))}).listen(0,'127.0.0.1');await new Promise(r=>server.once('listening',r));
 const browser=await chromium.launch({headless:true});
 try{
  const context=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let reads=0;const fixtures=[['running','checking the build',4],['blocked','waiting for db review',1],['waiting_on_you','click verify',2],['stale','old work',121],['empty',null,null]].map(([id,line,age])=>({id,title:id,updated_at:new Date().toISOString(),project:'Fictora',section:'ted_doing',live_state:id==='stale'?'running':id,live_status:line,live_status_at:age?new Date(Date.now()-age*60000).toISOString():null}));
  await context.route('**/functions/v1/ted-mockups*',r=>r.fulfill({json:{mockups:[],pins:[]}}));
  await context.route('**/functions/v1/ted-board*',r=>{if(r.request().url().includes('resource=jobs'))return r.fulfill({json:{jobs:[{card_id:'running',status:'running',pid:123,heartbeat_at:new Date().toISOString()},{card_id:'blocked',status:'queued',pid:null,heartbeat_at:new Date().toISOString()}],approvals:[]}});reads++;return r.fulfill({json:{cards:fixtures}})});
  await page.goto('http://127.0.0.1:'+server.address().port+'/#k=test&tab=Fictora');await page.locator('[data-card-id="running"]').waitFor();
  await page.waitForFunction(()=>document.querySelector('.work-summary')?.textContent==='1 running · 1 queued · 3 stale');
  const card=id=>page.locator('[data-card-id="'+id+'"]');
  assert.match(await card('running').locator('.live-strip').innerText(),/checking the build.*updated 4m ago/s);
  assert.equal(await card('blocked').locator('.live-strip').getAttribute('data-state'),'blocked');assert.equal(await card('waiting_on_you').locator('.live-strip').getAttribute('data-state'),'waiting_on_you');
  assert.match(await card('stale').locator('.live-strip').innerText(),/stale, ted's checking/);assert.equal(await card('stale').locator('.live-strip').getAttribute('data-state'),'blocked');
  assert.match(await card('empty').locator('.live-strip').innerText(),/waiting for a live update/);
  assert.equal(await card('running').locator('.live-strip').evaluate(e=>getComputedStyle(e,'::before').animationName),'none');
  const draft=card('running').locator('textarea');await draft.fill('keep my draft');await draft.focus();fixtures[0].live_status='checking changed work';
  await page.evaluate(()=>pollCards());assert.equal(await draft.inputValue(),'keep my draft');assert.equal(await draft.evaluate(e=>document.activeElement===e),true);assert.match(await card('running').locator('.live-strip').innerText(),/checking changed work/);
  await page.locator('h1').click();fixtures[1].section='done';await page.evaluate(()=>pollCards());assert.equal(await card('blocked').locator('xpath=..').getAttribute('data-section'),'done');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.deepEqual(errors,[]);assert.ok(reads>=3);
  console.log('PASS running, queued, and stale summary, live strips, colors, stale state, missing state, reduced motion, polling, draft/focus preservation, section changes, and mobile overflow');
 }finally{await browser.close();await new Promise(r=>server.close(r))}
})().catch(e=>{console.error(e);process.exitCode=1});
