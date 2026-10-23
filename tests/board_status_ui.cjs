const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),http=require('node:http'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const root=path.resolve(__dirname,'..');
 const server=http.createServer((req,res)=>{const file=path.join(root,new URL(req.url,'http://localhost').pathname==='/'?'index.html':new URL(req.url,'http://localhost').pathname);if(!fs.existsSync(file)){res.writeHead(404);res.end();return}res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.svg')?'image/svg+xml':'text/html');res.end(fs.readFileSync(file))}).listen(0,'127.0.0.1');await new Promise(r=>server.once('listening',r));
 const browser=await chromium.launch({headless:true});
 try{
  for(const width of [390,1440]){
   const context=await browser.newContext({viewport:{width,height:844},reducedMotion:'reduce'});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
   const now=Date.now(),fresh=new Date(now-30000).toISOString();
   const cards=[['running','up_next'],['queued','done'],['stale','ted_doing'],['idle','up_next']].map(([id,section])=>({id,title:id,project:'Test',section,body:'',options:[],steps:[],updated_at:new Date(now).toISOString(),live_state:section==='ted_doing'?'blocked':null}));
   const jobs=[{id:'j-running',card_id:'running',title:'Running job',engine:'codex',status:'running',pid:123,heartbeat_at:fresh},{id:'j-queued',card_id:'queued',title:'Queued job',engine:'claude',status:'queued',pid:null,heartbeat_at:fresh},{id:'untracked-1',title:'Untracked job',engine:'claude',status:'untracked',pid:456,heartbeat_at:fresh}];
   await context.route('**/functions/v1/ted-mockups*',r=>r.fulfill({json:{mockups:[],pins:[]}}));
   await context.route('**/functions/v1/ted-board*',r=>r.fulfill({json:new URL(r.request().url()).searchParams.get('resource')==='jobs'?{jobs,approvals:[]}:{cards,pod_pulse:[]}}));
   await page.goto('http://127.0.0.1:'+server.address().port+'/#k=fixture-only&tab=Jobs');await page.waitForFunction(()=>state.jobsLoaded);await page.locator('.job-list article').first().waitFor();
   assert.deepEqual(await page.locator('.jobs-work-summary').allTextContents(),['1 running · 1 queued · 1 stale in Ted doing']);
   jobs[0].heartbeat_at=new Date(now-180000).toISOString();jobs[1].heartbeat_at=jobs[0].heartbeat_at;
   await page.evaluate(()=>loadJobs());
   assert.deepEqual(await page.locator('.jobs-work-summary').allTextContents(),['0 running · 0 queued · 1 stale in Ted doing']);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.deepEqual(errors,[]);await context.close();
  }
  console.log('PASS current Jobs counts, manual card moves, polling, stale heartbeats, untracked exclusion, and mobile and desktop layout');
 }finally{await browser.close();await new Promise(r=>server.close(r))}
})().catch(e=>{console.error(e);process.exitCode=1});
