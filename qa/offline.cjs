// The suite may use fixture routes, but an unmatched request must never leave localhost.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const launch=chromium.launch.bind(chromium);let blocked=false;
async function guard(context){await context.route('**/*',route=>{
 const url=new URL(route.request().url());
 if(['127.0.0.1','localhost','[::1]'].includes(url.hostname))return route.continue();
 blocked=true;return route.abort('blockedbyclient');
});}
chromium.launch=async(...args)=>{
 const browser=await launch(...args),newContext=browser.newContext.bind(browser),newPage=browser.newPage.bind(browser);
 browser.newContext=async(...args)=>{const context=await newContext(...args);await guard(context);return context;};
 browser.newPage=async(...args)=>{const page=await newPage(...args);await guard(page.context());return page;};
 return browser;
};
process.on('exit',()=>{if(blocked){process.stderr.write('Offline QA blocked an unmatched external request.\n');process.exitCode=1;}});
