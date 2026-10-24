'use strict';
class ControlCenterV3 {
 static order=[];
 static names={};
 static isMockups(value){return value==='Mockups'||String(value).startsWith('mockups:')}
 static route(value){
  const v=String(value||'').trim(), l=v.toLowerCase();
  if(!l||l==='all'||l==='inbox')return 'inbox';
  if(l==='mockups')return 'Mockups';
  if(['spaces','roadmap'].includes(l)||/^(space|pod|agent|roadmap|mockups):[^\s]+$/i.test(v))return l;
  if(['control','jobs'].includes(l))return l==='control'?'Control':'Jobs';
  return 'inbox';
 }
 constructor(deps){Object.assign(this,deps);this.reset();}
 reset(){this.generation=(this.generation||0)+1;this.snapshots=[];this.capabilities={};this.linesFallback=false;this.lineCards=[];this.lineSnapshots=[];this.linePulse=[];this.lineDirectory=null;ControlCenterV3.order=[];ControlCenterV3.names={};this.split='yours';this.item=null;this.focusIndex=0;this.snapshotLoading=false;this.reviewBusy=new Set();this.skipped=new Set();this.skipOrder=[];try{const saved=JSON.parse(sessionStorage.getItem(this.skipAccount())||'[]');if(Array.isArray(saved))this.skipOrder=[...new Set(saved.filter(id=>typeof id==='string'))].slice(-500);}catch{}}
 skipAccount(){let hash=2166136261;for(const c of this.getKey())hash=Math.imul(hash^c.charCodeAt(0),16777619);return 'ted-board-skipped:'+String(hash>>>0);}
 accept(data){this.acceptLines(data);this.capabilities=data.capabilities||{};if(Array.isArray(data.snapshots))this.snapshots=data.snapshots;else if(this.capabilities.snapshots)this.loadSnapshots();else if(Array.isArray(data.cards))this.snapshots=[];}
 // The authenticated feed owns line identity, order, and display names.
 acceptLines(data){
  const C=ControlCenterV3;
  if(Array.isArray(data.cards))this.lineCards=data.cards;
  if(Array.isArray(data.snapshots))this.lineSnapshots=data.snapshots;
  else if(Array.isArray(data.cards)&&!data.capabilities?.snapshots)this.lineSnapshots=[];
  if(Array.isArray(data.pod_pulse))this.linePulse=data.pod_pulse;
  else if(Array.isArray(data.cards)&&data.pod_pulse_error!==true)this.linePulse=[];
  const directories=(Array.isArray(data.snapshots)?data.snapshots:[]).filter(s=>s?.kind==='lines');
  if(Array.isArray(data.lines))this.lineDirectory=data.lines;
  else if(directories.length)this.lineDirectory=directories.flatMap(s=>{
   const payload=s.payload;
   return Array.isArray(payload)?payload:Array.isArray(payload?.items)?payload.items:Array.isArray(payload?.lines)?payload.lines:[];
  });
  else if(Array.isArray(data.cards)&&!data.capabilities?.snapshots)this.lineDirectory=null;
  this.linesFallback=false;
  C.order=[];C.names=Object.create(null);
  const add=(id,name)=>{
   if(typeof id!=='string'||typeof name!=='string')return;
   id=id.toLowerCase().trim();name=name.trim();
   if(!/^[a-z0-9_-]+$/.test(id)||!name)return;
   if(!C.order.includes(id))C.order.push(id);
   C.names[id]=name;
  };
  if(this.lineDirectory!==null){
   for(const row of this.lineDirectory)if(row&&typeof row==='object')add(row.id||row.key,row.name||row.label);
   return;
  }
  // Preserve recorded identities on older cards and snapshots when available.
  const inferred=this.lineCards.filter(row=>row&&typeof row==='object').map(row=>({id:row.line,name:row.line_name||row.project,project:row.project}));
  for(const snapshot of this.lineSnapshots){
   if(!snapshot||!['pods','roadmap'].includes(snapshot.kind))continue;
   const row=snapshot.payload||{};inferred.push({id:row.line||snapshot.key,name:row.line_name||row.project,project:row.project});
  }
  const label=value=>typeof value==='string'?value.trim():'',canonical=value=>label(value).toLowerCase();
  const encode=project=>'project-'+Array.from(project,c=>c.codePointAt(0).toString(16)).join('-');
  // Project-only feeds use canonical labels for identity, preserving punctuation
  // and Unicode. Card frequency chooses the display spelling, not the route.
  const groups=new Map();
  for(const row of [...this.linePulse.map(row=>({name:row?.project})),...inferred]){
   const name=label(row.name),key=canonical(row.project||name);if(!key)continue;
   if(!groups.has(key))groups.set(key,{name,id:null});
   const group=groups.get(key);
   if(!group.id&&typeof row.id==='string'&&/^[a-z0-9_-]+$/i.test(row.id.trim()))group.id=row.id;
  }
  for(const [key,group]of groups){
   const spellings=new Map();
   for(const row of this.lineCards){const name=label(row?.project||row?.line_name);if(canonical(name)===key)spellings.set(name,(spellings.get(name)||0)+1)}
   const name=[...spellings].sort((a,b)=>b[1]-a[1])[0]?.[0]||group.name;
   add(group.id||encode(key),name);
  }
 }
 authFailed(){this.linesFallback=true;ControlCenterV3.order=Array.from({length:10},(_,i)=>'line'+(i+1));ControlCenterV3.names=Object.fromEntries(ControlCenterV3.order.map((id,i)=>[id,'Line '+(i+1)]));}
 unreadCount(card){return unread(card)?1:0;}
 pendingApprovals(card){return this.getState().approvals.filter(a=>a.status==='pending'&&(!card||a.card_id===card.id));}
 attentionBadges(parent,unreadCount,approvalCount,cls='v3-attention-count'){
  for(const [count,label]of [[unreadCount,'unread'],[approvalCount,'approvals']])if(count)parent.append(this.el('span',cls,count+' '+label));
 }
 attentionList(parent){
  const state=this.getState(),cards=state.cards.filter(c=>this.unreadCount(c)||this.pendingApprovals(c).length),orphans=this.pendingApprovals().filter(a=>!state.cards.some(c=>c.id===a.card_id));
  if(!cards.length&&!orphans.length)return;
  const list=this.el('section','v3-attention');list.append(this.el('h2',null,'Ted replied / approvals waiting'));
  for(const card of cards){const row=this.el('article','v3-row'),open=this.button(card.title,'sp-text-link',()=>{this.item=card.id;this.split='yours';this.redraw();document.querySelector('.v3-detail')?.scrollIntoView({block:'nearest'});});open.dataset.attentionCard=card.id;row.append(open);this.attentionBadges(row,this.unreadCount(card),this.pendingApprovals(card).length);list.append(row);}
  for(const approval of orphans.filter((a,i)=>orphans.findIndex(b=>b.card_id===a.card_id)===i)){const row=this.el('article','v3-row');row.append(this.el('h3',null,approval.summary||'Approval waiting'));renderApprovals({id:approval.card_id},row);list.append(row);}parent.append(list);
 }
 setup(){
  const mast=document.querySelector('.masthead');mast.classList.add('v3-top');
  const controls=this.el('div','ted-controls');controls.append(document.getElementById('talk-ted'),document.getElementById('fresh-ted'));mast.append(controls);
  const brand=mast.querySelector('.brand');brand.replaceChildren(this.el('strong','v3-logo','TED.'));
  const command=this.el('input','v3-command');command.placeholder='⌘K  approve, veto, open a space, ask Ted';command.setAttribute('aria-label','Find a view, space, or card');command.type='search';mast.insertBefore(command,document.getElementById('refresh'));
  const results=this.el('div','v3-command-results');results.hidden=true;results.setAttribute('role','region');results.setAttribute('aria-label','Search results');mast.append(results);mast.insertBefore(document.querySelector('.tab-wrap'),command);
  const search=()=>{results.replaceChildren();const q=command.value.trim().toLowerCase();results.hidden=!q;if(!q)return;const choices=[['Inbox','inbox'],['Spaces','spaces'],['Roadmap','roadmap'],['Mockups','Mockups'],...ControlCenterV3.order.map(id=>[ControlCenterV3.names[id],'space:'+id])];
   for(const [name,route] of choices.filter(([n])=>n.toLowerCase().includes(q)))results.append(this.button(name,'',()=>{command.value='';results.hidden=true;this.select(route)}));
   for(const c of this.getState().cards.filter(c=>c.title.toLowerCase().includes(q)).slice(0,8))results.append(this.button(c.title,'',()=>{command.value='';results.hidden=true;this.item=c.id;this.split='yours';this.select('inbox')}));
   if(!results.children.length)results.append(this.el('p',null,'No matching view, space, or card.'));
  };command.addEventListener('input',search);command.addEventListener('keydown',e=>{if(e.key==='Escape'){results.hidden=true;command.blur()}if(e.key==='Enter')results.querySelector('button')?.click()});
  document.addEventListener('keydown',e=>{if(this.deciding?.())return;if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();command.focus();return}if(e.target.closest('input,textarea,select,[contenteditable=true]')||document.querySelector('dialog[open]')||e.metaKey||e.ctrlKey||e.altKey)return;this.keydown?.(e)});
 }
 tabs(){
  const tabs=document.getElementById('tabs'),state=this.getState();tabs.replaceChildren();
  const active=ControlCenterV3.isMockups(state.project)?'Mockups':state.project.split(':')[0];
  const open=new Set(this.mockups.mockups.filter(m=>m.status!=='archived'&&!['approved','scrapped'].includes(m.verdict)).map(m=>JSON.stringify([m.project,m.batch]))).size;
  const list=[['inbox','Inbox',this.needs().length],['spaces','Spaces',ControlCenterV3.order.length],['roadmap','Roadmap',ControlCenterV3.order.length],['Mockups','Mockups',open]];
  list.forEach(([route,label,count],i)=>{const b=this.button(label,'tab',()=>this.select(route));b.id='v3-tab-'+i;b.setAttribute('role','tab');b.setAttribute('aria-selected',String(active===route||active==='space'&&route==='spaces'||active==='pod'&&route==='spaces'||active==='agent'&&route==='spaces'));b.setAttribute('aria-controls','main');b.append(this.el('span','tab-count',state.loaded?String(count):'…'));if(route==='inbox'&&state.loaded)this.attentionBadges(b,state.cards.filter(c=>this.unreadCount(c)).length,this.pendingApprovals().length);b.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const n=e.key==='Home'?0:e.key==='End'?3:(i+(e.key==='ArrowRight'?1:3))%4;this.select(list[n][0]);tabs.children[n].focus()}});tabs.append(b)});
  document.getElementById('main').setAttribute('aria-labelledby',tabs.querySelector('[aria-selected=true]')?.id||'v3-tab-0');
 }
 feed(kind){return this.snapshots.filter(s=>s.kind===kind).flatMap(s=>{const p=s.payload;return Array.isArray(p)?p:Array.isArray(p?.items)?p.items:Array.isArray(p?.[kind])&&['decisions','routines'].includes(kind)?p[kind]:p?[{...p,key:s.key,generated_at:s.generated_at}]:[]});}
 heading(parent,title,description='',prop='stamp',line=''){
  const hero=this.el('section','v3-hero'),text=this.el('div','v3-hero-copy');text.append(this.el('h1','v3-headline',title));if(description)text.append(this.el('p','v3-sub',description));hero.append(text);if(line)hero.append(this.say(line,prop));parent.append(hero);return hero;
 }
 say(line,prop='stamp'){const box=this.el('div','v3-ted');box.append(this.el('p','v3-bubble',line));const art=this.el('div','v3-bear');art.innerHTML=TedTheme.bear(130,{prop});box.append(art);return box;}
 paper(parent){const p=this.el('section','v3-paper');parent.append(p);return p;}
 empty(parent,text='Not logged.'){parent.append(this.el('p','v3-empty',text));}
 tools(parent){const details=this.el('details','v3-tools'),summary=this.el('summary',null,'Rules, sprint, batches, and jobs');details.append(summary);const row=this.el('div','v3-actions');for(const name of ['Veto','Rules','Sprint','Batches'])row.append(this.button(name,'',()=>controlCenter.open(name)));row.append(this.button('Jobs','',()=>this.select('Jobs')));details.append(row);const all=this.el('details','v3-all-cards');all.append(this.el('summary',null,'All project cards'));const list=this.el('div','v3-card-directory');for(const card of this.getState().cards){const open=this.button(card.project+' / '+card.title,'',()=>{this.item=card.id;this.split='yours';this.select('inbox');});list.append(open);}all.append(list);details.append(all);parent.append(details);}
 needsYou(card){return !['done','killed'].includes(card.section)&&(['yours','needs_you'].includes(card.section)||this.pendingApprovals(card).length>0);}
 needs(){return this.getState().cards.filter(c=>this.needsYou(c));}
 inboxGroups(){
  const groups=new Map();
  for(const card of this.needs()){
   const line=this.lineOf(card),name=ControlCenterV3.names[line]||String(card.project||card.line||'Ted ops').trim()||'Ted ops',id=line||name.toLowerCase();
   if(!groups.has(id))groups.set(id,{id,name,cards:[]});groups.get(id).cards.push(card);
  }
  return [...groups.values()].sort((a,b)=>b.cards.length-a.cards.length);
 }
 inboxQueue(){
  const cards=this.inboxGroups().flatMap(group=>group.cards),byId=new Map(cards.map(card=>[card.id,card])),skipped=new Set(this.skipOrder);
  return [...cards.filter(card=>!skipped.has(card.id)),...this.skipOrder.map(id=>byId.get(id)).filter(Boolean)];
 }
 skipCard(card){
  if(!this.needsYou(card))return;
  const queue=this.inboxQueue(),index=queue.findIndex(c=>c.id===card.id);if(index<0)return;
  const next=queue[(index+1)%queue.length];
  this.skipOrder=this.skipOrder.filter(id=>id!==card.id&&queue.some(c=>c.id===id));this.skipOrder.push(card.id);this.skipped.add(card.id);
  try{sessionStorage.setItem(this.skipAccount(),JSON.stringify(this.skipOrder));}catch{}
  this.item=null;this.focusIndex=this.inboxQueue().findIndex(c=>c.id===next.id);this.redraw();
  requestAnimationFrame(()=>{const target=[...document.querySelectorAll('[data-ticket]')].find(node=>node.dataset.ticket===next.id);target?.focus();});
 }
 cardsForLine(which){
  const number=(value,fallback)=>value!==null&&value!==undefined&&value!==''&&Number.isFinite(Number(value))?Number(value):fallback;
  return this.getState().cards.filter(c=>this.lineOf(c)===which).sort((a,b)=>number(b.priority_value,0)-number(a.priority_value,0)||number(a.sort,Infinity)-number(b.sort,Infinity));
 }
 kind(card){return ({money_out:'money out',your_words:'your words',your_login:'your login',legal:'legal',database_write:'database write'})[TedDecisionKinds.normalize(card.decision_kind||card.kind)]||'your call';}
 lineOf(card){const recorded=String(card.line||'').toLowerCase().trim();if(ControlCenterV3.order.includes(recorded))return recorded;const raw=String(card.project||card.line||'').trim(),lower=raw.toLowerCase();return ControlCenterV3.order.find(id=>ControlCenterV3.names[id]===raw)||ControlCenterV3.order.find(id=>id===lower||String(ControlCenterV3.names[id]||'').toLowerCase()===lower)||null;}
 payloads(kind){return this.snapshots.filter(s=>s.kind===kind).map(s=>s.payload||{});}
 decisions(){
  const cards=this.getState().cards;
  const held=d=>{const card=cards.find(c=>c.id===d.card_id);return ['approve','needs_approval'].includes(d.status)||[d.decision_kind,d.kind,card?.decision_kind,card?.kind].some(TedDecisionKinds.isReserved);};
  const rows=this.feed('decisions').filter(d=>!held(d));
  for(const veto of controlCenter.vetoes){if(rows.some(d=>d.card_id===veto.card_id)||held(veto))continue;rows.push({...veto,title:veto.planned_action,status:veto.status==='stopped'?'stopped':'proposed',legacy:true});}
  return rows;
 }
 async loadSnapshots(){
  if(!this.capabilities.snapshots||this.snapshotLoading)return;
  this.snapshotLoading=true;const generation=this.generation;
  try{const data=await this.api('GET',undefined,'snapshots');if(generation!==this.generation||!this.capabilities.snapshots)return;if(Array.isArray(data.snapshots)){this.snapshots=data.snapshots;this.acceptLines(data);this.redraw();}}
  catch{if(generation===this.generation)this.notice('Snapshot updates are unavailable. Existing cards and mockups still work.',true);}
  finally{if(generation===this.generation)this.snapshotLoading=false;}
 }
 inbox(main){
  const state=this.getState();if(!state.loaded){main.append(this.el('p','loading',state.loading?'Opening your board…':'Your board could not be loaded. Tap Refresh to try again.'));return;}
  const n=this.needs().length,calls=this.decisions();
  const hero=this.heading(main,'NEED YOU',new Intl.DateTimeFormat('en-US',{weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZone:'America/Los_Angeles'}).format(new Date())+' Pacific','stamp',this.needs()[0]?.ted_line||'Your calls, then I can keep moving.');
  const eye=this.el('div','v3-counter');eye.innerHTML=TedTheme.eye(n);hero.querySelector('.v3-hero-copy').prepend(eye);hero.querySelector('.v3-hero-copy').append(this.el('p','v3-scrawl','TED HANDLED '+calls.filter(c=>c.status==='done').length));
  const paper=this.paper(main),splits=this.el('nav','v3-splits');splits.setAttribute('aria-label','Inbox splits');
  const routines=this.feed('routines'),woke=this.payloads('decisions').flatMap(p=>Array.isArray(p.woke)?p.woke:[]);
  for(const [id,label,count] of [['yours','Yours',n],['decided','Ted decided',calls.length],['routines','Routines',routines.filter(r=>!['fine','ok'].includes(r.state||r.status||r.ok)).length],['woke','Woke',woke.length]]){const b=this.button(label,'',()=>{this.split=id;this.item=null;this.redraw()});b.dataset.split=id;b.setAttribute('aria-pressed',String(this.split===id));b.append(this.el('span','v3-count',count));splits.append(b);}paper.append(splits);
  const keys=this.el('p','v3-keys','1 yes · 2 not yet · H snooze · S skip · J / K move · U undo · Tab next split');paper.append(keys);
  if(this.split==='decided'){const grid=this.el('div','v3-inbox-grid');grid.append(this.decisionList(calls));grid.append(this.say(TedTheme.lines.decided,'sign:VETO?'));paper.append(grid);}
  else if(this.split==='routines')this.routines(paper,routines);
  else if(this.split==='woke'){if(!woke.length)this.empty(paper,'No wake-up status logged. Approvals stay on their cards.');for(const w of woke){const row=this.el('article','v3-row');row.append(this.el('span','v3-status',w.state||'not logged'),this.el('h3',null,w.title||w.t||'Approval'),this.el('p',null,w.why||w.now||w.s||'Not logged.'));paper.append(row);}}
  else{
   const grid=this.el('div','v3-inbox-grid v3-project-layout'),list=this.el('div','v3-yours v3-projects'),cards=this.inboxQueue(),positions=new Map(cards.map((card,i)=>[card.id,i]));
   if(!cards.length)this.empty(list,'Nothing on you right now. Go live a little.');
   for(const [i,group] of this.inboxGroups().entries()){
    const section=this.el('section','v3-project-group'),heading=this.el('h2','v3-project-heading');heading.id='inbox-project-'+i;section.setAttribute('aria-labelledby',heading.id);
    heading.append(this.el('span','v3-project-name',group.name),this.el('span','v3-project-count',String(group.cards.length)));section.append(heading);
    for(const card of group.cards.sort((a,b)=>positions.get(a.id)-positions.get(b.id)))section.append(this.ticket(card,positions.get(card.id)));
    list.append(section);
   }
   grid.append(list);
   const selected=this.getState().cards.find(c=>c.id===this.item);if(selected)grid.append(this.itemDetail(selected,cards));else {const side=this.el('aside','v3-stream');side.append(this.el('h2',null,'Ted decided'),this.decisionList(calls));grid.append(side);}paper.append(grid);
  }
  this.attentionList(paper);this.tools(paper);
  if(this.split==='yours'&&this.spTiles){const spaces=this.el('section','v3-home-spaces');spaces.append(this.el('h2',null,'Spaces'));this.spTiles(spaces);main.append(spaces);}
 }
 ticket(card,i){
  const row=this.el('article','v3-ticket'+(i===0?' v3-ticket-hero':''));row.dataset.cardId=card.id;row.dataset.ticket=card.id;row.tabIndex=0;row.addEventListener('focusin',()=>this.focusIndex=i);
  const meta=this.el('div','v3-meta');meta.append(this.el('span','v3-tag',this.kind(card)),this.el('strong',null,ControlCenterV3.names[this.lineOf(card)]||card.line||card.project));if(this.skipped.has(card.id))meta.append(this.el('span','v3-tag v3-skipped','skipped'));if(this.unreadCount(card))meta.append(replyDot());this.attentionBadges(meta,this.unreadCount(card),this.pendingApprovals(card).length);row.append(meta);
  const open=this.button(card.title,'v3-ticket-title',()=>{this.item=card.id;this.redraw();document.querySelector('.v3-detail')?.scrollIntoView({block:'nearest'});});open.dataset.openCard=card.id;row.append(open,this.el('p','v3-why',card.why||String(card.body||'').split('\n')[0]||'Open this card to read the details.'));
  const actions=this.el('div','v3-actions');for(const o of options(card))actions.append(this.button(o.label,'primary',()=>this.answerCard(card,o)));
  if(this.kind(card)==='database write')actions.append(this.button('Read the SQL','',()=>{this.item=card.id;this.redraw();document.querySelector('.v3-detail')?.scrollIntoView({block:'nearest'});}));
  else this.swipe(row,()=>this.quick(card,0),()=>this.quick(card,1));
  actions.append(this.button('Skip','v3-skip',()=>this.skipCard(card)));row.append(actions);return row;
 }
 async answerCard(card,option){const ok=await act(card,'choice',option.value);if(ok){this.lastAnswer={id:card.id};this.item=null;this.redraw();}}
 quick(card,index){const option=options(card)[index];if(option){const ks=[card.decision_kind,card.kind].filter(Boolean);if((!ks.length||ks.some(k=>TedDecisionKinds.isReserved(k)))&&!confirm(option.label+': '+card.title+'?'))return;return this.answerCard(card,option);}this.notice('Open the card and choose one of its recorded actions.');}
 swipe(node,right,left){let start=null;node.style.touchAction='pan-y';node.addEventListener('pointerdown',e=>{if(e.target.closest('button,a,input,textarea,select')||e.pointerType==='mouse')return;start={x:e.clientX,y:e.clientY};});node.addEventListener('pointercancel',()=>start=null);node.addEventListener('pointerup',e=>{if(!start)return;const dx=e.clientX-start.x,dy=e.clientY-start.y;start=null;if(Math.abs(dx)>90&&Math.abs(dx)>Math.abs(dy)*1.5)(dx>0?right:left)();});}
 itemDetail(card,cards){
  const detail=this.el('aside','v3-detail');detail.append(this.button((cards.includes(card)?'Inbox / Yours / '+(cards.indexOf(card)+1)+' of '+cards.length:'Inbox / '+card.project+' / '+({ted_doing:'In progress',up_next:'Up next',done:'Done',killed:'Killed'}[card.section]||'Card')),'v3-crumb',()=>{this.item=null;this.redraw()}),this.el('span','v3-tag',this.kind(card)),this.el('h2','v3-detail-title',card.title));
  if(card.ted_call)detail.append(this.el('p','v3-call',card.ted_call));
  const original=this.renderCard(card);original.querySelector('h3')?.remove();detail.append(original);
  if(this.kind(card)==='database write'){const sql=this.el('details','v3-sql');sql.open=true;sql.append(this.el('summary',null,'Read the SQL'));const url=safeURL(card.sql_url);if(url){const a=this.el('a',null,'Open the SQL');a.href=url;a.target='_blank';a.rel='noopener noreferrer';sql.append(a);}else sql.append(this.el('pre',null,card.sql||card.sql_text||card.body||'SQL attachment not logged. Ask Ted for apply.sql before approving.'));detail.append(sql);}
  const verbs=this.el('div','v3-actions');verbs.append(this.button('Snooze','',()=>act(card,'move','up_next')));if(this.needsYou(card))verbs.append(this.button('Skip','v3-skip',()=>this.skipCard(card)));detail.append(verbs);return detail;
 }
 decisionList(calls){
  const list=this.el('div','v3-decisions');if(!calls.length)this.empty(list,'No calls logged.');
  for(const d of calls){const row=this.el('article','v3-decision'),status=d.status||'not logged';let label=status;
   if(status==='proposed')label=d.veto_starts?`proposed, ${d.veto_hours||'?'}h veto from first view`:'proposed, veto clock not started';
   row.append(this.el('span','v3-status',label));if(d.card_close)row.append(this.el('span','v3-status','card close, your rule pending'));row.append(this.el('small',null,ControlCenterV3.names[d.line]||d.line||'Line not logged'),this.el('h3',null,d.title||d.planned_action||'Untitled call'),this.el('p',null,d.why||'Reason not logged.'));
   if(status==='proposed'){const veto=controlCenter.vetoes.find(v=>v.card_id===d.card_id);const b=this.button('Veto','',()=>veto?controlCenter.stopVeto(veto):this.decisionAction(d,'veto'));b.disabled=!veto&&!this.capabilities.decision_action;row.append(b);}
   else if(status==='done'&&d.undo){const b=this.button(d.undo==='split'?'Split back':d.undo==='reopen'?'Reopen':'Undo','',()=>this.decisionAction(d,d.undo));b.disabled=!this.capabilities.decision_action;row.append(b);}
   list.append(row);
  }return list;
 }
 async decisionAction(d,choice){if(!this.capabilities.decision_action)return;const generation=this.generation;try{const result=await this.api('POST',{action:'decision_action',decision_id:d.id,choice,operation_id:crypto.randomUUID()});if(generation!==this.generation)return;if(!result.ok)throw Error('Decision was not confirmed.');await this.loadSnapshots();}catch(e){if(generation===this.generation)this.notice(e.message,true);}}
 routines(parent,rows){
  const grid=this.el('div','v3-inbox-grid'),reviews=this.el('section'),list=this.el('section');reviews.append(this.el('h2',null,'Bookmarks and screenshots'));const items=this.payloads('routines').flatMap(p=>Array.isArray(p.review_items)?p.review_items:[]);
  if(!items.length)this.empty(reviews,'No review items logged.');for(const item of items){const row=this.el('article','v3-review');row.dataset.reviewId=item.id;row.tabIndex=0;row.append(this.el('h3',null,item.title||item.t),this.el('p',null,item.why||'Reason not logged.'),this.el('p','v3-call','Ted says '+(item.suggestion||item.ted||'not logged')));const actions=this.el('div','v3-actions');for(const [choice,label]of [['keep','Keep'],['skip','Skip'],['card','Card it']]){const b=this.button(label,'',()=>this.reviewChoice(item,choice));b.disabled=!this.capabilities.review_choice||this.reviewBusy?.has(item.id);actions.append(b);}row.append(actions);reviews.append(row);}
  list.append(this.el('h2',null,'Every routine'));if(!rows.length)this.empty(list,'Routine ledger not logged.');const fine=this.el('details','v3-fine');fine.append(this.el('summary',null,rows.filter(r=>['fine','ok'].includes(r.state||r.status||r.ok)).length+' fine routines hidden'));
  for(const r of rows){const row=this.el('article','v3-routine'),state=r.state||r.status||({ok:'fine',warn:'look',fail:'broke'})[r.ok]||'not logged';row.append(this.el('span','v3-status',state),this.el('h3',null,r.name||r.n),this.el('p',null,r.last_output||r.out||'Output not logged.'),this.el('small',null,'Last run: '+(r.last_run||r.last||'not logged')+' · '+(r.schedule||r.sched||'Schedule not logged')));(['fine','ok'].includes(state)?fine:list).append(row);}list.append(fine);grid.append(reviews,list);parent.append(grid,this.say(TedTheme.lines.routines,'glass'));
 }
 async reviewChoice(item,choice){if(!this.capabilities.review_choice)return;this.reviewBusy||=new Set();if(this.reviewBusy.has(item.id))return;this.reviewBusy.add(item.id);const generation=this.generation;this.redraw();try{const result=await this.api('POST',{action:'review_choice',item_id:item.id,choice,operation_id:crypto.randomUUID()});if(generation!==this.generation)return;if(!result.ok)throw Error('Review choice was not confirmed.');for(const p of this.payloads('routines'))if(Array.isArray(p.review_items))p.review_items=p.review_items.filter(i=>i.id!==item.id);this.notice(choice==='card'?'Card requested.':'Review choice saved.');}catch(e){if(generation===this.generation)this.notice(e.message,true);}finally{if(generation===this.generation){this.reviewBusy.delete(item.id);this.redraw();}}}
 keydown(e){if(ControlCenterV3.isMockups(this.getState().project)){this.mockups.keydown?.(e);return;}if(this.spacesKeydown?.(e))return;if(this.getState().project!=='inbox')return;if(e.key==='Tab'&&['BODY','MAIN'].includes(e.target.tagName)){e.preventDefault();const splits=['yours','decided','routines','woke'];this.split=splits[(splits.indexOf(this.split)+1)%4];this.redraw();return;}if(this.split==='routines'){const choice=({k:'keep',s:'skip',c:'card'})[e.key.toLowerCase()];if(choice){const items=this.payloads('routines').flatMap(p=>Array.isArray(p.review_items)?p.review_items:[]);const id=e.target.closest('[data-review-id]')?.dataset.reviewId,item=items.find(i=>i.id===id)||items[0];if(item){e.preventDefault();this.reviewChoice(item,choice);}}return;}if(this.split!=='yours'){if(e.key.toLowerCase()==='u')document.querySelector('.v3-decisions button:not(:disabled)')?.textContent==='Undo'&&document.querySelector('.v3-decisions button:not(:disabled)').click();return;}const cards=this.inboxQueue();if(['j','k'].includes(e.key.toLowerCase())){e.preventDefault();this.focusIndex=Math.max(0,Math.min(cards.length-1,this.focusIndex+(e.key.toLowerCase()==='j'?1:-1)));const next=cards[this.focusIndex];[...document.querySelectorAll('[data-ticket]')].find(node=>node.dataset.ticket===next?.id)?.focus();return;}const focused=e.target.closest('[data-ticket]')?.dataset.ticket;const card=cards.find(c=>c.id===(focused||this.item))||cards[this.focusIndex];if(card&&e.key.toLowerCase()==='s'){e.preventDefault();this.skipCard(card);return;}if(card&&['1','2'].includes(e.key)){e.preventDefault();this.quick(card,Number(e.key)-1);}if(card&&e.key.toLowerCase()==='h'){e.preventDefault();act(card,'move','up_next');}if(e.key.toLowerCase()==='u'){this.notice('Use the recorded Undo action in Ted decided or Mockups.');}if(e.key==='Tab'&&['BODY','MAIN'].includes(e.target.tagName)){e.preventDefault();const splits=['yours','decided','routines','woke'];this.split=splits[(splits.indexOf(this.split)+1)%4];this.redraw();}}

 render(main,route){
  if(!['inbox','spaces','roadmap'].includes(route)&&!route.includes(':')&&!ControlCenterV3.isMockups(route))return false;
  main.classList.add('v3');
  if(route==='inbox'){this.inbox(main);return true;}
  if(route==='spaces'){this.spaces(main);return true;}
  if(route==='roadmap'||route.startsWith('roadmap:')){this.roadmap(main,route.split(':')[1]);return true;}
  if(/^(space|pod|agent):/.test(route)){const [kind,rest]=route.split(':');const [line,raw]=rest.split('/');let id=raw;try{id=decodeURIComponent(raw||'');}catch{}this[kind](main,line,id);return true;}
  if(ControlCenterV3.isMockups(route)){this.mockups.render(main);return true;}
  this.heading(main,route==='inbox'?'NEED YOU':route==='spaces'?'TEN LINES. ONE BOARD.':route.toUpperCase(),'Your calls, what Ted is on, and what comes next.','stamp','The board is open. Your calls stay yours.');
  const p=this.paper(main);if(route==='inbox'){const cards=this.getState().cards.filter(c=>c.section==='needs_you');if(!cards.length)this.empty(p,'Nothing on you right now.');cards.forEach(c=>p.append(this.renderCard(c)));this.tools(p);}else this.empty(p,'Not logged. This view is waiting for its live feed.');return true;
 }
}

if(window.installSpacesV3)installSpacesV3(ControlCenterV3);
if(window.installRoadmapV3)installRoadmapV3(ControlCenterV3);
