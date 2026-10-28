const assert=require('node:assert/strict');
const {test,before,after}=require('node:test');
const {chromium,fixture}=require('./browser.cjs');

let browser;
before(async()=>{browser=await chromium.launch();});
after(async()=>{await browser?.close();});

const cases=[
 {name:'missing kind, dismissed confirmation',fields:{},accept:false,posts:0,prompts:1},
 {name:'missing kind, accepted confirmation',fields:{},accept:true,posts:1,prompts:1},
 {name:'explicit safe decision_kind',fields:{decision_kind:'routine'},accept:false,posts:1,prompts:0},
 {name:'explicit safe kind',fields:{kind:'routine'},accept:false,posts:1,prompts:0},
 {name:'safe decision_kind with reserved kind',fields:{decision_kind:'routine',kind:'money_out'},accept:false,posts:0,prompts:1}
];

for(const shortcut of ['swipe right','key 1'])for(const scenario of cases){
 test(shortcut+': '+scenario.name,async()=>{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  try{
   const posts=await fixture(page),dialogs=[];
   page.on('dialog',async dialog=>{
    dialogs.push({type:dialog.type(),message:dialog.message()});
    if(scenario.accept)await dialog.accept();else await dialog.dismiss();
   });
   await page.goto('http://127.0.0.1:8763/#k=fixture-only&tab=inbox');
   await page.waitForSelector('[data-ticket="money"]');
   await page.evaluate(fields=>{
    const card={...state.cards.find(c=>c.id==='money')};
    delete card.decision_kind;delete card.kind;Object.assign(card,fields);
    state.cards=[card];v3.item=null;v3.focusIndex=0;v3.split='yours';render();
   },scenario.fields);
   const ticket=page.locator('[data-ticket="money"]');
   if(shortcut==='swipe right'){
    await ticket.dispatchEvent('pointerdown',{pointerType:'touch',clientX:20,clientY:40});
    await ticket.dispatchEvent('pointerup',{pointerType:'touch',clientX:260,clientY:45});
   }else{
    await ticket.focus();await page.keyboard.press('1');
   }
   await page.waitForFunction(()=>state.busy.size===0);
   assert.equal(posts.length,scenario.posts,shortcut+' must honor the confirmation result before POST');
   assert.equal(dialogs.length,scenario.prompts,shortcut+' confirmation count');
   if(scenario.prompts)assert.equal(dialogs[0].type,'confirm');
   if(scenario.posts)assert.deepEqual(posts.map(({action,card_id,value})=>({action,card_id,value})),[{action:'choice',card_id:'money',value:'yes'}]);
  }finally{await page.close();}
 });
}
