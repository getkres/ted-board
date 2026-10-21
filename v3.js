'use strict';
class ControlCenterV3 {
 static order=['fictora','bookish','luvo','wcd','skyauto','bld','kres','dgc','personal','ted'];
 static names={fictora:'Fictora',bookish:'Bookish',luvo:'Luvo',wcd:'WCD',skyauto:'Sky Auto',bld:'BLD and Thomas Yang',kres:'Kres',dgc:"Dad's Golf Club",personal:'Personal',ted:'Ted'};
 static isMockups(value){return value==='Mockups'||String(value).startsWith('mockups:')}
 static route(value){
  const v=String(value||'').trim(), l=v.toLowerCase();
  if(!l||l==='all'||l==='inbox')return 'inbox';
  if(l==='mockups')return 'Mockups';
  if(['spaces','roadmap'].includes(l)||/^(space|pod|agent|roadmap|mockups):[^\s]+$/i.test(v))return l;
  if(['control','jobs'].includes(l))return l==='control'?'Control':'Jobs';
  return ['Fictora','Bookish','Kres + clients','Lunair + art','Ted ops'].find(p=>p.toLowerCase()===l)||'inbox';
 }
 constructor(deps){Object.assign(this,deps);this.reset();}
 reset(){this.generation=(this.generation||0)+1;this.snapshots=[];this.capabilities={};this.split='yours';this.item=null;this.focusIndex=0;this.snapshotLoading=false;this.reviewBusy=new Set();}
 accept(data){this.capabilities=data.capabilities||{};if(Array.isArray(data.snapshots))this.snapshots=data.snapshots;else if(this.capabilities.snapshots)this.loadSnapshots();}
 setup(){
  document.documentElement.dataset.theme='zine';
  const mast=document.querySelector('.masthead');mast.classList.add('v3-top');
  const controls=this.el('div','ted-controls');controls.append(document.getElementById('talk-ted'),document.getElementById('fresh-ted'));mast.append(controls);
  const brand=mast.querySelector('.brand');brand.replaceChildren(this.el('strong','v3-logo','TED.'));
  const command=this.el('input','v3-command');command.placeholder='⌘K  approve, veto, open a space, ask Ted';command.setAttribute('aria-label','Find a view, space, or card');command.type='search';mast.insertBefore(command,document.getElementById('refresh'));
  const results=this.el('div','v3-command-results');results.hidden=true;results.setAttribute('role','region');results.setAttribute('aria-label','Search results');mast.append(results);
  const search=()=>{results.replaceChildren();const q=command.value.trim().toLowerCase();results.hidden=!q;if(!q)return;const choices=[['Inbox','inbox'],['Spaces','spaces'],['Roadmap','roadmap'],['Mockups','Mockups'],...ControlCenterV3.order.map(id=>[ControlCenterV3.names[id],'space:'+id])];
   for(const [name,route] of choices.filter(([n])=>n.toLowerCase().includes(q)))results.append(this.button(name,'',()=>{command.value='';results.hidden=true;this.select(route)}));
   for(const c of this.getState().cards.filter(c=>c.title.toLowerCase().includes(q)).slice(0,8))results.append(this.button(c.title,'',()=>{command.value='';results.hidden=true;this.item=c.id;this.split='yours';this.select('inbox')}));
   if(!results.children.length)results.append(this.el('p',null,'No matching view, space, or card.'));
  };command.addEventListener('input',search);command.addEventListener('keydown',e=>{if(e.key==='Escape'){results.hidden=true;command.blur()}if(e.key==='Enter')results.querySelector('button')?.click()});
  document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();command.focus();return}if(e.target.closest('input,textarea,select,[contenteditable=true]')||document.querySelector('dialog[open]')||e.metaKey||e.ctrlKey||e.altKey)return;this.keydown?.(e)});
 }
 tabs(){
  const tabs=document.getElementById('tabs'),state=this.getState();tabs.replaceChildren();
  const active=ControlCenterV3.isMockups(state.project)?'Mockups':state.project.split(':')[0];
  const open=new Set(this.mockups.mockups.filter(m=>m.status!=='archived'&&!['approved','scrapped'].includes(m.verdict)).map(m=>JSON.stringify([m.project,m.batch]))).size;
  const list=[['inbox','Inbox',state.cards.filter(c=>c.section==='needs_you').length],['spaces','Spaces',10],['roadmap','Roadmap',this.feed('roadmap').length],['Mockups','Mockups',open]];
  list.forEach(([route,label,count],i)=>{const b=this.button(label,'tab',()=>this.select(route));b.id='v3-tab-'+i;b.setAttribute('role','tab');b.setAttribute('aria-selected',String(active===route||active==='space'&&route==='spaces'||active==='pod'&&route==='spaces'||active==='agent'&&route==='spaces'));b.setAttribute('aria-controls','main');b.append(this.el('span','tab-count',String(count)));b.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const n=e.key==='Home'?0:e.key==='End'?3:(i+(e.key==='ArrowRight'?1:3))%4;this.select(list[n][0]);tabs.children[n].focus()}});tabs.append(b)});
  document.getElementById('main').setAttribute('aria-labelledby',tabs.querySelector('[aria-selected=true]')?.id||'v3-tab-0');
 }
 feed(kind){return this.snapshots.filter(s=>s.kind===kind).flatMap(s=>{const p=s.payload;return Array.isArray(p)?p:Array.isArray(p?.items)?p.items:Array.isArray(p?.[kind])&&['decisions','routines'].includes(kind)?p[kind]:p?[{...p,key:s.key,generated_at:s.generated_at}]:[]});}
 heading(parent,title,description='',prop='stamp',line=''){
  const hero=this.el('section','v3-hero'),text=this.el('div','v3-hero-copy');text.append(this.el('h1','v3-headline',title));if(description)text.append(this.el('p','v3-sub',description));hero.append(text);if(line)hero.append(this.say(line,prop));parent.append(hero);return hero;
 }
 say(line,prop='stamp'){const box=this.el('div','v3-ted');box.append(this.el('p','v3-bubble',line));const art=this.el('div','v3-bear');art.innerHTML=TedTheme.bear(130,{prop});box.append(art);return box;}
 paper(parent){const p=this.el('section','v3-paper');parent.append(p);return p;}
 empty(parent,text='Not logged.'){parent.append(this.el('p','v3-empty',text));}
 tools(parent){const details=this.el('details','v3-tools'),summary=this.el('summary',null,'Rules, sprint, batches, and jobs');details.append(summary);const row=this.el('div','v3-actions');for(const name of ['Veto','Rules','Sprint','Batches'])row.append(this.button(name,'',()=>controlCenter.open(name)));row.append(this.button('Jobs','',()=>this.select('Jobs')));details.append(row);parent.append(details);}
 needs(){return this.getState().cards.filter(c=>c.section==='needs_you');}
 kind(card){const k=String(card.decision_kind||card.kind||'');return /database|sql|db_write/.test(k)?'database write':/money|spend/.test(k)?'money out':/login|auth/.test(k)?'your login':/legal|signature/.test(k)?'legal':/copy|words|send/.test(k)?'your words':'your call';}
 lineOf(card){const raw=String(card.line||card.project||'').toLowerCase();return ControlCenterV3.order.find(id=>id===raw||ControlCenterV3.names[id].toLowerCase()===raw)||(/ted/.test(raw)?'ted':/lunair/.test(raw)?'fictora':null);}
 payloads(kind){return this.snapshots.filter(s=>s.kind===kind).map(s=>s.payload||{});}
 decisions(){
  const cards=this.getState().cards;
  const held=d=>['approve','needs_approval'].includes(d.status)||/money|spend|database|sql|send|email/.test(String(d.decision_kind||d.kind||''))||/money|spend|database|sql|send|email/.test(String(cards.find(c=>c.id===d.card_id)?.decision_kind||''));
  const rows=this.feed('decisions').filter(d=>!held(d));
  for(const veto of controlCenter.vetoes){if(rows.some(d=>d.card_id===veto.card_id)||held(veto))continue;rows.push({...veto,title:veto.planned_action,status:veto.status==='stopped'?'stopped':'proposed',legacy:true});}
  return rows;
 }
 async loadSnapshots(){
  if(!this.capabilities.snapshots||this.snapshotLoading)return;
  this.snapshotLoading=true;const generation=this.generation;
  try{const data=await this.api('GET',undefined,'snapshots');if(generation!==this.generation)return;if(Array.isArray(data.snapshots)){this.snapshots=data.snapshots;this.redraw();}}
  catch{if(generation===this.generation)this.notice('Snapshot updates are unavailable. Existing cards and mockups still work.',true);}
  finally{if(generation===this.generation)this.snapshotLoading=false;}
 }
 inbox(main){
  const n=this.needs().length,calls=this.decisions();
  const hero=this.heading(main,'NEED YOU',new Intl.DateTimeFormat('en-US',{weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZone:'America/Los_Angeles'}).format(new Date())+' Pacific','stamp',this.needs()[0]?.ted_line||'Your calls, then I can keep moving.');
  const eye=this.el('div','v3-counter');eye.innerHTML=TedTheme.eye(n);hero.querySelector('.v3-hero-copy').prepend(eye);hero.querySelector('.v3-hero-copy').append(this.el('p','v3-scrawl','and I handled '+calls.filter(c=>c.status==='done').length+' more'));
  const paper=this.paper(main),splits=this.el('nav','v3-splits');splits.setAttribute('aria-label','Inbox splits');
  const routines=this.feed('routines'),woke=this.payloads('decisions').flatMap(p=>Array.isArray(p.woke)?p.woke:[]);
  for(const [id,label,count] of [['yours','Yours',n],['decided','Ted decided',calls.length],['routines','Routines',routines.filter(r=>!['fine','ok'].includes(r.state||r.status||r.ok)).length],['woke','Woke',woke.length]]){const b=this.button(label,'',()=>{this.split=id;this.item=null;this.redraw()});b.dataset.split=id;b.setAttribute('aria-pressed',String(this.split===id));b.append(this.el('span','v3-count',count));splits.append(b);}paper.append(splits);
  const keys=this.el('p','v3-keys','1 yes · 2 not yet · H snooze · J / K move · U undo · Tab next split');paper.append(keys);
  if(this.split==='decided'){const grid=this.el('div','v3-inbox-grid');grid.append(this.decisionList(calls));grid.append(this.say(TedTheme.lines.decided,'sign:VETO?'));paper.append(grid);}
  else if(this.split==='routines')this.routines(paper,routines);
  else if(this.split==='woke'){if(!woke.length)this.empty(paper,'No wake-up status logged. Approvals stay on their cards.');for(const w of woke){const row=this.el('article','v3-row');row.append(this.el('span','v3-status',w.state||'not logged'),this.el('h3',null,w.title||w.t||'Approval'),this.el('p',null,w.why||w.now||w.s||'Not logged.'));paper.append(row);}}
  else{
   const grid=this.el('div','v3-inbox-grid'),list=this.el('div','v3-yours'),cards=this.needs();
   if(!cards.length)this.empty(list,'Nothing on you right now. Go live a little.');
   for(const [i,card] of cards.entries())list.append(this.ticket(card,i));
   grid.append(list);
   const selected=cards.find(c=>c.id===this.item);if(selected)grid.append(this.itemDetail(selected,cards));else {const side=this.el('aside','v3-stream');side.append(this.el('h2',null,'Ted decided'),this.decisionList(calls));grid.append(side);}paper.append(grid);
  }
  this.tools(paper);
 }
 ticket(card,i){
  const row=this.el('article','v3-ticket'+(i===0?' v3-ticket-hero':''));row.dataset.cardId=card.id;row.dataset.ticket=card.id;row.tabIndex=0;
  const meta=this.el('div','v3-meta');meta.append(this.el('span','v3-tag',this.kind(card)),this.el('strong',null,card.line||card.project));row.append(meta);
  const open=this.button(card.title,'v3-ticket-title',()=>{this.item=card.id;this.redraw();document.querySelector('.v3-detail')?.scrollIntoView({block:'nearest'});});open.dataset.openCard=card.id;row.append(open,this.el('p','v3-why',card.why||String(card.body||'').split('\n')[0]||'Open this card to read the details.'));
  const actions=this.el('div','v3-actions');for(const o of options(card))actions.append(this.button(o.label,'primary',()=>this.answerCard(card,o)));
  if(this.kind(card)==='database write')actions.append(this.button('Read the SQL','',()=>{this.item=card.id;this.redraw();document.querySelector('.v3-detail')?.scrollIntoView({block:'nearest'});}));
  else this.swipe(row,()=>this.quick(card,0),()=>this.quick(card,1));
  row.append(actions);return row;
 }
 async answerCard(card,option){const ok=await act(card,'choice',option.value);if(ok){this.lastAnswer={id:card.id};this.item=null;this.redraw();}}
 quick(card,index){const option=options(card)[index];if(option)return this.answerCard(card,option);this.notice('Open the card and choose one of its recorded actions.');}
 swipe(node,right,left){let start=null;node.style.touchAction='pan-y';node.addEventListener('pointerdown',e=>{if(e.target.closest('button,a,input,textarea,select')||e.pointerType==='mouse')return;start={x:e.clientX,y:e.clientY};});node.addEventListener('pointercancel',()=>start=null);node.addEventListener('pointerup',e=>{if(!start)return;const dx=e.clientX-start.x,dy=e.clientY-start.y;start=null;if(Math.abs(dx)>90&&Math.abs(dx)>Math.abs(dy)*1.5)(dx>0?right:left)();});}
 itemDetail(card,cards){
  const detail=this.el('aside','v3-detail');detail.append(this.button('Inbox / Yours / '+(cards.indexOf(card)+1)+' of '+cards.length,'v3-crumb',()=>{this.item=null;this.redraw()}),this.el('span','v3-tag',this.kind(card)),this.el('h2','v3-detail-title',card.title));
  if(card.ted_call)detail.append(this.el('p','v3-call',card.ted_call));
  const original=this.renderCard(card);original.querySelector('h3')?.remove();detail.append(original);
  if(this.kind(card)==='database write'){const sql=this.el('details','v3-sql');sql.open=true;sql.append(this.el('summary',null,'Read the SQL'));const url=safeURL(card.sql_url);if(url){const a=this.el('a',null,'Open the SQL');a.href=url;a.target='_blank';a.rel='noopener noreferrer';sql.append(a);}else sql.append(this.el('pre',null,card.sql||card.sql_text||card.body||'SQL attachment not logged. Ask Ted for apply.sql before approving.'));detail.append(sql);}
  const verbs=this.el('div','v3-actions');verbs.append(this.button('Snooze','',()=>act(card,'move','up_next')));detail.append(verbs);return detail;
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
  if(!items.length)this.empty(reviews,'No review items logged.');for(const item of items){const row=this.el('article','v3-review');row.append(this.el('h3',null,item.title||item.t),this.el('p',null,item.why||'Reason not logged.'),this.el('p','v3-call','Ted says '+(item.suggestion||item.ted||'not logged')));const actions=this.el('div','v3-actions');for(const [choice,label]of [['keep','Keep'],['skip','Skip'],['card','Card it']]){const b=this.button(label,'',()=>this.reviewChoice(item,choice));b.disabled=!this.capabilities.review_choice||this.reviewBusy?.has(item.id);actions.append(b);}row.append(actions);reviews.append(row);}
  list.append(this.el('h2',null,'Every routine'));if(!rows.length)this.empty(list,'Routine ledger not logged.');const fine=this.el('details','v3-fine');fine.append(this.el('summary',null,rows.filter(r=>['fine','ok'].includes(r.state||r.status||r.ok)).length+' fine routines hidden'));
  for(const r of rows){const row=this.el('article','v3-routine'),state=r.state||({ok:'fine',warn:'look',fail:'broke'})[r.ok]||'not logged';row.append(this.el('span','v3-status',state),this.el('h3',null,r.name||r.n),this.el('p',null,r.last_output||r.out||'Output not logged.'),this.el('small',null,'Last run: '+(r.last_run||r.last||'not logged')+' · '+(r.schedule||r.sched||'Schedule not logged')));(['fine','ok'].includes(state)?fine:list).append(row);}list.append(fine);grid.append(reviews,list);parent.append(grid,this.say(TedTheme.lines.routines,'glass'));
 }
 async reviewChoice(item,choice){if(!this.capabilities.review_choice)return;this.reviewBusy||=new Set();if(this.reviewBusy.has(item.id))return;this.reviewBusy.add(item.id);const generation=this.generation;this.redraw();try{const result=await this.api('POST',{action:'review_choice',item_id:item.id,choice,operation_id:crypto.randomUUID()});if(generation!==this.generation)return;if(!result.ok)throw Error('Review choice was not confirmed.');for(const p of this.payloads('routines'))if(Array.isArray(p.review_items))p.review_items=p.review_items.filter(i=>i.id!==item.id);this.notice(choice==='card'?'Card requested.':'Review choice saved.');}catch(e){if(generation===this.generation)this.notice(e.message,true);}finally{if(generation===this.generation){this.reviewBusy.delete(item.id);this.redraw();}}}
 keydown(e){if(this.getState().project!=='inbox')return;const cards=this.needs();if(['j','k'].includes(e.key.toLowerCase())){e.preventDefault();this.focusIndex=Math.max(0,Math.min(cards.length-1,this.focusIndex+(e.key.toLowerCase()==='j'?1:-1)));document.querySelectorAll('[data-ticket]')[this.focusIndex]?.focus();return;}const card=cards.find(c=>c.id===this.item)||cards[this.focusIndex];if(card&&['1','2'].includes(e.key)){e.preventDefault();this.quick(card,Number(e.key)-1);}if(card&&e.key.toLowerCase()==='h'){e.preventDefault();act(card,'move','up_next');}if(e.key.toLowerCase()==='u'){this.notice('Use the recorded Undo action in Ted decided or Mockups.');}if(e.key==='Tab'&&['BODY','MAIN'].includes(e.target.tagName)){e.preventDefault();const splits=['yours','decided','routines','woke'];this.split=splits[(splits.indexOf(this.split)+1)%4];this.redraw();}}

 render(main,route){
  if(!['inbox','spaces','roadmap'].includes(route)&&!route.includes(':'))return false;
  main.classList.add('v3');
  if(route==='inbox'){this.inbox(main);return true;}
  if(ControlCenterV3.isMockups(route)){this.mockups.render(main);return true;}
  this.heading(main,route==='inbox'?'NEED YOU':route==='spaces'?'TEN LINES. ONE BOARD.':route.toUpperCase(),'Your calls, what Ted is on, and what comes next.','stamp','The board is open. Your calls stay yours.');
  const p=this.paper(main);if(route==='inbox'){const cards=this.getState().cards.filter(c=>c.section==='needs_you');if(!cards.length)this.empty(p,'Nothing on you right now.');cards.forEach(c=>p.append(this.renderCard(c)));this.tools(p);}else this.empty(p,'Not logged. This view is waiting for its live feed.');return true;
 }
}
