const {test,before,after}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium,fixture,clip}=require('./browser.cjs');
// This is the complete legacy board envelope: no lines, snapshots, or card line/kind.
const live={
 cards:[{id:'project-call',project:'Fixture beta',section:'needs_you',title:'Review the draft',body:'Choose the recorded action.',options:[{label:'Approve',value:'yes'}]}],
 pod_pulse:[
  {project:'Fixture beta',pod_id:'review',label:'Review pod',headline:'Waiting for the draft review.',health:'amber',last_update_at:'2026-10-21T20:00:00Z',shipped_today:['Draft prepared'],testing:[]},
  {project:'Fixture alpha',pod_id:'data',label:'Data pod',headline:'Reading the report.',health:'green',last_update_at:'2026-10-21T20:00:00Z',shipped_today:[],testing:['Report check']},
  {project:'Fixture beta',pod_id:'copy',label:'Copy pod',headline:'Checking the wording.',health:'green',last_update_at:'2026-10-21T20:00:00Z',shipped_today:[],testing:[]}
 ]
};
let browser;before(async()=>{browser=await chromium.launch()});after(async()=>{await browser.close()});
async function open(width){
 const page=await browser.newPage({viewport:{width,height:width===390?844:960}});await fixture(page);
 await page.route('**/functions/v1/ted-board?key=*',r=>{
  if(r.request().method()!=='GET'||new URL(r.request().url()).searchParams.has('resource'))return r.fallback();
  return r.fulfill({json:live});
 });
 await page.goto('http://127.0.0.1:8763/#k=fixture-only');await page.waitForSelector('.v3-paper');return page;
}
async function capture(page,name,width){
 await page.evaluate(()=>document.fonts.ready);const qa=await clip(page);
 assert.equal(qa.scrollWidth,width,name+' horizontal overflow');assert.deepEqual(qa.clips,[],name+' clipped text');assert.equal(qa.emDash,false);assert.deepEqual(qa.gradients,[]);
 const out=path.join(process.env.QA_OUT||'../qa-evidence/pr8-fix2','live-feed');fs.mkdirSync(out,{recursive:true});
 await page.screenshot({path:path.join(out,name+'-'+width+'.png'),fullPage:true});fs.writeFileSync(path.join(out,name+'-'+width+'.json'),JSON.stringify({name,width,...qa},null,2));
}
for(const width of [390,1440])test('live cards and pod pulse populate Spaces, Roadmap, and pod details '+width,async()=>{
 const page=await open(width),errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',c=>{if(c.type()==='error')errors.push(c.text())});
 try{
  assert.equal(await page.locator('#v3-tab-1 .tab-count').textContent(),'2');
  await page.getByRole('tab',{name:/Spaces/}).click();assert.deepEqual(await page.locator('.sp-line-name').allTextContents(),['Fixture beta','Fixture alpha']);
  assert.match(await page.locator('.sp-space-tile').first().innerText(),/2 pods/);await capture(page,'spaces',width);
  await page.locator('.sp-line-name').first().click();assert.equal(await page.locator('.sp-pod-card').count(),2);
  assert.match(await page.locator('.sp-side').innerText(),/Review the draft/);assert.match(await page.locator('.sp-pod-grid').innerText(),/Waiting for the draft review/);await capture(page,'space',width);
  await page.locator('.sp-pod-card').getByRole('button',{name:'Review pod',exact:true}).click();assert.match(await page.locator('#main').innerText(),/Latest pod pulse/i);assert.match(await page.locator('#main').innerText(),/Draft prepared/);await capture(page,'pod',width);
  await page.getByRole('tab',{name:/Roadmap/}).click();assert.deepEqual(await page.locator('.rm-line-button').allTextContents(),['Fixture beta','Fixture alpha']);await capture(page,'roadmap',width);
  await page.locator('.rm-line-button').first().click();assert.equal(await page.locator('.rm-column').count(),4);assert.equal(await page.locator('.rm-item').count(),0);assert.match(await page.locator('.rm-columns').innerText(),/Not logged/);await capture(page,'roadmap-line',width);
  // A snapshots-only update must retain the live feed's line directory.
  const before=await page.evaluate(()=>ControlCenterV3.order);await page.evaluate(()=>{v3.accept({snapshots:[]});render()});assert.deepEqual(await page.evaluate(()=>ControlCenterV3.order),before);
  assert.deepEqual(errors,[]);
 }finally{await page.close()}
});
test('pod projects refresh, preserve distinct labels, and yield to explicit metadata',async()=>{
 const page=await open(390);
 try{
  await page.evaluate(()=>{v3.accept({cards:[],pod_pulse:[{project:'A&B'},{project:'A B'},{project:'A&B'},{project:'東京'},{project:'  '},null]});selectProject('spaces')});
  assert.deepEqual(await page.locator('.sp-line-name').allTextContents(),['A&B','A B','東京']);
  assert.equal(new Set(await page.evaluate(()=>ControlCenterV3.order)).size,3);
  await page.evaluate(()=>{state.podPulse=[{project:'A B',pod_id:'one',label:'Only this pod',headline:'Second project'}];render()});
  assert.match(await page.locator('.sp-space-tile').nth(1).innerText(),/1 pods/);assert.doesNotMatch(await page.locator('.sp-space-tile').first().innerText(),/1 pods/);
  await page.evaluate(()=>{v3.accept({cards:[],pod_pulse:[{project:'Replacement fixture'}]});render()});assert.deepEqual(await page.locator('.sp-line-name').allTextContents(),['Replacement fixture']);
  await page.evaluate(()=>{v3.accept({cards:[],pod_pulse:[],lines:[]});render()});assert.equal(await page.locator('.sp-line-name').count(),0);
  await page.evaluate(()=>{v3.accept({cards:[],pod_pulse:[{project:'Pulse fixture'}],lines:[{id:'explicit',name:'Explicit fixture'}]});render()});assert.deepEqual(await page.locator('.sp-line-name').allTextContents(),['Explicit fixture']);
  await page.evaluate(()=>{v3.accept({cards:[],pod_pulse:[{project:'Current pulse fixture'}]});render()});assert.deepEqual(await page.locator('.sp-line-name').allTextContents(),['Current pulse fixture']);
  await page.evaluate(()=>{v3.accept({cards:[]});render()});assert.equal(await page.locator('.sp-line-name').count(),0);
  await page.evaluate(()=>resetForKeyChange());assert.deepEqual(await page.evaluate(()=>ControlCenterV3.order),[]);
 }finally{await page.close()}
});
test('case-distinct project labels keep their own cards, pods, and stable routes',async()=>{
 const page=await open(390);
 try{
  const feed={cards:[{id:'upper',project:'Fixture case',section:'needs_you',title:'Upper project call'},{id:'lower',project:'fixture case',section:'needs_you',title:'Lower project call'}],pod_pulse:[{project:'Fixture case',pod_id:'upper-pod',label:'Upper pod'},{project:'fixture case',pod_id:'lower-pod',label:'Lower pod'}]};
  await page.evaluate(feed=>{state.cards=feed.cards;applyPodPulse(feed);v3.accept(feed);selectProject('spaces')},feed);
  assert.deepEqual(await page.evaluate(()=>state.cards.map(card=>ControlCenterV3.names[v3.lineOf(card)])),['Fixture case','fixture case']);
  assert.deepEqual(await page.evaluate(()=>ControlCenterV3.order.map(id=>v3.spData(id).pods.map(pod=>pod.id))),[['upper-pod'],['lower-pod']]);
  const ids=await page.evaluate(()=>ControlCenterV3.order);feed.pod_pulse.reverse();await page.evaluate(feed=>v3.accept(feed),feed);assert.deepEqual(await page.evaluate(()=>ControlCenterV3.order),ids.reverse());
 }finally{await page.close()}
});
test('card polls preserve a snapshot directory while its resource is unavailable',async()=>{
 const page=await open(390);
 try{
  await page.route('**/functions/v1/ted-board?key=*&resource=snapshots',r=>r.fulfill({status:503,json:{error:'Snapshots temporarily unavailable'}}));
  await page.evaluate(()=>{v3.accept({snapshots:[{kind:'lines',payload:{items:[{id:'snapshot-line',name:'Snapshot fixture'}]}}]});v3.accept({cards:[],pod_pulse:[],capabilities:{snapshots:true}})});
  assert.deepEqual(await page.evaluate(()=>ControlCenterV3.order),['snapshot-line']);
  await page.waitForFunction(()=>!v3.snapshotLoading);assert.deepEqual(await page.evaluate(()=>ControlCenterV3.order),['snapshot-line']);
 }finally{await page.close()}
});
test('project labels that resemble routes map by name',async()=>{
 const page=await open(390);
 try{
  const feed={cards:[{id:'one',project:'A',section:'needs_you',title:'First call'},{id:'two',project:'project-41',section:'needs_you',title:'Second call'}],pod_pulse:[{project:'A',pod_id:'first',label:'First pod'},{project:'project-41',pod_id:'second',label:'Second pod'}]};
  await page.evaluate(feed=>{state.cards=feed.cards;applyPodPulse(feed);v3.accept(feed)},feed);
  assert.deepEqual(await page.evaluate(()=>state.cards.map(card=>ControlCenterV3.names[v3.lineOf(card)])),['A','project-41']);
  assert.deepEqual(await page.evaluate(()=>ControlCenterV3.order.map(id=>v3.spData(id).pods.map(pod=>pod.id))),[['first'],['second']]);
 }finally{await page.close()}
});
test('legacy line IDs and pod project labels stay unified',async()=>{
 const page=await open(390);
 try{
  await page.evaluate(()=>{const feed={cards:[{id:'legacy',line:'legacy-line',project:'Legacy fixture',section:'needs_you',title:'Legacy call'}],pod_pulse:[{project:'Legacy fixture',pod_id:'legacy-pod',label:'Legacy pod'}],snapshots:[]};state.cards=feed.cards;applyPodPulse(feed);v3.accept(feed);selectProject('spaces')});
  assert.deepEqual(await page.locator('.sp-line-name').allTextContents(),['Legacy fixture']);assert.deepEqual(await page.evaluate(()=>ControlCenterV3.order),['legacy-line']);
  assert.equal(await page.evaluate(()=>v3.lineOf(state.cards[0])),'legacy-line');assert.equal(await page.evaluate(()=>v3.spData('legacy-line').pods.length),1);
 }finally{await page.close()}
});
test('snapshot line names reconcile with project-only pulse labels',async()=>{
 const page=await open(390);
 try{
  await page.evaluate(()=>{const feed={cards:[],pod_pulse:[{project:'Snapshot fixture',pod_id:'pulse',label:'Pulse pod'}],snapshots:[{kind:'roadmap',key:'snapshot-line',payload:{line_name:'Snapshot fixture',now:[{title:'Recorded work'}]}},{kind:'pods',key:'snapshot-line',payload:{line_name:'Snapshot fixture',pods:[{id:'recorded',name:'Recorded pod'}]}}]};state.cards=feed.cards;applyPodPulse(feed);v3.accept(feed);selectProject('spaces')});
  assert.deepEqual(await page.evaluate(()=>ControlCenterV3.order),['snapshot-line']);assert.equal(await page.evaluate(()=>v3.roadData('snapshot-line').now[0].title),'Recorded work');assert.deepEqual(await page.evaluate(()=>v3.spData('snapshot-line').pods.map(pod=>pod.id)),['recorded','pulse']);
 }finally{await page.close()}
});
