// Synthetic data only. Every backend request is intercepted before navigation.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {test,before,after}=require('node:test');
const {chromium,fixture}=require('./browser.cjs');
const out=process.env.QA_OUT||'../qa-evidence/decide';fs.mkdirSync(out,{recursive:true});
const now=new Date().toISOString();
const base=(id,title,extra={})=>({id,title,project:'Test project',section:'needs_you',revision:1,body:'Choose the next step.\nLong details stay behind More.',...extra});
const seed=[base('fyi1','Homepage is live',{decision_kind:'status',body:'Deployed and verified. Nothing needed.'}),base('other','Name the next milestone'),base('spend','Approve the test budget',{decision_kind:'spend_money',amount_cents:2500,currency:'USD',ted_call:'Hold the budget until paid orders reconcile.',options:[{label:'Approve',value:'yes'},{label:'No',value:'no'}]}),base('send','Send the reviewed reply',{decision_kind:'send_email',options:[{label:'Send',value:'send'},{label:'No',value:'no'}]}),base('design','Pick the homepage design',{decision_kind:'approve_design',options:[{label:'Use A',value:'a'},{label:'Use B',value:'b'}]}),base('fyi2','The fix was merged',{body:'Merged, applied, and verified. No decision needed.'})];
let browser;
before(async()=>browser=await chromium.launch());after(async()=>browser?.close());
async function open({cards=seed,width=390,mode='',fail=false,approvals=[],reduced=false,onPost=()=>{}}={}){
 const page=await browser.newPage({viewport:{width,height:844},reducedMotion:reduced?'reduce':'no-preference'}),posts=[],errors=[];
 page.on('pageerror',e=>errors.push(e.message));await fixture(page,{list:false});
 let rows=structuredClone(cards);
 await page.route('**/functions/v1/ted-board*',async route=>{
  const req=route.request(),url=new URL(req.url()),body=req.postDataJSON()||{};
  if(req.method()==='POST'){
   posts.push({...body,key:undefined});await onPost(body);if(fail===true||fail===body.card_id)return route.fulfill({status:503,json:{error:'Could not save. Try again.'}});
   if(body.action==='approval')return route.fulfill({json:{ok:true}});
   const card=rows.find(c=>c.id===body.card_id);if(!card)return route.fulfill({json:{ok:true}});
   const saved={...card,section:body.action==='move'?body.value:'ted_doing',answer:{choice:body.action==='choice'?body.value:body.action,note:body.note}};rows=rows.map(c=>c.id===card.id?saved:c);
   return route.fulfill({json:{ok:true,card:saved}});
  }
  if(url.searchParams.get('resource')==='jobs')return route.fulfill({json:{jobs:[],approvals,fresh_ted:{status:'done',completed_at:'2026-01-01T00:00:00Z'}}});
  if(url.searchParams.get('resource')==='control')return route.fulfill({json:{vetoes:[],rules:[],server_time:now}});
  return route.fulfill({json:{cards:rows,snapshots:[],capabilities:{}}});
 });
 await page.goto('http://127.0.0.1:8763/'+(mode?'?view='+mode:'')+'#k=fixture-only');await page.waitForFunction(()=>state.loaded);
 return {page,posts,errors};
}
async function advance(page,ms=5300){await page.clock.runFor(ms);await page.waitForTimeout(30);}
async function shot(page,name){await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});}
async function visibleCard(page,id){await page.locator('.decide-card[data-card-id="'+id+'"]').waitFor();}

test('mobile starts with one real decision, compact face, no chrome, and no overflow',async()=>{
 const {page,errors}=await open();try{
  await visibleCard(page,'spend');assert.equal(await page.locator('.decide-card').count(),1);assert.equal(await page.locator('.decide-counter').textContent(),'5 left');
  assert.equal(await page.locator('.masthead').isVisible(),false);assert.equal(await page.locator('#fresh-status').isVisible(),false);
  assert.equal(await page.locator('.decide-more').getAttribute('open'),null);assert.match(await page.locator('.decide-recommendation').innerText(),/Hold the budget/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390);assert.equal(await page.evaluate(()=>document.body.innerText.includes(String.fromCharCode(8212))),false);
  assert.deepEqual(errors,[]);await shot(page,'after-mobile');
 }finally{await page.close();}
});

test('choice leaves immediately, Undo cancels during 5 seconds, and confirmed choice stays gone across reloads and polls',async()=>{
 const {page,posts}=await open();try{
  await page.clock.install();await visibleCard(page,'spend');await page.getByRole('button',{name:'Approve',exact:true}).click();await advance(page,210);await visibleCard(page,'send');
  assert.equal(posts.length,0,'Undo window precedes the existing API call');await page.getByRole('button',{name:'Undo',exact:true}).click();await visibleCard(page,'spend');await advance(page,5300);assert.equal(posts.length,0);
  await page.getByRole('button',{name:'Approve',exact:true}).click();await advance(page);assert.deepEqual(posts.map(({action,card_id,value,note})=>({action,card_id,value,note})),[{action:'choice',card_id:'spend',value:'yes',note:''}]);
  await page.evaluate(()=>{const old=state.cards.find(c=>c.id==='spend');state.cards=state.cards.map(c=>c.id==='spend'?{...old,section:'needs_you',revision:999,live_status:'reviewing',updated_at:new Date().toISOString()}:c);render();});
  assert.equal(await page.locator('.decide-card[data-card-id="spend"]').count(),0);await page.reload();await page.waitForFunction(()=>state.loaded);assert.equal(await page.locator('.decide-card[data-card-id="spend"]').count(),0);
  await page.evaluate(()=>{state.cards=state.cards.map(c=>c.id==='spend'?{...c,section:'needs_you',body:'New ask: approve the revised budget?'}:c);render();});await visibleCard(page,'spend');
 }finally{await page.close();}
});

test('Later is session-only, reorders behind updates, and makes no API call',async()=>{
 const {page,posts}=await open();try{
  await visibleCard(page,'spend');await page.getByRole('button',{name:'Later',exact:true}).click();await visibleCard(page,'send');assert.equal(posts.length,0);assert.equal(await page.locator('.decide-counter').textContent(),'5 left');
  await page.reload();await visibleCard(page,'spend');
 }finally{await page.close();}
});

test('FYI pile clears in one tap, Undo restores it, and empty state has a bear',async()=>{
 const {page,posts}=await open({cards:seed.filter(c=>c.id.startsWith('fyi'))});try{
  await page.clock.install();assert.equal(await page.locator('.decide-card').count(),1);assert.match(await page.locator('.decide-card h1').innerText(),/Ted’s updates \(2\)/i);assert.equal(await page.locator('.decide-updates li').count(),2);
  await shot(page,'after-updates-mobile');await page.getByRole('button',{name:'Got it',exact:true}).click();await advance(page,210);await page.locator('.decide-empty').waitFor();assert.equal(await page.locator('.decide-empty svg').count(),1);
  await page.getByRole('button',{name:'Undo',exact:true}).click();assert.equal(await page.locator('.decide-updates li').count(),2);await page.getByRole('button',{name:'Got it',exact:true}).click();await advance(page);assert.deepEqual(posts.map(({action,card_id,value,note})=>({action,card_id,value,note})),[{action:'move',card_id:'fyi1',value:'done',note:''},{action:'move',card_id:'fyi2',value:'done',note:''}],'Got it reuses the existing move action');await shot(page,'after-empty-mobile');await page.reload();await page.locator('.decide-empty').waitFor();
 }finally{await page.close();}
});

test('No, Send, design picks, Tell Ted, fallback No, and pending approvals reuse existing payloads',async()=>{
 const scenarios=[
  {card:seed[2],label:'No',expected:{action:'choice',card_id:'spend',value:'no',note:''}},
  {card:seed[3],label:'Send',expected:{action:'choice',card_id:'send',value:'send',note:''}},
  {card:seed[4],label:'Use B',expected:{action:'choice',card_id:'design',value:'b',note:''}},
  {card:seed[1],label:'No',expected:{action:'move',card_id:'other',value:'killed',note:''}},
  {card:seed[1],note:'Use the paid order milestone.',expected:{action:'note',card_id:'other',value:'',note:'Use the paid order milestone.'}},
  {card:base('approval','Approve the reviewed draft'),approvals:[{id:'ap1',card_id:'approval',status:'pending',summary:'Send the reviewed draft',content:'Exact synthetic draft'}],label:'Approve',expected:{action:'approval',approval_id:'ap1',decision:'approve'}},
  {card:base('approval','Approve the reviewed draft'),approvals:[{id:'ap1',card_id:'approval',status:'pending',summary:'Send the reviewed draft',content:'Exact synthetic draft'}],label:'No',expected:{action:'approval',approval_id:'ap1',decision:'reject'}}
 ];
 for(const scenario of scenarios){const {page,posts}=await open({cards:[scenario.card],approvals:scenario.approvals});try{
  await page.clock.install();await visibleCard(page,scenario.card.id);if(scenario.note){await page.getByRole('button',{name:'Tell Ted',exact:true}).click();await page.getByRole('textbox',{name:'Tell Ted'}).fill(scenario.note);await page.getByRole('button',{name:'Send note',exact:true}).click();}else await page.getByRole('button',{name:scenario.label,exact:true}).click();
  await advance(page);assert.deepEqual(posts.map(p=>{const {key,...payload}=p;return payload}),[scenario.expected]);await page.locator('.decide-empty').waitFor();
 }finally{await page.close();}}
});

test('failed saves restore the card and expose a retryable error',async()=>{
 const {page,posts}=await open({cards:[seed[2]],fail:true});try{
  await page.clock.install();await visibleCard(page,'spend');await page.getByRole('button',{name:'Approve',exact:true}).click();await advance(page);await visibleCard(page,'spend');assert.match(await page.locator('#notice').innerText(),/Could not save/);assert.equal(posts.length,1);
 }finally{await page.close();}
});

test('List is one tap away, desktop stays list, stale Fresh Ted is removed, and reduced motion is respected',async()=>{
 const {page}=await open();try{
  await page.getByRole('button',{name:'List',exact:true}).click();await page.locator('.v3-paper').waitFor();assert.equal(await page.locator('.masthead').isVisible(),true);assert.equal(await page.locator('#fresh-status').innerText(),'');await page.getByRole('button',{name:'Decide',exact:true}).click();await visibleCard(page,'spend');
  await page.evaluate(()=>{freshState={status:'done',completed_at:new Date().toISOString()};renderFresh();});assert.match(await page.locator('#fresh-status').innerText(),/Fresh Ted is up/);
 }finally{await page.close();}
 const desktop=await open({width:1440});try{await desktop.page.locator('.v3-paper').waitFor();await desktop.page.getByRole('button',{name:'Decide',exact:true}).click();await visibleCard(desktop.page,'spend');assert.equal(await desktop.page.evaluate(()=>document.documentElement.scrollWidth),1440);await shot(desktop.page,'after-desktop');}finally{await desktop.page.close();}
 const reduced=await open({cards:[seed[2]],reduced:true});try{await visibleCard(reduced.page,'spend');await reduced.page.getByRole('button',{name:'Approve',exact:true}).click();await reduced.page.locator('.decide-empty').waitFor();assert.equal(await reduced.page.evaluate(()=>document.documentElement.scrollWidth),390);}finally{await reduced.page.close();}
});

if(process.env.CAPTURE_BEFORE)test('capture baseline',async()=>{for(const width of [390,1440]){const {page}=await open({width,mode:'list'});try{await page.locator('.v3-paper').waitFor();await shot(page,'before-'+(width===390?'mobile':'desktop'));}finally{await page.close();}}});

test('Undo remains available in List, and cancels every queued decision',async()=>{
 const {page,posts}=await open();try{
  await page.clock.install();await visibleCard(page,'spend');await page.getByRole('button',{name:'Approve',exact:true}).click();await advance(page,210);await page.getByRole('button',{name:'Send',exact:true}).click();await advance(page,210);
  await page.getByRole('button',{name:'List',exact:true}).click();await page.getByRole('button',{name:'Undo all',exact:true}).click();await advance(page);assert.equal(posts.length,0);await page.getByRole('button',{name:'Decide',exact:true}).click();await visibleCard(page,'spend');
 }finally{await page.close();}
});

test('new asks during the grace period and account resets cancel unsent actions',async()=>{
 const {page,posts}=await open({cards:[seed[2]]});try{
  await page.clock.install();await visibleCard(page,'spend');await page.getByRole('button',{name:'Approve',exact:true}).click();await advance(page,210);
  await page.evaluate(()=>{state.cards=state.cards.map(c=>({...c,body:'New ask: approve the larger budget?'}));render();});await advance(page);assert.equal(posts.length,0);await visibleCard(page,'spend');assert.match(await page.locator('#notice').innerText(),/card changed/);
  await page.getByRole('button',{name:'Approve',exact:true}).click();await advance(page,210);await page.evaluate(()=>{key='second-fixture-account';resetForKeyChange();});await advance(page);assert.equal(posts.length,0);
 }finally{await page.close();}
});

test('legacy shortcuts cannot answer a hidden list card while Decide is open',async()=>{
 const {page,posts}=await open();try{
  await page.clock.install();await visibleCard(page,'spend');for(const key of ['1','2','h','j','k'])await page.keyboard.press(key);await advance(page);assert.equal(posts.length,0);await visibleCard(page,'spend');
 }finally{await page.close();}
});

test('FYI detection keeps sends, spend, questions, and design choices in the decision stack',async()=>{
 const cards=[base('notice','Design is live',{decision_kind:'approve_design',options:[{label:'Choose A',value:'a'}]}),base('question','Build is live',{body:'Can you review the next launch?'}),base('money-update','Budget applied',{decision_kind:'spend_money'}),base('status-choice','Status update',{decision_kind:'status',options:[{label:'Approve',value:'yes'}]}),seed[0]];
 const {page}=await open({cards});try{
  const facts=await page.evaluate(()=>state.cards.map(c=>({id:c.id,update:decide.isUpdate(c)})));assert.deepEqual(facts.map(c=>c.update),[false,false,false,false,true]);assert.equal(await page.locator('.decide-counter').textContent(),'5 left');
 }finally{await page.close();}
});

test('759px defaults to Decide, 760px defaults to List, and long content has no horizontal overflow',async()=>{
 for(const width of [320,390,759,760]){const {page}=await open({width,cards:[base('long','A very long title for the revised homepage and next launch decision',{project:'Test project with a very long project name',body:'A long question about '+('details '.repeat(90)),options:[{label:'Approve this exact revised proposal',value:'yes'}]})]});try{
  if(width<760){await visibleCard(page,'long');assert.equal(await page.locator('.decide-card').count(),1);}else await page.locator('.v3-paper').waitFor();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);
 }finally{await page.close();}}
});


test('partial updates failure keeps only unsaved updates, with a visible retry error',async()=>{
 const {page,posts}=await open({cards:seed.filter(c=>c.id.startsWith('fyi')),fail:'fyi1'});try{
  await page.clock.install();await page.getByRole('button',{name:'Got it',exact:true}).click();await advance(page);assert.equal(posts.length,2);assert.equal(await page.locator('.decide-updates li').count(),1);assert.match(await page.locator('#notice').innerText(),/could not|not saved/i);
 }finally{await page.close();}
});

test('completed cards with old approval options appear only in the updates pile',async()=>{
 const {page,posts}=await open({cards:[{...seed[2],section:'done',updated_at:now,answer:{choice:'yes'}}]});try{
  await page.clock.install();assert.equal(await page.locator('.decide-updates li').count(),1);assert.equal(await page.getByRole('button',{name:'Approve',exact:true}).count(),0);await page.getByRole('button',{name:'Got it',exact:true}).click();await advance(page);await page.locator('.decide-empty').waitFor();assert.equal(posts.length,0,'already-done updates need no second backend decision');
 }finally{await page.close();}
});

test('a newer List choice replaces the queued Decide action',async()=>{
 const {page,posts}=await open({cards:[seed[2]]});try{
  await page.clock.install();await visibleCard(page,'spend');await page.getByRole('button',{name:'Approve',exact:true}).click();await advance(page,210);await page.getByRole('button',{name:'List',exact:true}).click();await page.locator('[data-ticket="spend"]').getByRole('button',{name:'No',exact:true}).click();await page.waitForFunction(()=>state.busy.size===0);await advance(page);
  assert.deepEqual(posts.map(({action,value})=>({action,value})),[{action:'choice',value:'no'}],'the earlier queued approval must not overwrite the newer No');
 }finally{await page.close();}
});

test('an approval arriving during submission stays visible until reviewed',async()=>{
 const approvals=[{id:'ap1',card_id:'approval',status:'pending',summary:'Reviewed draft',content:'Original synthetic draft'}];
 const {page,posts}=await open({cards:[base('approval','Approve the reviewed draft')],approvals,onPost:body=>{if(body.action==='approval')approvals.push({id:'ap2',card_id:'approval',status:'pending',summary:'A new draft',content:'Unreviewed synthetic draft'});}});try{
  await page.clock.install();await visibleCard(page,'approval');await page.getByRole('button',{name:'Approve',exact:true}).click();await advance(page);
  assert.equal(posts.length,1);assert.equal(await page.locator('.decide-card[data-card-id="approval"]').count(),1,'the new approval must not be marked reviewed by the earlier submission');
 }finally{await page.close();}
});

test('confirmed decisions stay dismissed for the session when persistent storage is full',async()=>{
 const {page}=await open({cards:[seed[2]]});try{
  await page.clock.install();await page.evaluate(()=>{const set=storage.set;storage.set=(name,value)=>name.startsWith('ted-board-decided:')?false:set(name,value);});await page.getByRole('button',{name:'Approve',exact:true}).click();await advance(page);await page.evaluate(()=>{state.cards=state.cards.map(c=>({...c,section:'needs_you',revision:99,live_status:'Still working'}));render();});
  assert.equal(await page.locator('.decide-card[data-card-id="spend"]').count(),0,'storage failure must not put an answered card back in the stack');
 }finally{await page.close();}
});

test('status metadata cannot hide an explicit new question in the updates pile',async()=>{
 const {page}=await open({cards:[base('status-ask','Deployment update',{decision_kind:'status',body:'The deployment is live. Can you approve the next launch?'})]});try{
  assert.equal(await page.locator('.decide-updates').count(),0);assert.equal(await page.getByRole('button',{name:'Tell Ted',exact:true}).count(),1);
 }finally{await page.close();}
});

test('a decision received by polling cancels a conflicting queued action',async()=>{
 const {page,posts}=await open({cards:[seed[2]]});try{
  await page.clock.install();await page.getByRole('button',{name:'Approve',exact:true}).click();await advance(page,210);await page.evaluate(()=>{state.cards=state.cards.map(c=>({...c,section:'ted_doing',answer:{choice:'no'}}));render();});await advance(page);assert.equal(posts.length,0,'a stale queued approval must not overwrite a recorded decision from another view or device');
 }finally{await page.close();}
});

test('a newer approval rejection cancels the queued approval submission',async()=>{
 const {page,posts}=await open({cards:[base('approval','Approve the reviewed draft')],approvals:[{id:'ap1',card_id:'approval',status:'pending',summary:'Reviewed draft',content:'Synthetic draft'}]});try{
  await page.clock.install();await visibleCard(page,'approval');await page.getByRole('button',{name:'Approve',exact:true}).click();await advance(page,210);await page.getByRole('button',{name:'List',exact:true}).click();await page.evaluate(()=>control('approval',{approval_id:'ap1',decision:'reject'}));await advance(page);
  assert.deepEqual(posts.map(({action,decision})=>({action,decision})),[{action:'approval',decision:'reject'}]);
 }finally{await page.close();}
});
