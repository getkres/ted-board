'use strict';
(() => {
 const $ = id => document.getElementById(id);
 const compare=$('compare'), notice=$('notice'), viewer=$('viewer');
 let offer=null, busy=false, retryPayload=null, mediaReady=false, generation=0;
 let sessionStart=null;
 try { const raw=sessionStorage.getItem('taste-session-start'); if(raw!==null) sessionStart=Number(raw); } catch {}
 function setStart(value){sessionStart=value;try{sessionStorage.setItem('taste-session-start',String(value));}catch{}}
 function message(text,error=false){notice.textContent=text;notice.classList.toggle('error',error);}
 function controls(){
  $('pick-a').disabled=busy||!offer||!mediaReady;
  $('pick-b').disabled=busy||!offer||!mediaReady;
  $('skip').disabled=busy||!offer;
  $('why').disabled=busy;
  $('retry').disabled=busy;
  $('refresh').disabled=busy;
  compare.setAttribute('aria-busy',String(busy));
 }
 async function request(path,payload){
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),15000);
  try{
   const response=await fetch('api/'+path,{cache:'no-store',signal:controller.signal,
    ...(payload?{method:'POST',headers:{'Content-Type':'application/json','X-Taste-Request':'1'},body:JSON.stringify(payload)}:{})});
   let body;try{body=await response.json();}catch{throw new Error('The local service did not return a choice. Retry when the Mac is reachable.');}
   if(!response.ok){const error=new Error(body.error||'The local service is unavailable.');error.status=response.status;throw error;}
   return body;
  }finally{clearTimeout(timer);}
 }
 function stats(s){
  $('saved-count').textContent=s.total+' saved';
  if(s.repeat_checks){$('agreement').textContent='Self-agreement: '+s.repeat_agreements+' of '+s.repeat_checks+' repeat checks. Choices stay on this Mac.';}
  else $('agreement').textContent='Your choices stay on this Mac.';
 }
 function content(item){
  if(item.text){const text=document.createElement('p');text.className='headline';text.textContent=item.text;return text;}
  const image=document.createElement('img');image.src=item.media;image.alt=item.business+' creative: '+item.brief;image.decoding='async';return image;
 }
 function renderCreative(side,item){
  const button=$('creative-'+side);button.replaceChildren(content(item));button.disabled=false;
  $('source-'+side).textContent=item.source_label;
  const image=button.querySelector('img');
  if(!image)return Promise.resolve(true);
  return new Promise(resolve=>{
   if(image.complete)return resolve(image.naturalWidth>0);
   image.onload=()=>resolve(true);image.onerror=()=>resolve(false);
  });
 }
 async function load(){
  const priorId=offer?.id;const thisGeneration=++generation;busy=true;offer=null;mediaReady=false;retryPayload=null;
  $('recovery').hidden=true;$('retry').hidden=true;message('Finding your next pair.');controls();
  try{
   const next=await request('next');
   if(thisGeneration!==generation)return;
   if(priorId&&priorId!==next.id)$('why').value='';
   offer=next;if(sessionStart===null||sessionStart>next.stats.total)setStart(next.stats.total);
   stats(next.stats);
   $('business').textContent=next.a.business;$('format').textContent=next.a.format;
   $('audience').textContent='For '+next.a.audience.charAt(0).toLowerCase()+next.a.audience.slice(1);
   $('brief').textContent=next.a.brief;
   $('pair-number').textContent='Pair '+next.seq+' / '+(next.stats.total-sessionStart+1)+' of 25 this visit';
   message('Loading both creatives.');
   const results=await Promise.all([renderCreative('a',next.a),renderCreative('b',next.b)]);
   if(thisGeneration!==generation)return;
   mediaReady=results.every(Boolean);
   if(!mediaReady){message('A creative did not load. Load this pair again, or skip it.',true);$('recovery').hidden=false;}
   else message('Same business, format, and audience.');
  }catch(error){
   if(thisGeneration!==generation)return;
   message(error.name==='AbortError'?'The Mac is taking too long. Load the pair again.':error.message,true);
   $('recovery').hidden=false;
  }finally{if(thisGeneration===generation){busy=false;controls();}}
 }
 async function save(payload){
  if(busy)return;
  busy=true;retryPayload=payload;$('recovery').hidden=true;message('Saving your choice.');controls();
  try{
   const receipt=await request('pick',payload);
   stats(receipt.stats);$('why').value='';retryPayload=null;busy=false;
   if(receipt.stats.total-sessionStart>=25){
    compare.hidden=true;$('pause').hidden=false;
    $('pause-copy').textContent=(receipt.stats.total-sessionStart)+' choices saved this visit. '+receipt.stats.total+' saved in total.';
    $('pause-title').focus();controls();
   }else await load();
  }catch(error){
   message(error.name==='AbortError'?'The save receipt timed out. Retry save safely to check it.':error.message,true);
   $('recovery').hidden=false;$('retry').hidden=error.status===409;
   // Keep the exact payload for a retry. It is safe even if the first receipt was lost.
   if(error.status===409)retryPayload=null;
   busy=false;controls();
  }
 }
 $('choice-form').addEventListener('submit',event=>{
  event.preventDefault();const choice=event.submitter?.value;
  if(!offer||busy||!['a','b','skip'].includes(choice)||(!mediaReady&&choice!=='skip'))return;
  save({id:offer.id,choice,why:$('why').value.trim()});
 });
 $('retry').addEventListener('click',()=>{if(retryPayload)save(retryPayload);});
 $('refresh').addEventListener('click',load);
 $('continue').addEventListener('click',async()=>{
  setStart(null);sessionStart=null;
  $('pause').hidden=true;compare.hidden=false;await load();$('title').setAttribute('tabindex','-1');$('title').focus();
 });
 function inspect(side){
  if(!offer||busy)return;
  $('viewer-title').textContent='Creative '+side.toUpperCase();
  $('viewer-content').replaceChildren(content(offer[side]));
  viewer.showModal();
 }
 $('creative-a').addEventListener('click',()=>inspect('a'));
 $('creative-b').addEventListener('click',()=>inspect('b'));
 $('close-viewer').addEventListener('click',()=>viewer.close());
 viewer.addEventListener('click',event=>{if(event.target===viewer){const r=viewer.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)viewer.close();}});
 load();
})();
