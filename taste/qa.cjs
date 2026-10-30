/* Synthetic browser contract checks. Requires a local static server and Google Chrome. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const base=process.env.TASTE_QA_URL||'http://127.0.0.1:8767/taste/';
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let count=0,failSave=false,sequence=1,posted=[],failNext=false;
  const stats=()=>({total:count,decisive:count,repeat_checks:0,repeat_agreements:0});
  const creative=id=>({id,business:'Fixture',audience:'Readers',format:'Saved ad headline',brief:'Make the offer clear.',source_label:'Synthetic fixture',text:id==='left'?'Read something unexpected.':'Find your next favorite.'});
  await page.route('**/taste/api/**',async route=>{
   if(route.request().url().endsWith('/pick')){
    const payload=route.request().postDataJSON();posted.push(payload);
    if(failSave)return route.fulfill({status:503,json:{error:'Could not save locally. Keep this pair open, and retry.'}});
    count++;sequence++;return route.fulfill({json:{id:payload.id,seq:count,stats:stats()}});
   }
   if(failNext)return route.fulfill({status:503,json:{error:'The local service is unavailable.'}});
   return route.fulfill({json:{id:'offer-'+sequence,seq:sequence,a:creative('left'),b:creative('right'),stats:stats()}});
  });
  await page.goto(base);await page.waitForFunction(()=>!document.querySelector('#pick-a').disabled);
  for(const width of [320,390,768,1440]){
   await page.setViewportSize({width,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);
  }
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'Open creative A full size'}).click();
  await page.getByRole('dialog').waitFor();await page.keyboard.press('Escape');
  assert.equal(await page.getByRole('dialog').count(),0);
  await page.getByLabel('Why?').fill('a clearer message');failSave=true;
  await page.getByRole('button',{name:'Pick A',exact:true}).click();
  await page.getByRole('button',{name:'Retry save'}).waitFor();
  assert.equal(await page.getByLabel('Why?').inputValue(),'a clearer message');
  failSave=false;await page.getByRole('button',{name:'Retry save'}).click();
  await page.waitForFunction(()=>document.querySelector('#pair-number').textContent.startsWith('Pair 2 /'));
  assert.deepEqual(posted[0],posted[1]);assert.equal(await page.getByLabel('Why?').inputValue(),'');
  // Another device may save a pair while this page is recovering.
  await page.getByLabel('Why?').fill('belongs to pair two');failSave=true;
  await page.getByRole('button',{name:'Pick B',exact:true}).click();
  await page.getByRole('button',{name:'Retry save'}).waitFor();
  count++;sequence++;failSave=false;
  await page.getByRole('button',{name:'Load current pair'}).click();
  await page.waitForFunction(()=>document.querySelector('#pair-number').textContent.startsWith('Pair 3 /'));
  assert.equal(await page.getByLabel('Why?').inputValue(),'');
  while(count<25){
   await page.waitForFunction(()=>!document.querySelector('#skip').disabled);
   const expected=count+1;await page.getByRole('button',{name:'Skip this pair'}).click();
   await page.waitForFunction(n=>document.querySelector('#saved-count').textContent===n+' saved',expected);
  }
  await page.getByRole('heading',{name:'A good place to pause.'}).waitFor();
  await page.getByRole('button',{name:'Keep going'}).click();
  await page.waitForFunction(()=>!document.querySelector('#pick-a').disabled);
  assert.match(await page.locator('#pair-number').textContent(),/^Pair 26 \/ 1 of 25/);
  failNext=true;await page.reload();await page.getByRole('button',{name:'Load current pair'}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Pick A',exact:true}).isDisabled(),true);
  assert.deepEqual(errors,[]);
  console.log('Taste Chrome checks passed: widths, focus, retry, stale recovery, pause, and service failure.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
