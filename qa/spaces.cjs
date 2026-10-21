const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),context={window:{}};vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'spaces-v3.js'),'utf8'),context);
const S=context.window.SpacesV3Data,order=['fictora','bookish','luvo','wcd','skyauto','bld','kres','dgc','personal','ted'],names={luvo:'Luvo',fictora:'Fictora',skyauto:'Sky Auto',bld:'BLD and Thomas Yang',dgc:"Dad's Golf Club"};
assert.equal(S.line('Sky Auto',{order,names}),'skyauto');
const pods=S.normalize('luvo',[{kind:'pods',key:'luvo',payload:{health:'risk',pods:[{id:'media',name:'Media',agents:[{id:'buyer',model:null}]}]}}],[{line:'luvo',pod_id:'data',label:'Data',headline:'Ingest failed',health:'red'}],{order,names});
assert.equal(pods.pods.length,2);assert.equal(pods.health,'risk');assert.equal(pods.pods[0].agents[0].id,'buyer');assert.equal(pods.pods[1].now,'Ingest failed');assert.equal(pods.pods[1].state,'not logged');assert.equal(pods.pods[1].last_run,undefined);
assert.equal(S.normalize('ted',[],[],{order,names}).health,'not logged');assert.equal(S.normalize('ted',[],[],{order,names}).logged,false);
console.log('Spaces normalization: 9 assertions passed.');
if(process.argv.includes('--browser'))(async()=>{
 const {chromium,fixture,clip}=require('./browser.cjs'),out=process.env.QA_OUT||'/tmp/cc-v3-spaces-qa';fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true}),report=[];
 for(const width of [390,1440]){
  const page=await browser.newPage({viewport:{width,height:width===390?844:960}}),errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',c=>{if(c.type()==='error')errors.push(c.text())});await fixture(page);await page.goto('http://127.0.0.1:8763/#k=fixture-only&tab=inbox');await page.waitForSelector('.v3-paper');
  for(const route of ['spaces','space:luvo','pod:luvo/media','agent:luvo/meta-media-buyer']){
   await page.evaluate(route=>selectProject(route),route);await page.evaluate(()=>document.fonts.ready);const qa=await clip(page);assert.deepEqual(errors,[],route+' console');assert.equal(qa.scrollWidth,width,route+' scroll');assert.deepEqual(qa.clips,[],route+' clip');assert.equal(qa.emDash,false);assert.deepEqual(qa.gradients,[]);await page.screenshot({path:path.join(out,route.replace(/[:/]/g,'-')+'-'+width+'.png'),fullPage:true});report.push({route,width,...qa});
  }
  assert.match(await page.locator('#main').innerText(),/Insights ingest rejected/);assert.match(await page.locator('#main').innerText(),/Model: not logged/);assert.match(await page.locator('#main').innerText(),/Approval not logged/);assert.equal(await page.getByRole('link',{name:'Open output'}).getAttribute('href'),'https://example.com/report');
  await page.evaluate(()=>selectProject('space:luvo'));assert.equal(await page.locator('.sp-pod-card .sp-cub svg').evaluate(e=>Math.round(e.getBoundingClientRect().width)),46);assert.match(await page.locator('#main').innerText(),/At risk/);
  await page.keyboard.press(']');assert.match(page.url(),/tab=space%3Awcd/);await page.keyboard.press('[');assert.match(page.url(),/tab=space%3Aluvo/);await page.keyboard.press('p');assert.equal(await page.evaluate(()=>document.activeElement.id),'sp-pods-heading');await page.keyboard.press('Escape');assert.match(page.url(),/tab=inbox/);
  await page.evaluate(()=>{selectProject('space:luvo');const main=document.getElementById('main');main.dispatchEvent(new PointerEvent('pointerdown',{pointerType:'touch',clientX:240,clientY:300,bubbles:true}));main.dispatchEvent(new PointerEvent('pointerup',{pointerType:'touch',clientX:60,clientY:310,bubbles:true}))});assert.match(page.url(),/tab=space%3Awcd/);
  await page.evaluate(()=>{const pod=v3.snapshots.find(s=>s.kind==='pods').payload.pods[0];pod.agents[0].name='very-long-agent-name-'.repeat(20);selectProject('agent:luvo/meta-media-buyer')});assert.deepEqual((await clip(page)).clips,[]);
  await page.evaluate(()=>{v3.snapshots=[];state.podPulse=[];selectProject('agent:luvo/missing')});assert.match(await page.locator('#main').innerText(),/Outputs not logged/);await page.close();
 }
 await browser.close();fs.writeFileSync(path.join(out,'spaces-results.json'),JSON.stringify(report,null,2));console.log('Spaces browser checks passed: '+report.length+' screenshots, keyboard, swipe, links, missing data, and long names.');
})().catch(e=>{console.error(e);process.exit(1)});
