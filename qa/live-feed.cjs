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
function card(id,project,section,title,extra={}){
 return {id,project,section,title,body:'Recorded board work.',live_status:'Waiting for the next update.',live_state:'idle',decision_kind:null,priority_value:1,effort_seconds:60,updated_at:new Date().toISOString(),sort:0,...extra};
}
async function openLive(width,board,jobs={jobs:[],approvals:[]}){
 const page=await browser.newPage({viewport:{width,height:width===390?844:960}}),feed={board,jobs},errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',c=>{if(c.type()==='error')errors.push(c.text())});await fixture(page);
 await page.route('**/functions/v1/ted-board?key=*',r=>{
  if(r.request().method()!=='GET')return r.fallback();
  const resource=new URL(r.request().url()).searchParams.get('resource');
  if(resource&&resource!=='jobs')return r.fallback();
  return r.fulfill({json:resource==='jobs'?feed.jobs:feed.board});
 });
 await page.goto('http://127.0.0.1:8763/#k=fixture-only');await page.waitForSelector('.v3-paper');await page.waitForFunction(()=>state.jobsLoaded&&!state.jobsLoading);
 return {page,errors,async reload(next){feed.board=next;await page.evaluate(()=>load(true));await page.waitForFunction(()=>!state.loading&&!state.jobsLoading)}};
}
function countText(text,count,label){
 assert.match(text,new RegExp('(?:\\b'+count+'\\s+'+label+'\\b|\\b'+label+'\\s*:?\\s*'+count+'\\b)','i'));
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
  await page.locator('.rm-line-button').first().click();assert.equal(await page.locator('.rm-column').count(),4);assert.deepEqual(await page.locator('.rm-column[data-lane="later"] .rm-item h3').allTextContents(),['Review the draft']);await capture(page,'roadmap-line',width);
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
  await page.evaluate(()=>{v3.accept({cards:[{id:'c1',project:'Card fixture',section:'up_next',title:'One'},{id:'c2',project:'Card fixture',section:'ted_doing',title:'Two'},{id:'c3',project:'Other fixture',section:'up_next',title:'Three'}],pod_pulse:[]});selectProject('spaces')});assert.deepEqual(await page.locator('.sp-line-name').allTextContents(),['Card fixture','Other fixture']);
  await page.evaluate(()=>{v3.accept({cards:[],pod_pulse:[],lines:[]});render()});assert.equal(await page.locator('.sp-line-name').count(),0);
  await page.evaluate(()=>{v3.accept({cards:[],pod_pulse:[{project:'Pulse fixture'}],lines:[{id:'explicit',name:'Explicit fixture'}]});render()});assert.deepEqual(await page.locator('.sp-line-name').allTextContents(),['Explicit fixture']);
  await page.evaluate(()=>{v3.accept({cards:[],pod_pulse:[{project:'Current pulse fixture'}]});render()});assert.deepEqual(await page.locator('.sp-line-name').allTextContents(),['Current pulse fixture']);
  await page.evaluate(()=>{v3.accept({cards:[]});render()});assert.equal(await page.locator('.sp-line-name').count(),0);
  await page.evaluate(()=>resetForKeyChange());assert.deepEqual(await page.evaluate(()=>ControlCenterV3.order),[]);
 }finally{await page.close()}
});
test('case variants share their cards, pods, and stable routes',async()=>{
 const page=await open(390);
 try{
  const feed={cards:[{id:'upper',project:'Fixture case',section:'needs_you',title:'Upper project call'},{id:'lower',project:'fixture case',section:'needs_you',title:'Lower project call'}],pod_pulse:[{project:'Fixture case',pod_id:'upper-pod',label:'Upper pod'},{project:'fixture case',pod_id:'lower-pod',label:'Lower pod'}]};
  await page.evaluate(feed=>{state.cards=feed.cards;applyPodPulse(feed);v3.accept(feed);selectProject('spaces')},feed);
  assert.deepEqual(await page.evaluate(()=>state.cards.map(card=>ControlCenterV3.names[v3.lineOf(card)])),['Fixture case','Fixture case']);
  assert.deepEqual(await page.evaluate(()=>ControlCenterV3.order.map(id=>v3.spData(id).pods.map(pod=>pod.id))),[['upper-pod','lower-pod']]);
  const ids=await page.evaluate(()=>ControlCenterV3.order);feed.pod_pulse.reverse();await page.evaluate(feed=>v3.accept(feed),feed);assert.deepEqual(await page.evaluate(()=>ControlCenterV3.order),ids);
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
test('HTTP snapshot capability downgrade discards cached lines and work for current cards',async()=>{
 const board={cards:[card('current-work','Harbor Studio','ted_doing','Previous board work',{line:'current'})],pod_pulse:[],capabilities:{snapshots:true},snapshots:[
  {kind:'lines',payload:{items:[{id:'current',name:'Harbor Studio'},{id:'retired',name:'Archive Studio'}]}},
  {kind:'pods',key:'current',payload:{line_name:'Harbor Studio',now:'Stale pod work',pods:[{id:'stale-pod',name:'Stale pod',state:'running',now:'Stale pod work'}]}},
  {kind:'pods',key:'retired',payload:{line_name:'Archive Studio',now:'Retired pod work',pods:[]}},
  {kind:'roadmap',key:'current',payload:{line_name:'Harbor Studio',now:[{title:'Stale roadmap work'}],next:[],later:[],shipped:[]}},
  {kind:'roadmap',key:'retired',payload:{line_name:'Archive Studio',now:[{title:'Retired roadmap work'}],next:[],later:[],shipped:[]}}
 ]};
 const {page,reload,errors}=await openLive(390,board);
 try{
  await page.getByRole('tab',{name:/Spaces/}).click();
  assert.deepEqual(await page.locator('.sp-line-name').allTextContents(),['Harbor Studio','Archive Studio']);
  assert.match(await page.locator('.sp-space-tile').first().innerText(),/Stale pod work/);
  await page.getByRole('tab',{name:/Roadmap/}).click();assert.match(await page.locator('.rm-wall').innerText(),/Stale roadmap work/);
  await reload({cards:[
   card('current-work','Harbor Studio','ted_doing','Prepare the current report',{live_state:'running',live_status:'Checking the current source.'}),
   card('current-next','Harbor Studio','up_next','Prepare the next review')
  ],pod_pulse:[],capabilities:{snapshots:false}});
  await page.getByRole('tab',{name:/Spaces/}).click();
  assert.deepEqual(await page.locator('.sp-line-name').allTextContents(),['Harbor Studio']);
  const text=await page.locator('.sp-space-tile').innerText();
  countText(text,1,'in progress');countText(text,1,'up next');
  assert.match(text,/Prepare the current report/);assert.match(text,/Checking the current source\./);
  assert.doesNotMatch(text,/Stale|Retired|Previous board work/);
  await page.getByRole('tab',{name:/Roadmap/}).click();
  assert.deepEqual(await page.locator('.rm-line-button').allTextContents(),['Harbor Studio']);
  assert.match(await page.locator('.rm-wall').innerText(),/Prepare the current report/);assert.match(await page.locator('.rm-wall').innerText(),/Prepare the next review/);
  assert.doesNotMatch(await page.locator('.rm-wall').innerText(),/Stale|Retired|Previous board work/);
  assert.deepEqual(await page.evaluate(()=>({snapshots:v3.snapshots.length,lineSnapshots:v3.lineSnapshots.length})),{snapshots:0,lineSnapshots:0});
  assert.deepEqual(errors,[]);
 }finally{await page.close()}
});
test('HTTP legacy project aliases keep cards and pulse in one recorded space',async()=>{
 const board={cards:[card('recorded-call','Project label','needs_you','Review the recorded brief',{line:'recorded',line_name:'Display label'})],pod_pulse:[
  {project:'Project label',pod_id:'one',label:'Recorded pod',headline:'Preparing the recorded brief.',health:'green',last_update_at:new Date().toISOString(),shipped_today:[],testing:[]}
 ],capabilities:{snapshots:false}};
 const {page,errors}=await openLive(390,board);
 try{
  await page.getByRole('tab',{name:/Spaces/}).click();
  assert.equal(await page.locator('.sp-line-name').count(),1);
  assert.equal(await page.locator('#v3-tab-1 .tab-count').textContent(),'1');
  await page.locator('.sp-line-name').click();
  assert.equal(await page.evaluate(()=>state.project),'space:recorded');
  assert.deepEqual(await page.locator('.sp-pod-card .sp-text-link').allTextContents(),['Recorded pod']);
  assert.deepEqual(await page.locator('.sp-side .sp-side-row .sp-text-link').allTextContents(),['Review the recorded brief']);
  assert.equal(await page.evaluate(()=>v3.lineOf(state.cards[0])),'recorded');
  assert.deepEqual(errors,[]);
 }finally{await page.close()}
});
test('HTTP explicit empty snapshots retain precedence over live card fallback',async()=>{
 const board={cards:[card('current-work','Harbor Studio','ted_doing','Card work awaiting a snapshot',{line:'recorded'})],pod_pulse:[],capabilities:{snapshots:false},snapshots:[
  {kind:'pods',key:'recorded',payload:{line_name:'Harbor Studio',pods:[]}},
  {kind:'roadmap',key:'recorded',payload:{line_name:'Harbor Studio',now:[],next:[],later:[],shipped:[]}}
 ]};
 const {page,errors}=await openLive(390,board);
 try{
  await page.getByRole('tab',{name:/Spaces/}).click();
  assert.equal(await page.locator('.sp-space-tile').count(),1);
  assert.match(await page.locator('.sp-space-tile .sp-count').innerText(),/0 pods/);
  assert.doesNotMatch(await page.locator('.sp-space-tile').innerText(),/Card work awaiting a snapshot/);
  await page.getByRole('tab',{name:/Roadmap/}).click();
  assert.deepEqual(await page.locator('.rm-wall-cell .rm-count').allTextContents(),['0','0','0','0']);
  assert.doesNotMatch(await page.locator('.rm-wall').innerText(),/Card work awaiting a snapshot/);
  await page.locator('.rm-line-button').click();assert.equal(await page.locator('.rm-item').count(),0);
  assert.deepEqual(errors,[]);
 }finally{await page.close()}
});
test('HTTP card projects trim and deduplicate case while preserving spelling and punctuation',async()=>{
 const board={cards:[
  card('studio-one','  harbor studio  ','needs_you','Review the first brief'),
  card('studio-two','Harbor Studio','needs_you','Review the second brief'),
  card('studio-three','  Harbor Studio  ','needs_you','Review the third brief'),
  card('studio-four','Harbor Studio','needs_you','Review the fourth brief'),
  card('studio-upper','HARBOR STUDIO','needs_you','Review the fifth brief'),
  card('ampersand','Harbor & Co','needs_you','Review the design brief'),
  card('plain','Harbor Co','needs_you','Review the research brief')
 ],pod_pulse:[]};
 const {page,reload,errors}=await openLive(390,board);
 try{
  await page.getByRole('tab',{name:/Spaces/}).click();
  assert.deepEqual(await page.locator('.sp-line-name').allTextContents(),['Harbor Studio','Harbor & Co','Harbor Co']);
  assert.equal(await page.locator('#v3-tab-1 .tab-count').textContent(),'3');
  await page.getByRole('button',{name:'Harbor Studio',exact:true}).click();
  assert.deepEqual(await page.locator('.sp-side .sp-side-row .sp-text-link').allTextContents(),['Review the first brief','Review the second brief','Review the third brief','Review the fourth brief','Review the fifth brief']);
  const route=await page.evaluate(()=>state.project);
  await reload({cards:board.cards.map(c=>({...c,project:c.id.startsWith('studio-')?'  HARBOR STUDIO  ':c.project})),pod_pulse:[]});
  assert.equal(await page.evaluate(()=>state.project),route,'case-only changes retain the open space route');
  assert.equal(await page.locator('.sp-side .sp-side-row .sp-text-link').count(),5);
  await page.getByRole('tab',{name:/Spaces/}).click();
  assert.deepEqual(await page.locator('.sp-line-name').allTextContents(),['HARBOR STUDIO','Harbor & Co','Harbor Co']);
  await page.getByRole('button',{name:'Harbor & Co',exact:true}).click();
  assert.deepEqual(await page.locator('.sp-side .sp-side-row .sp-text-link').allTextContents(),['Review the design brief']);
  await page.getByRole('tab',{name:/Spaces/}).click();await page.getByRole('button',{name:'Harbor Co',exact:true}).click();
  assert.deepEqual(await page.locator('.sp-side .sp-side-row .sp-text-link').allTextContents(),['Review the research brief']);
  assert.deepEqual(errors,[]);
 }finally{await page.close()}
});
for(const width of [390,1440])test('HTTP cards and jobs supply Spaces counts, current work, and known zeroes '+width,async()=>{
 const at=minutes=>new Date(Date.now()-minutes*60000).toISOString(),board={cards:[
  card('live-call','Harbor Studio','yours','Choose the launch wording',{live_state:'waiting_on_you'}),
  card('recorded-call','Harbor Studio','needs_you','Review the proposed schedule'),
  card('top-work','Harbor Studio','ted_doing','Prepare the launch brief',{priority_value:10,live_state:'running',live_status:'Checking the latest report.'}),
  card('approval-work','Harbor Studio','ted_doing','Check the presentation',{priority_value:8,live_state:'blocked'}),
  card('fresh-work','Harbor Studio','ted_doing','Compile the notes',{live_state:'running'}),
  card('next-one','Harbor Studio','up_next','Prepare the reference set'),
  card('next-two','Harbor Studio','up_next','Draft the handoff'),
  card('closed','Harbor Studio','done','Archive the approved draft'),
  card('killed','Harbor Studio','killed','Discard the old outline'),
  card('quiet','Quiet Archive','done','Archive the weekly report')
 ],pod_pulse:[]},jobs={jobs:[
  {card_id:'top-work',status:'running',last_line:'Inspecting the report.',heartbeat_at:at(21)},
  {card_id:'fresh-work',status:'running',last_line:'Preparing the notes.',heartbeat_at:at(19)},
  {card_id:'approval-work',status:'done',last_line:'Presentation ready.',heartbeat_at:at(60)}
 ],approvals:[
  {id:'call-approval',card_id:'live-call',status:'pending',summary:'Review the wording',content:'Recorded wording.'},
  {id:'work-approval',card_id:'approval-work',status:'pending',summary:'Review the presentation',content:'Recorded presentation.'},
  {id:'work-approval-two',card_id:'approval-work',status:'pending',summary:'Review the attachment',content:'Recorded attachment.'},
  {id:'closed-approval',card_id:'closed',status:'pending',summary:'Closed review',content:'Archived draft.'},
  {id:'killed-approval',card_id:'killed',status:'pending',summary:'Discarded review',content:'Discarded outline.'},
  {id:'approved',card_id:'fresh-work',status:'approved',summary:'Completed review',content:'Approved notes.'}
 ]};
 const {page,errors}=await openLive(width,board,jobs);
 try{
  await page.getByRole('tab',{name:/Spaces/}).click();
  const active=page.locator('.sp-space-tile').filter({has:page.getByRole('button',{name:'Harbor Studio',exact:true})}),text=await active.innerText();
  countText(text,3,'your calls');countText(text,3,'in progress');countText(text,2,'up next');countText(text,1,'stuck');
  assert.match(text,/Prepare the launch brief/);assert.match(text,/Checking the latest report\./);
  const quiet=page.locator('.sp-space-tile').filter({has:page.getByRole('button',{name:'Quiet Archive',exact:true})}),zeroText=await quiet.innerText();
  for(const label of ['your calls','in progress','up next','stuck'])countText(zeroText,0,label);
  assert.doesNotMatch(await quiet.locator('.sp-count').innerText(),/not logged/i,'known zeroes are recorded counts');
  await capture(page,'card-spaces',width);
  await active.getByRole('button',{name:'Harbor Studio',exact:true}).click();
  const yours=await page.locator('.sp-side .sp-side-row .sp-text-link').allTextContents();
  assert.deepEqual([...yours].sort(),['Check the presentation','Choose the launch wording','Review the proposed schedule']);
  assert.equal(yours.length,3,'pending approvals count cards once and exclude closed cards');
  assert.deepEqual(errors,[]);
 }finally{await page.close()}
});
function roadmapBoard(){
 const ago=days=>new Date(Date.now()-days*86400000).toISOString();
 return {cards:[
  card('now-four','Harbor Studio','ted_doing','Now four',{sort:4}),
  card('now-two','Harbor Studio','ted_doing','Now two',{sort:2}),
  card('now-one','Harbor Studio','ted_doing','Now one',{sort:1}),
  card('now-three','Harbor Studio','ted_doing','Now three',{sort:3}),
  card('next-low','Harbor Studio','up_next','Next lower value',{priority_value:5,sort:0}),
  card('next-third','Harbor Studio','up_next','Next high third',{priority_value:10,sort:30}),
  card('next-first','Harbor Studio','up_next','Next high first',{priority_value:10,sort:10}),
  card('next-second','Harbor Studio','up_next','Next high second',{priority_value:10,sort:20}),
  card('next-last','Harbor Studio','up_next','Next lowest value',{priority_value:1,sort:0}),
  card('later-one','Harbor Studio','needs_you','Later one',{sort:1}),
  card('later-two','Harbor Studio','yours','Later two',{sort:2}),
  card('later-three','Harbor Studio','needs_you','Later three',{sort:3}),
  card('later-four','Harbor Studio','needs_you','Later four',{sort:4}),
  card('shipped-one','Harbor Studio','done','Shipped one',{updated_at:ago(1),sort:1}),
  card('shipped-two','Harbor Studio','done','Shipped two',{updated_at:ago(3),sort:2}),
  card('shipped-three','Harbor Studio','done','Shipped three',{updated_at:ago(7),sort:3}),
  card('shipped-four','Harbor Studio','done','Shipped four',{updated_at:ago(13),sort:4}),
  card('old-done','Harbor Studio','done','Old completed work',{updated_at:ago(15)}),
  card('killed-recent','Harbor Studio','killed','Discarded recent work',{updated_at:ago(1)}),
  card('quiet-old','Quiet Archive','done','Quiet archived work',{updated_at:ago(15)})
 ],pod_pulse:[],capabilities:{snapshots:false}};
}
test('HTTP cards supply Roadmap lanes, priority order, and the 14 day shipped window',async()=>{
 const {page,errors}=await openLive(390,roadmapBoard());
 try{
  await page.getByRole('tab',{name:/Roadmap/}).click();await page.getByRole('button',{name:'Harbor Studio',exact:true}).click();
  for(const [lane,count,titles]of [
   ['now','4',['Now four','Now one','Now three','Now two']],
   ['next','5',['Next high first','Next high second','Next high third','Next lower value','Next lowest value']],
   ['later','4',['Later four','Later one','Later three','Later two']],
   ['shipped','4',['Shipped four','Shipped one','Shipped three','Shipped two']]
  ]){
   const column=page.locator('.rm-column[data-lane="'+lane+'"]');
   assert.equal(await column.locator('.rm-column-title .rm-count').textContent(),count,lane+' known count');
   const actual=await column.locator('.rm-item h3').allTextContents();assert.deepEqual(lane==='next'?actual:[...actual].sort(),titles,lane+' card membership and order');
  }
  assert.doesNotMatch(await page.locator('.rm-columns').innerText(),/Old completed work|Discarded recent work|not logged/i);
  assert.deepEqual(errors,[]);
 }finally{await page.close()}
});
for(const width of [390,1440])test('HTTP card Roadmap wall shows three titles and remaining counts per cell '+width,async()=>{
 const {page,errors}=await openLive(width,roadmapBoard());
 try{
  await page.getByRole('tab',{name:/Roadmap/}).click();
  const row=page.locator('.rm-wall-row').filter({has:page.getByRole('button',{name:'Harbor Studio',exact:true})}),cells=row.locator('.rm-wall-cell');
  assert.equal(await cells.count(),4);
  for(const [index,count,titles,hidden]of [
   [0,'4',['Now one','Now two','Now three'],['Now four']],
   [1,'5',['Next high first','Next high second','Next high third'],['Next lower value','Next lowest value']],
   [2,'4',['Later one','Later two','Later three'],['Later four']],
   [3,'4',['Shipped one','Shipped two','Shipped three'],['Shipped four']]
  ]){
   const cell=cells.nth(index);assert.equal(await cell.locator('.rm-count').textContent(),count);
   for(const title of titles)assert.equal(await cell.getByText(title,{exact:true}).count(),1,title+' visible');
   for(const title of hidden)assert.equal(await cell.getByText(title,{exact:true}).count(),0,title+' summarized');
   assert.match(await cell.innerText(),new RegExp('\\+'+(Number(count)-3)+'\\b'));
  }
  const quiet=page.locator('.rm-wall-row').filter({has:page.getByRole('button',{name:'Quiet Archive',exact:true})});
  assert.deepEqual(await quiet.locator('.rm-count').allTextContents(),['0','0','0','0']);
  assert.doesNotMatch(await quiet.locator('.rm-wall-cell').allTextContents().then(rows=>rows.join(' ')),/not logged/i);
  await capture(page,'card-roadmap',width);assert.deepEqual(errors,[]);
 }finally{await page.close()}
});
