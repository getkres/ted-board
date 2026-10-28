// Synthetic inbox tests. All backend traffic is intercepted, including failures.
const assert=require('node:assert/strict');
const {test,before,after}=require('node:test');
const {chromium,fixture}=require('./browser.cjs');
let browser;
before(async()=>browser=await chromium.launch());
after(async()=>browser?.close());
const seed=[['b1','Beta','b'],['a1','Alpha','a'],['c1','Gamma','c'],['a2','Alpha','a'],['b2','Beta','b'],['a3','Alpha','a']].map(([id,project,line])=>({id,project,line,title:'Choose '+id,section:'needs_you',kind:'routine',options:[{label:'Yes',value:'yes'},{label:'Not yet',value:'wait'}]}));
async function open({width=1440,storage='',mode='list',cards=seed}={}){
 const page=await browser.newPage({viewport:{width,height:960}}),writes=[],errors=[];
 page.on('pageerror',e=>errors.push(e.message));await fixture(page,{list:false});
 if(storage)await page.addInitScript(storage);
 let rows=structuredClone(cards);
 await page.route('**/functions/v1/ted-board*',route=>{
  const req=route.request(),url=new URL(req.url());
  if(req.method()!=='GET'){
   const {key,...body}=req.postDataJSON();writes.push(body);
   const card=rows.find(c=>c.id===body.card_id);
   if(!card)return route.fulfill({json:{ok:true}});
   const saved={...card,section:body.action==='move'?body.value:'ted_doing',answer:{choice:body.value}};
   rows=rows.map(c=>c.id===saved.id?saved:c);return route.fulfill({json:{ok:true,card:saved}});
  }
  if(url.searchParams.get('resource')==='jobs')return route.fulfill({json:{jobs:[],approvals:[],fresh_ted:{status:'done',due:false}}});
  if(url.searchParams.get('resource')==='control')return route.fulfill({json:{vetoes:[],rules:[]}});
  return route.fulfill({json:{cards:rows,lines:[{id:'a',name:'Alpha'},{id:'b',name:'Beta'},{id:'c',name:'Gamma'},{id:'empty',name:'Empty'}],snapshots:[],capabilities:{}}});
 });
 await page.goto('http://127.0.0.1:8763/?view='+mode+'#k=fixture-only&tab=inbox');
 await page.waitForFunction(()=>state.loaded&&state.jobsLoaded);
 return {page,writes,errors};
}
const ids=page=>page.locator('[data-ticket]').evaluateAll(nodes=>nodes.map(n=>n.dataset.ticket));
const focused=page=>page.evaluate(()=>document.activeElement.closest('[data-ticket]')?.dataset.ticket);

for(const width of [375,1399,1400,1440,2560])test('project counts, ordering, and layout at '+width+'px',async()=>{
 const {page,writes,errors}=await open({width});try{
  const groups=page.locator('.v3-project-group');assert.equal(await groups.count(),3);
  assert.deepEqual(await groups.locator('.v3-project-name').allTextContents(),['Alpha','Beta','Gamma']);
  assert.deepEqual(await groups.locator('.v3-project-count').allTextContents(),['3','2','1']);
  assert.deepEqual(await ids(page),['a1','a2','a3','b1','b2','c1']);
  const positions=await groups.evaluateAll(nodes=>nodes.map(n=>Math.round(n.getBoundingClientRect().left)));
  assert.equal(new Set(positions).size,width>=1400?3:1);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);
  if(width>=1400)assert.ok(await page.locator('.shell').evaluate(n=>n.getBoundingClientRect().width)>width-2);
  assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
 }finally{await page.close();}
});

test('Skip button and S rotate only the local queue, including across projects',async()=>{
 const {page,writes,errors}=await open();try{
  assert.equal(await page.locator('[data-ticket="a1"]').getByRole('button',{name:'Skip',exact:true}).count(),1);
  await page.clock.install();const original=await page.evaluate(()=>JSON.stringify(state.cards));
  await page.locator('[data-ticket="a1"]').getByRole('button',{name:'Skip',exact:true}).click();
  await page.waitForFunction(()=>document.activeElement.dataset.ticket==='a2');
  assert.deepEqual(await ids(page),['a2','a3','a1','b1','b2','c1']);
  assert.equal(await page.locator('[data-ticket="a1"] .v3-skipped').textContent(),'skipped');
  await page.locator('[data-ticket="a3"]').focus();await page.keyboard.press('s');
  await page.waitForFunction(()=>document.activeElement.dataset.ticket==='b1');
  assert.deepEqual(await page.evaluate(()=>v3.inboxQueue().map(c=>c.id)),['a2','b1','b2','c1','a1','a3']);
  await page.locator('[data-ticket="a1"]').focus();await page.keyboard.press('S');
  await page.waitForFunction(()=>document.activeElement.dataset.ticket==='a3');
  assert.equal(await page.evaluate(()=>v3.inboxQueue().at(-1).id),'a1');
  await page.clock.runFor(6500);
  assert.equal(await page.evaluate(()=>JSON.stringify(state.cards)),original);
  assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
  await page.reload();await page.waitForSelector('[data-ticket="a1"]');
  assert.equal(await page.locator('.v3-skipped').count(),0);
  assert.equal(await page.evaluate(()=>v3.inboxQueue().at(-1).id),'a1');
  await page.evaluate(()=>{location.hash='k=second-fixture&tab=inbox';});
  await page.waitForFunction(()=>key==='second-fixture'&&state.loaded&&state.jobsLoaded);
  assert.deepEqual(await ids(page),['a1','a2','a3','b1','b2','c1']);
 }finally{await page.close();}
});

test('Skip survives denied storage and a single-card queue',async()=>{
 const {page,writes,errors}=await open({cards:[seed[1]],storage:`Storage.prototype.getItem=Storage.prototype.setItem=function(){throw new Error('Storage disabled');}`});try{
  await page.locator('[data-ticket="a1"]').getByRole('button',{name:'Skip',exact:true}).click();
  await page.waitForFunction(()=>document.activeElement.dataset.ticket==='a1');
  assert.equal(await page.locator('.v3-skipped').count(),1);assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
 }finally{await page.close();}
});

test('Skip ignores editable fields, modifiers, and other tabs; Not yet and H keep their actions',async()=>{
 const {page,writes}=await open();try{
  await page.locator('[data-open-card="a1"]').click();
  const input=page.locator('.v3-detail textarea').first();await input.fill('s');await input.press('s');
  assert.equal(await page.locator('.v3-skipped').count(),0);
  await page.locator('[data-ticket="a1"]').focus();await page.keyboard.press('Alt+s');
  assert.equal(await page.locator('.v3-skipped').count(),0);
  await page.keyboard.press('2');assert.equal(writes.at(-1).action,'choice');assert.equal(writes.at(-1).value,'wait');
  await page.locator('[data-ticket="a2"]').focus();await page.keyboard.press('h');
  assert.deepEqual(writes.at(-1),{card_id:'a2',action:'move',value:'up_next',note:''});
  const order=await page.evaluate(()=>JSON.stringify(v3.skipOrder));
  await page.getByRole('tab',{name:/Spaces/}).click();await page.locator('body').press('s');
  assert.equal(await page.evaluate(()=>JSON.stringify(v3.skipOrder)),order);
 }finally{await page.close();}
});

test('phone Decide has a separate Skip, session badge, project count, and no queued answer',async()=>{
 const {page,writes,errors}=await open({width:375,mode:'decide'});try{
  await page.clock.install();
  assert.match(await page.locator('.decide-project').innerText(),/Alpha.*3/);
  await page.locator('.decide-card').getByRole('button',{name:'Skip',exact:true}).click();
  await page.waitForSelector('.decide-card[data-card-id="a2"]');
  await page.keyboard.press('s');await page.waitForSelector('.decide-card[data-card-id="a3"]');
  await page.clock.runFor(6500);assert.deepEqual(writes,[]);
  assert.equal(await page.evaluate(()=>decide.pending.size),0);assert.deepEqual(errors,[]);
 }finally{await page.close();}
});
