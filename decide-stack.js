'use strict';
/* A presentation layer over the board's existing card and approval actions. */
class DecideStack {
 constructor(deps){Object.assign(this,deps);this.reset();this.clock=setInterval(()=>this.paintToast(),250);}
 reset(){
  this.sessionRecords||=new Map();
  for(const item of this.pending?.values()||[])clearTimeout(item.timer);
  clearTimeout(this.departTimer);document.querySelector('.decide-toast')?.remove();this.generation=(this.generation||0)+1;this.pending=new Map();this.later=[];this.leaving=false;this.lastShown=null;this.more=new Set();this.notes=new Set();this.errors='';
  let preference='';try{preference=sessionStorage.getItem('ted-board-view')||'';}catch{}
  this.mode=new URLSearchParams(location.search).get('view')||preference||(matchMedia('(width < 760px)').matches?'decide':'list');
 }
 active(){return this.mode==='decide'&&this.getState().project==='inbox';}
 view(mode){this.mode=mode;try{sessionStorage.setItem('ted-board-view',mode);}catch{}this.lastShown=null;this.select('inbox');}
 account(){let hash=2166136261;for(const c of this.getKey())hash=Math.imul(hash^c.charCodeAt(0),16777619);return 'ted-board-decided:'+String(hash>>>0);}
 records(){let saved={};try{const parsed=JSON.parse(this.storage.get(this.account())||'{}');if(parsed&&typeof parsed==='object'&&!Array.isArray(parsed))saved=parsed;}catch{}return {...saved,...this.sessionRecords.get(this.getKey())};}
 ask(card){
  const asks=(Array.isArray(card.messages)?card.messages:[]).filter(m=>m?.who==='ted'&&typeof m.text==='string'&&(/\?|\b(?:please (?:approve|choose|pick|review)|new ask|need your (?:approval|decision|input))\b/i.test(m.text)));
  return JSON.stringify([card.title||'',card.body||'',card.why||'',card.ted_call||'',card.decision_kind||card.kind||'',this.options(card),asks.at(-1)||null]);
 }
 approvals(card){return this.getState().approvals.filter(a=>a.card_id===card.id&&a.status==='pending');}
 hidden(card,records=this.records()){const saved=records[card.id];return saved?.ask===this.ask(card)&&this.approvals(card).every(a=>(saved.approvals||[]).includes(a.id));}
 remember(card,approvalIds=[]){const rows=this.sessionRecords.get(this.getKey())||{};rows[card.id]={ask:this.ask(card),approvals:[...new Set(approvalIds)]};this.sessionRecords.set(this.getKey(),rows);this.storage.set(this.account(),JSON.stringify(this.records()));}
 isUpdate(card){
  if(card.decision_kind||this.getState().approvals.some(a=>a.card_id===card.id)||card.amount_cents!=null||(Array.isArray(card.options)?card.options.length:Boolean(card.options)))return false;
  if(/[?]|\b(?:approve|choose|pick|please|need your|decision needed|review needed)\b/i.test([card.title,card.body].join(' ').replace(/\bno (?:decision|review|approval)(?: is)? needed\b/ig,'')))return false;
  return card.section==='done'||['fyi','status','update','info'].includes(card.kind);
 }
 yesNo(card){return /^(?:yes|approve|send|proceed|confirm|allow|accept|go ahead)$/i.test(this.options(card)[0]?.label||'')||/^(?:should|shall|can|could|would|will|do|does|is|are|may|approve|send|proceed|confirm|allow|accept)\b/i.test(card.title||'');}

 items(){
  const cards=this.getState().cards.filter(c=>this.needsYou(c)||(c.section==='done'&&this.isUpdate(c)&&Date.parse(c.updated_at)>Date.now()-7*86400000));
  const records=this.records();
  const visible=cards.filter(c=>!this.hidden(c,records)&&![...this.pending.values()].some(p=>p.cards.some(x=>x.id===c.id)));
  const updates=visible.filter(c=>this.isUpdate(c));
  const normal=visible.filter(c=>!this.isUpdate(c)).sort((a,b)=>this.rank(a)-this.rank(b)).map(card=>({id:card.id,cards:[card]}));
  if(updates.length)normal.push({id:'ted-updates',cards:updates,updates:true});
  return [...normal.filter(i=>!this.later.includes(i.id)),...this.later.map(id=>normal.find(i=>i.id===id)).filter(Boolean)];
 }
 rank(card){return this.approvals(card).length||this.options(card).length||[card.decision_kind,card.kind].some(TedDecisionKinds.isReserved)||/design|approv/i.test(card.decision_kind||card.kind||'')?0:1;}
 laterItem(item){if(this.leaving)return;this.later=this.later.filter(id=>id!==item.id);this.later.push(item.id);this.lastShown=null;this.redraw();}
 depart(){
  this.leaving=true;const node=document.querySelector('.decide-card');node?.classList.add('decide-leaving');
  const delay=matchMedia('(prefers-reduced-motion: reduce)').matches?0:180;
  clearTimeout(this.departTimer);this.departTimer=setTimeout(()=>{this.leaving=false;this.lastShown=null;this.redraw();},delay);
 }
 queue(item,payload){
  if(this.leaving||this.pending.has(item.id))return;
  this.notice('');
  const entry={...item,cards:structuredClone(item.cards),payload,key:this.getKey(),generation:this.generation,until:Date.now()+5000,phase:'queued'};
  entry.timer=setTimeout(()=>this.commit(entry),5000);this.pending.set(item.id,entry);this.depart();this.paintToast();
 }
 cancelQueued(cardId){
  let cancelled=false;for(const [id,entry] of this.pending){if(entry.phase!=='queued'||!entry.cards.some(card=>card.id===cardId))continue;clearTimeout(entry.timer);this.pending.delete(id);this.later=this.later.filter(item=>item!==id);cancelled=true;}
  if(cancelled){clearTimeout(this.departTimer);this.leaving=false;this.lastShown=null;this.paintToast();}return cancelled;
 }
 async commit(entry,transport={}){
  if(entry.phase!=='queued'||entry.generation!==this.generation||entry.key!==this.getKey()||this.pending.get(entry.id)!==entry)return;
  clearTimeout(entry.timer);
  entry.phase='sending';this.paintToast();let ok=true;
  const work=entry.updates?entry.cards.map(card=>{const option=this.options(card)[0];return {card,payload:card.section==='done'?null:option?{action:'choice',value:option.value,note:''}:{action:'move',value:'done',note:''}};}):[{card:entry.cards[0],payload:entry.payload}];
  const save=async({card,payload})=>{
   // A new ask arriving during the grace period must be read before it is answered.
   const current=this.getState().cards.find(c=>c.id===card.id);
   if(!this.getState().jobsLoaded||!current||payload&&!this.needsYou(current)||current.section!==card.section||JSON.stringify(current.answer??null)!==JSON.stringify(card.answer??null)||this.ask(current)!==this.ask(card)||payload?.action==='approval'&&!this.approvals(current).some(a=>a.id===payload.approval_id)||this.approvals(current).length&&payload?.action!=='approval'){
    ok=false;this.notice('This card changed. Read the new ask before deciding.',true);return;
   }
   const confirmed=!payload||(payload.action==='approval'?await this.approve(payload,transport):await this.answer(current,payload.action,payload.value,payload.note,transport));
   if(entry.generation!==this.generation||entry.key!==this.getKey())return;
   if(confirmed)this.remember(card,payload?.action==='approval'?[payload.approval_id]:[]);else ok=false;
  };
  // Exit handlers must start every request before the document can disappear.
  if(transport.keepalive)await Promise.all(work.map(save));else for(const request of work)await save(request);
  if(entry.generation!==this.generation||entry.key!==this.getKey())return;
  if(!ok){this.later=this.later.filter(id=>id!==entry.id);this.lastShown=null;if(entry.updates)this.notice('Some updates were not saved. Try Got it again.',true);}
  this.pending.delete(entry.id);this.redraw();
 }
 flush(){for(const entry of this.pending.values())if(entry.phase==='queued')void this.commit(entry,{keepalive:true});}
 undo(){
  const queued=[...this.pending.values()].filter(p=>p.phase==='queued'&&p.until>Date.now());
  for(const entry of queued){clearTimeout(entry.timer);this.pending.delete(entry.id);this.later=this.later.filter(id=>id!==entry.id);}
  clearTimeout(this.departTimer);this.leaving=false;this.lastShown=null;this.notice(queued.length?'Decision cancelled.':'This decision is already sending.');this.redraw();
 }
 paintToast(){
  let toast=document.querySelector('.decide-toast');
  if(!toast&&this.pending.size){toast=this.el('div','decide-toast');toast.setAttribute('role','status');toast.setAttribute('aria-live','polite');toast.setAttribute('aria-atomic','true');toast.append(this.el('span'),this.button('Undo','',()=>this.undo()));document.body.append(toast);}
  if(!toast)return;
  const queued=[...this.pending.values()].filter(p=>p.phase==='queued'),sending=[...this.pending.values()].some(p=>p.phase==='sending');
  toast.hidden=!queued.length&&!sending;
  const text=toast.querySelector('span'),undo=toast.querySelector('button');
  if(queued.length){const left=Math.max(1,Math.ceil((Math.min(...queued.map(p=>p.until))-Date.now())/1000));text.textContent=(queued.length>1?queued.length+' decisions queued. ':queued[0].updates?'Updates cleared. ':'Decision queued. ')+(queued.every(p=>p.updates)?'Saving in '+left+'s.':'Sending in '+left+'s.');undo.textContent=queued.length>1?'Undo all':'Undo';undo.hidden=false;}
  else{text.textContent='Sending to Ted…';undo.hidden=true;}
 }
 noteForm(card,item){
  const form=this.el('form','decide-note');const label=this.el('label',null,'Tell Ted');label.htmlFor='decide-note';
  const input=this.el('textarea');input.id='decide-note';input.name='note';input.rows=3;input.maxLength=2000;input.required=true;input.placeholder='What should Ted do?';input.value=this.getState().drafts[card.id]||'';input.addEventListener('input',()=>this.getState().drafts[card.id]=input.value);
  const send=this.button('Send note','primary',()=>{});send.type='submit';form.append(label,input,send);
  form.addEventListener('submit',e=>{e.preventDefault();if(input.value.trim())this.queue(item,{action:'note',card_id:card.id,value:'',note:input.value.trim()});else input.focus();});return form;
 }
 details(card){
  const more=this.el('details','decide-more');more.open=this.more.has(card.id);more.append(this.el('summary',null,'More'));
  more.addEventListener('toggle',()=>{if(more.isConnected){if(more.open)this.more.add(card.id);else this.more.delete(card.id);}});
  const content=this.el('div','decide-details');if(card.body)content.append(this.el('p',null,card.body));
  for(const a of this.approvals(card)){content.append(this.el('h2',null,a.summary||'Exact content'),this.el('pre',null,a.content||'Exact content is not available. Ask Ted before approving.'));}
  if(TedDecisionKinds.normalize(card.decision_kind||card.kind)==='database_write'){content.append(this.el('p',null,'Board approval does not apply SQL. Ted reviews and applies it.'),this.el('pre',null,card.sql||card.sql_text||'Ask Ted for apply.sql before approving.'));const url=this.safeURL(card.sql_url);if(url){const link=this.el('a',null,'Read apply.sql');link.href=url;link.target='_blank';link.rel='noopener noreferrer';content.append(link);}}
  const thread=this.renderThread(card);if(thread)content.append(thread);more.append(content);return more;
 }
 render(main){
  const shell=this.el('section','decide-shell');shell.setAttribute('aria-label','Decide');
  const state=this.getState(),ready=state.loaded&&state.jobsLoaded;const head=this.el('div','decide-head');const items=ready?this.items():[];head.append(this.el('span','decide-counter',items.length+' left'),this.button('List','',()=>this.view('list')));shell.append(head);
  if(state.loadError||state.jobsError){
   const recovery=this.el('div','decide-recovery');const error=this.el('p','error',state.loadError||state.jobsError);error.setAttribute('role','alert');recovery.append(error,this.button('Refresh','',()=>this.refresh()),this.button('Access','',()=>this.access()));shell.append(recovery);main.append(shell);return;
  }
  if(!ready){shell.append(this.el('p','loading','Opening your decisions…'));main.append(shell);return;}
  const item=items[0];
  if(item){
   const card=item.cards[0],article=this.el('article','decide-card');article.dataset.cardId=item.id;article.setAttribute('aria-labelledby','decide-title');
   article.append(this.el('span','decide-project',item.updates?'From Ted':card.project||card.line||'Ted ops'));
   const title=this.el('h1',null,item.updates?'Ted’s updates ('+item.cards.length+')':card.title);title.id='decide-title';title.tabIndex=-1;article.append(title);
   if(item.updates){const list=this.el('ul','decide-updates');for(const update of item.cards){const row=this.el('li');row.append(this.el('span',null,update.project||'Ted ops'),this.el('strong',null,update.title));list.append(row);}article.append(list);}
   else{
    const summary=card.why||this.approvals(card)[0]?.summary||String(card.body||'').split('\n').find(Boolean)||'Tell Ted what you want to happen next.';article.append(this.el('p','decide-ask',summary));
    const recommendation=card.ted_call||String(card.body||'').split('\n').find(line=>/^ted(?:[’']s)? (?:call|recommendation):/i.test(line.trim()));
    if(recommendation){const call=this.el('div','decide-recommendation');call.append(this.el('strong',null,'Ted recommends'),this.el('p',null,recommendation.replace(/^ted(?:[’']s)? (?:call|recommendation):\s*/i,'')));article.append(call);}
    article.append(this.details(card));
   }
   const actions=this.el('div','decide-actions');
   if(item.updates)actions.append(this.button('Got it','primary',()=>this.queue(item,null)));
   else{
    const approvals=this.approvals(card);let opts=this.options(card);
    if(approvals.length){opts=[{label:approvals.length>1?'Review approvals':'Approve',value:'approve'}];}
    if(approvals.length>1){actions.append(this.button('Review approvals','primary',()=>{this.view('list');this.openCard(card);}));}
    else for(const opt of opts){const positive=!/^(?:no|reject|decline|not yet|wait|skip)\b/i.test(opt.label);actions.append(this.button(opt.label,positive?'primary':'',()=>this.queue(item,approvals.length?{action:'approval',approval_id:approvals[0].id,decision:'approve'}:{action:'choice',card_id:card.id,value:opt.value,note:''})));}
    if((approvals.length||(!opts.length&&this.yesNo(card)))&&!opts.some(o=>/^(?:no|reject|decline)\b/i.test(o.label)))actions.append(this.button('No','',()=>{if(approvals.length>1){this.view('list');this.openCard(card);}else this.queue(item,approvals.length?{action:'approval',approval_id:approvals[0].id,decision:'reject'}:{action:'move',card_id:card.id,value:'killed',note:''});}));
    actions.append(this.button('Tell Ted','',()=>{this.notes.add(card.id);this.redraw();document.getElementById('decide-note')?.focus();}));
   }
   actions.append(this.button('Later','quiet',()=>this.laterItem(item)));article.append(actions);
   if(!item.updates&&this.notes.has(card.id))article.append(this.noteForm(card,item));shell.append(article);
   if(this.lastShown!==item.id){this.lastShown=item.id;requestAnimationFrame(()=>{if(title.isConnected)title.focus({preventScroll:true});});}
  }else{
   const empty=this.el('div','decide-empty');const art=this.el('div','decide-bear');art.innerHTML=TedTheme.bear(150,{prop:'glass'});empty.append(art,this.el('h1',null,'You’re all clear.'),this.el('p',null,this.pending.size?'Your decisions are queued below.':'Ted has it from here. Go live a little.'),this.button('Open list','',()=>this.view('list')));shell.append(empty);
  }
  main.append(shell);this.paintToast();
 }
}
