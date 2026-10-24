'use strict';
// Batch notes use existing pin threads and feedback receipts, with explicit scope.
class MockupBatchComments {
 constructor(view){this.view=view;this.pending=new Map();this.epoch=0;this.focus=null;}
 reset(){this.epoch++;this.pending.clear();this.focus=null;}
 key(batch){return 'batch-note:'+this.view.batchKey(batch.project,batch.title);}
 images(batch){return this.view.mockups.filter(m=>m.project===batch.project&&m.batch===batch.title);}
 pins(batch){const ids=new Set(this.images(batch).map(m=>m.id));return this.view.pins.filter(p=>p.batch_note===true&&ids.has(p.mockup_id));}
 anchor(batch){return this.images(batch).filter(m=>m.status!=='archived'&&!this.view.archives.hidden(m)).sort((a,b)=>this.view.imageOrder(a,b))[0];}
 writable(batch){const v=this.view;return v.capabilities.batch_comments===true&&!batch.archived&&!!this.anchor(batch)&&!this.images(batch).some(m=>v.busy.has(m.id))&&!v.batchBusy.has(v.batchKey(batch.project,batch.title));}
 render(batch){
  const v=this.view,key=this.key(batch),owner=v.getKey(),box=v.el('section','mk3-batch-comments');
  box.setAttribute('aria-label','Batch comments');box.dataset.batchKey=key;
  box.append(v.el('h2',null,'Batch comments'));
  const pins=this.pins(batch),messages=pins.flatMap(p=>(Array.isArray(p.thread)?p.thread:[]).filter(m=>m&&['seb','ted'].includes(m.who)&&typeof m.text==='string').map((m,i)=>({...m,pin:p.id,index:i})));
  messages.sort((a,b)=>(Date.parse(a.at)||0)-(Date.parse(b.at)||0)||String(a.pin).localeCompare(String(b.pin))||a.index-b.index);
  if(messages.length){
   const list=v.el('ol','messages mk3-batch-thread');list.setAttribute('aria-label','Batch conversation');list.tabIndex=0;
   for(const m of messages){
    const row=v.el('li','message message-'+m.who);row.setAttribute('aria-label',m.who==='ted'?'Ted':'Sebastian');
    row.append(v.el('span','message-label',m.who==='ted'?'Ted':'You'),v.el('p',null,m.text));
    const date=new Date(m.at);if(!Number.isNaN(+date)){const time=v.el('time',null,v.date(m.at));time.dateTime=date.toISOString();row.append(time);}list.append(row);
   }
   box.append(list);
   for(const pin of pins)v.storage.set('ted-mockup-read:'+pin.id,v.marker(pin));
  }else box.append(v.el('p','mk3-batch-empty','No batch comments yet.'));
  const form=v.el('form','mk3-batch-comment-form'),input=v.el('textarea');
  input.setAttribute('aria-label','Comment on this batch');input.placeholder='A note for Ted about the whole batch.';input.maxLength=1200;input.rows=3;input.value=v.drafts.get(key)||'';
  const send=v.button('Send','primary',()=>{});send.type='submit';
  const saving=this.pending.has(key);input.readOnly=saving||batch.archived;
  const refreshSend=()=>{send.disabled=saving||!this.writable(batch)||!input.value.trim();};refreshSend();
  const remember=()=>{if(document.activeElement===input)this.focus={key,start:input.selectionStart,end:input.selectionEnd};};
  input.addEventListener('input',()=>{v.drafts.set(key,input.value);remember();refreshSend();});
  for(const event of ['focus','select','keyup'])input.addEventListener(event,remember);
  input.addEventListener('blur',e=>{if(e.relatedTarget)this.focus=null;});
  form.addEventListener('submit',e=>{e.preventDefault();if(owner===v.getKey())this.send(batch,input.value);});
  form.append(input,send);box.append(form);
  const status=v.el('p','mk3-batch-comment-status',saving?'Sending to Ted…':batch.archived?'Restore this batch to send another comment.':v.capabilities.batch_comments!==true?'Batch comments are not available yet. Your draft stays here.':'');
  status.setAttribute('role','status');box.append(status);
  if(this.focus?.key===key&&!saving){const selection={...this.focus};requestAnimationFrame(()=>{if(box.isConnected&&owner===v.getKey()&&document.activeElement===document.body){input.focus({preventScroll:true});input.setSelectionRange(selection.start,selection.end);}});}
  return box;
 }
 async send(batch,raw){
  const v=this.view,key=this.key(batch),text=raw.trim(),anchor=this.anchor(batch);
  if(this.pending.has(key)||!this.writable(batch)||!text||text.length>1200||!anchor)return;
  const request={owner:v.getKey(),epoch:this.epoch};this.pending.set(key,request);v.drafts.set(key,raw);v.revision++;v.onChange();
  try{
   const data=await v.api('POST',{action:'pin',mockup_id:anchor.id,batch_note:true,text});
   if(request.owner!==v.getKey()||request.epoch!==this.epoch)return;
   const pin=data.pin;
   if(!data.ok||!pin||typeof pin.id!=='string'||!pin.id||pin.mockup_id!==anchor.id||pin.batch_note!==true||!Number.isSafeInteger(data.decision_id)||data.decision_id<1||!Array.isArray(pin.thread)||!pin.thread.some(m=>m.who==='seb'&&m.text===text))throw Error('Comment was not confirmed. Refresh before sending again. Your draft is kept.');
   v.revision++;
   const index=v.pins.findIndex(p=>p.id===pin.id);if(index<0)v.pins.push(pin);else v.pins[index]=pin;
   v.drafts.delete(key);v.notify('Sent to Ted.');
  }catch(e){if(request.owner===v.getKey()&&request.epoch===this.epoch)v.notify(e.message,true);}
  finally{if(this.pending.get(key)===request){this.pending.delete(key);v.onChange();}}
 }
}
window.MockupBatchComments=MockupBatchComments;
