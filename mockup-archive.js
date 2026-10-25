'use strict';
// Archive has its own queue so it never reuses verdict or approval actions.
class MockupArchive {
 constructor(view){
  this.view=view;this.generation=0;this.pending=new Map();this.restoring=new Set();
  window.addEventListener('pagehide',()=>this.flush());
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')this.flush();});
 }
 matches(m,scope){return m.project===scope.project&&(scope.mockup_id?m.id===scope.mockup_id:m.batch===scope.batch);}
 hidden(m){return [...this.pending.values()].some(entry=>entry.ids.has(m.id));}
 scopeKey(scope){return JSON.stringify(scope);}
 reset(){this.generation++;for(const entry of this.pending.values())clearTimeout(entry.timer);this.pending.clear();this.restoring.clear();clearTimeout(this.tick);this.toast?.remove();this.toast=null;}
 control(scope,label,archived=false){
  const v=this.view,b=v.button(label,'mockup-archive-button',()=>archived?this.restore(scope):this.queue(scope));
  const images=v.mockups.filter(m=>this.matches(m,scope));
  b.disabled=!v.capabilities.archive||images.some(m=>v.busy.has(m.id)||this.hidden(m))||v.batchBusy.has(v.batchKey(scope.project,scope.batch||images[0]?.batch))||this.restoring.has(this.scopeKey(scope));
  if(!v.capabilities.archive)b.title='Archive and restore are waiting for the reviewed backend update.';
  return b;
 }
 queue(scope){
  const v=this.view,key=this.scopeKey(scope),rows=v.mockups.filter(m=>this.matches(m,scope)&&m.status!=='archived');
  if(!v.capabilities.archive||!rows.length||rows.some(m=>this.hidden(m)||v.busy.has(m.id))||this.restoring.has(key))return;
  const entry={scope,key,ids:new Set(rows.map(m=>m.id)),owner:v.getKey(),until:Date.now()+5000,phase:'queued'};
  entry.timer=setTimeout(()=>this.commit(entry),5000);this.pending.set(key,entry);
  if(v.active&&entry.ids.has(v.active.id))v.close();
  if(v.reviewBatch?.images.every(m=>this.hidden(m))){v.reviewView='home';v.reviewBatch=null;v.v3.select('Mockups');}else v.onChange();
  this.paintToast();if(document.activeElement===document.body)this.toast?.querySelector('button')?.focus({preventScroll:true});
 }
 undo(){
  for(const [key,entry]of this.pending)if(entry.phase==='queued'&&entry.until>Date.now()){clearTimeout(entry.timer);this.pending.delete(key);}
  this.view.onChange();this.paintToast();
 }
 valid(entry){return this.pending.get(entry.key)===entry&&entry.owner===this.view.getKey();}
 merge(data){
  const v=this.view;
  if(!data.ok||!Array.isArray(data.mockups)||data.mockups.some(m=>!m.id||!['archived','open','picked'].includes(m.status)))throw Error('Archive change was not confirmed. Refresh to check it.');
  v.revision++;
  for(const row of data.mockups){const i=v.mockups.findIndex(m=>m.id===row.id);if(i>=0)v.mockups[i]={...v.mockups[i],...row};}
 }
 async commit(entry,transport={}){
  if(!this.valid(entry)||entry.phase!=='queued')return;
  clearTimeout(entry.timer);entry.phase='saving';this.paintToast();
  try{
   const data=await this.view.api('POST',{action:'archive',...entry.scope},transport);
   if(!this.valid(entry))return;this.merge(data);
  }catch(error){if(this.valid(entry))this.view.notify(error.message,true);}
  finally{if(this.valid(entry)){this.pending.delete(entry.key);this.view.onChange();this.paintToast();}}
 }
 async restore(scope){
  const v=this.view,key=this.scopeKey(scope),owner=v.getKey(),generation=this.generation;
  if(!v.capabilities.archive||this.restoring.has(key)||v.mockups.some(m=>this.matches(m,scope)&&this.hidden(m)))return;
  this.restoring.add(key);v.onChange();
  try{
   const data=await v.api('POST',{action:'unarchive',...scope});
   if(owner!==v.getKey()||generation!==this.generation)return;this.merge(data);
   if(v.active&&this.matches(v.active,scope))v.close();
   v.notify(scope.mockup_id?'Frame restored.':'Batch restored.');
  }catch(error){if(owner===v.getKey()&&generation===this.generation)v.notify(error.message,true);}
  finally{if(owner===v.getKey()&&generation===this.generation){this.restoring.delete(key);v.onChange();}}
 }
 flush(){for(const entry of this.pending.values())if(entry.phase==='queued')void this.commit(entry,{keepalive:true});}
 paintToast(){
  clearTimeout(this.tick);
  if(!this.pending.size){this.toast?.remove();this.toast=null;return;}
  const v=this.view;
  if(!this.toast?.isConnected){this.toast=v.el('div','mockup-archive-toast');this.toast.setAttribute('role','status');this.toast.setAttribute('aria-live','polite');this.toast.setAttribute('aria-atomic','true');this.toast.append(v.el('span'),v.button('Undo','',()=>this.undo()));}
  const host=v.dialog.open?v.dialog:document.body;if(this.toast.parentElement!==host)host.append(this.toast);
  const queued=[...this.pending.values()].filter(e=>e.phase==='queued'),text=this.toast.querySelector('span'),undo=this.toast.querySelector('button');
  if(queued.length){const left=Math.max(1,Math.ceil((Math.min(...queued.map(e=>e.until))-Date.now())/1000));text.textContent=(queued.length>1?queued.length+' archive changes queued. ':queued[0].scope.mockup_id?'Frame archived. ':'Batch archived. ')+'Saving in '+left+'s.';undo.textContent=queued.length>1?'Undo all':'Undo';undo.hidden=false;}
  else{text.textContent='Saving archive changes…';undo.hidden=true;}
  this.tick=setTimeout(()=>this.paintToast(),1000);
 }
}
window.MockupArchive=MockupArchive;
