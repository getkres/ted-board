'use strict';
(()=>{
 const list=value=>Array.isArray(value)?value.filter(x=>x&&typeof x==='object'):[];
 const text=(value,fallback='not logged')=>typeof value==='string'&&value.trim()?value:typeof value==='number'?String(value):fallback;
 const id=value=>text(value,'');
 function line(raw,C,project=false){
  const label=String(raw||'').trim(),named=C.order.find(k=>C.names[k]===label),recorded=C.order.find(k=>k===label),direct=project?named||recorded:recorded||named;if(direct)return direct;
  const exact=label.toLowerCase(),match=C.order.find(k=>k===exact||String(C.names[k]||'').toLowerCase()===exact);if(match)return match;
  const value=exact.replace(/[^a-z0-9]/g,'');return value?C.order.find(k=>k.replace(/[^a-z0-9]/g,'')===value||String(C.names[k]||'').toLowerCase().replace(/[^a-z0-9]/g,'')===value)||null:null;
 }
 function normalize(which,snapshots,pulse,C){
  const matching=list(snapshots).filter(s=>s.kind==='pods'&&line(s.payload?.line||s.key,C)===which),meta=matching.at(-1)?.payload||{};
  const pods=[],seen=new Set();
  for(const snapshot of matching){const payload=snapshot.payload||{};for(const raw of list(Array.isArray(payload.pods)?payload.pods:payload.items)){
   const key=id(raw.id||raw.pod_id||raw.name||raw.label);if(!key||seen.has(key))continue;seen.add(key);
   pods.push({...raw,id:key,name:text(raw.name||raw.label,key),state:text(raw.state),now:text(raw.now||raw.headline),legacy:false});
  }}
  for(const raw of list(pulse).filter(p=>(line(p.line,C)||line(p.project,C,true))===which)){
   const key=id(raw.pod_id||raw.id);if(!key||seen.has(key))continue;seen.add(key);
   pods.push({...raw,id:key,name:text(raw.label||raw.name,key),state:'not logged',now:text(raw.headline),legacy:true});
  }
  return {...meta,pods,health:text(meta.health),now:text(meta.now),weekly_read:text(meta.weekly_read),generated_at:matching.at(-1)?.generated_at,logged:matching.length>0||pods.length>0};
 }
 window.SpacesV3Data={line,normalize};
 window.installSpacesV3=function(C){Object.assign(C.prototype,{
  spData(which){
   const state=this.getState(),data=normalize(which,this.snapshots,state.podPulse,C);
   if(this.snapshots.some(s=>s.kind==='pods'&&line(s.payload?.line||s.key,C)===which))return data;
   const cards=this.cardsForLine(which);if(!cards.length)return data;
   const doing=cards.filter(c=>c.section==='ted_doing'),top=doing[0],cardIds=new Set(cards.map(c=>c.id));
   const stuck=state.jobsLoaded?state.jobs.filter(job=>job.status==='running'&&cardIds.has(job.card_id)&&Date.now()-Date.parse(job.heartbeat_at)>20*60000).length:null;
   return {...data,logged:true,fromCards:true,yourCalls:cards.filter(c=>this.needsYou(c)).length,doing:doing.length,upNext:cards.filter(c=>c.section==='up_next').length,stuck,
    now:'Ted is on: '+doing.length+' in progress'+(top?' · '+top.title+(top.live_status?' · '+top.live_status:''):'.')};
  },
  spSummary(parent,data){
   const counts=this.el('p','sp-count',data.yourCalls+' your calls · '+data.upNext+' up next · '+(data.stuck===null?'Stuck: not logged.':data.stuck+' stuck'));
   parent.append(counts,this.el('p','sp-now',data.now));
  },
  spChip(value){const raw=text(value),label=({ok:'On track',risk:'At risk',off:'Off track',wait:'On your WAIT'})[raw]||raw,node=this.el('span','v3-status sp-state',label);node.dataset.state=raw.toLowerCase().replace(/[^a-z_]/g,'');return node},
  spCub(state,size=36){const art=this.el('span','sp-cub');art.style.width=size+'px';art.style.height=size+'px';art.innerHTML=TedTheme.cub(text(state),size);return art},
  spTitle(parent,title){const h=this.el('h2','sp-section-title',title);parent.append(h);return h},
  spCrumbs(parent,parts){const nav=this.el('nav','sp-crumbs');nav.setAttribute('aria-label','Breadcrumb');for(const [i,part]of parts.entries()){if(i)nav.append(this.el('span',null,'/'));nav.append(part[1]?this.button(part[0],'v3-crumb',()=>this.select(part[1])):this.el('span',null,part[0]));}parent.append(nav)},
  spSwitch(parent,which,kind='space'){
   const nav=this.el('nav','sp-switch');nav.setAttribute('aria-label','Choose a line');
   for(const key of C.order){const b=this.button(C.names[key],'',()=>this.select(kind+':'+key));b.setAttribute('aria-current',key===which?'page':'false');nav.append(b)}parent.append(nav);
   const dots=this.el('div','sp-dots');dots.setAttribute('aria-hidden','true');for(const key of C.order)dots.append(this.el('span',key===which?'on':''));dots.append(this.el('small',null,'swipe for the next space'));parent.append(dots);
  },
  spSwipe(node,which){let start=null;node.addEventListener('pointerdown',e=>{if(e.pointerType==='mouse'||e.target.closest('button,a,input,textarea,select'))return;start={x:e.clientX,y:e.clientY}});node.addEventListener('pointercancel',()=>start=null);node.addEventListener('pointerup',e=>{if(!start)return;const dx=e.clientX-start.x,dy=e.clientY-start.y;start=null;if(Math.abs(dx)>90&&Math.abs(dx)>Math.abs(dy)*1.5){const at=C.order.indexOf(which),next=(at+(dx<0?1:-1)+C.order.length)%C.order.length;this.select('space:'+C.order[next])}})},
  spYours(parent,cards,title='Yours here'){
   this.spTitle(parent,title);if(!cards.length){parent.append(this.el('p','sp-muted',title==='Yours here'?'No asks linked to this agent.':'No current asks in this line.'));return}
   for(const card of cards){const row=this.el('div','sp-side-row');row.append(this.el('span','v3-tag',this.kind(card)),this.button(card.title,'sp-text-link',()=>{this.item=card.id;this.split='yours';this.select('inbox')}));parent.append(row)}
  },
  spRoadMini(parent,which){this.spTitle(parent,'Roadmap, now and next');
   if(typeof this.roadData!=='function'){parent.append(this.el('p','sp-muted','Roadmap not logged.'));return}
   const road=this.roadData(which);for(const lane of ['now','next']){const group=this.el('section','sp-mini-road');group.append(this.el('h3',null,lane==='now'?'Now':'Next'));if(!road[lane].length)group.append(this.el('p','sp-muted',this.roadEmpty(road,lane,which)));for(const item of road[lane].slice(0,3))group.append(this.el('p',null,text(item.title||item.name)));parent.append(group)}
   parent.append(this.button('Open '+C.names[which]+"'s roadmap",'',()=>this.select('roadmap:'+which)));
  },
  spSide(parent,which){
   const cards=this.needs().filter(c=>this.lineOf(c)===which);this.spYours(parent,cards,'Yours in '+C.names[which]);
   this.spTitle(parent,"Ted's calls in "+C.names[which]);parent.append(this.decisionList(this.decisions().filter(d=>this.lineOf(d)===which)));
   this.spTitle(parent,'Routines in '+C.names[which]);const routines=this.snapshots.filter(s=>s.kind==='routines').flatMap(s=>list(s.payload?.items||s.payload?.routines).map(r=>({...r,line:r.line||s.payload?.line||(C.order.includes(s.key)?s.key:undefined)}))).filter(r=>this.lineOf(r)===which);
   if(!routines.length)parent.append(this.el('p','sp-muted','Routine ledger not logged.'));for(const routine of routines){const row=this.el('div','sp-side-row');row.append(this.spChip(routine.state||routine.status),this.el('strong',null,text(routine.name)),this.el('p',null,text(routine.last_output)));parent.append(row)}this.spRoadMini(parent,which);
  },
  spTiles(parent){
   const grid=this.el('div','sp-space-grid');
   for(const which of C.order){const data=this.spData(which),tile=this.el('article','sp-space-tile');tile.append(this.button(C.names[which],'sp-line-name',()=>this.select('space:'+which)));if(!data.fromCards||data.health!=='not logged')tile.append(this.spChip(data.health));
    if(data.fromCards)this.spSummary(tile,data);
    else{const stuck=data.pods.filter(p=>p.state==='stuck').length;tile.append(this.el('p','sp-count',data.logged?data.pods.length+' pods, '+stuck+' logged stuck':'Pod count and stuck count not logged.'));}
    const bears=this.el('div','sp-pod-bears');for(const pod of data.pods){const b=this.button('','sp-pod-bear',()=>this.select('pod:'+which+'/'+encodeURIComponent(pod.id)));b.setAttribute('aria-label',pod.name+', '+pod.state);b.append(this.spCub(pod.state));bears.append(b)}tile.append(bears);if(!data.fromCards)tile.append(this.el('p','sp-now',data.now));else if(data.pods.length)tile.append(this.el('p','sp-count',data.pods.length+' pods'));grid.append(tile)}parent.append(grid);parent.append(this.el('p','sp-shelf','On the shelf: not logged.'));return grid;
  },
  spaces(main){
   this.heading(main,'YOUR SPACES.','Your calls, what Ted is on, and what comes next.');this.spTiles(this.paper(main));
  },
  space(main,which){
   if(!C.order.includes(which)){this.heading(main,'SPACE NOT LOGGED');const p=this.paper(main);p.append(this.button('Back to Spaces','',()=>this.select('spaces')));return}
   const surface=this.el('section','sp-space-surface');main.append(surface);main=surface;
   const data=this.spData(which);this.spSwitch(main,which);this.heading(main,C.names[which],data.now,'glass',text(data.ted_line,'No note logged for this line.'));
   const paper=this.paper(main);if(!data.fromCards||data.health!=='not logged')paper.append(this.spChip(data.health));paper.append(this.el('p','v3-keys','[ / ] next space · P pods · R roadmap · Esc inbox'));
   const layout=this.el('div','sp-layout'),body=this.el('div','sp-main'),side=this.el('aside','sp-side');
   const weekly=this.el('section','sp-weekly');this.spTitle(weekly,data.fromCards?'Current work':"Ted's weekly read");if(data.fromCards)this.spSummary(weekly,data);else weekly.append(this.el('p',null,data.weekly_read));body.append(weekly);const title=this.spTitle(body,'Pods');title.id='sp-pods-heading';title.tabIndex=-1;
   const grid=this.el('div','sp-pod-grid');if(!data.pods.length)grid.append(this.el('p','sp-muted','Pods not logged.'));
   for(const pod of data.pods){const row=this.el('article','sp-pod-card');row.append(this.spCub(pod.state,46));const copy=this.el('div');copy.append(this.button(pod.name,'sp-text-link',()=>this.select('pod:'+which+'/'+encodeURIComponent(pod.id))),this.el('p','sp-agent-name',text(typeof pod.agent==='object'?pod.agent.name:pod.agent)),this.el('p',null,pod.now),this.spChip(pod.state));row.append(copy);grid.append(row)}body.append(grid);this.spSide(side,which);layout.append(body,side);paper.append(layout);this.spSwipe(main,which);
  },
  spReviews(parent,reviews,approval){
   const entries=list(reviews).slice();if(approval&&typeof approval==='object')entries.push({...approval,reviewer:approval.reviewer||'Sebastian'});
   const grid=this.el('div','sp-review-grid');for(const review of entries){const row=this.el('article','sp-review');row.append(this.el('strong',null,text(review.reviewer||review.who||review.name)),this.spChip(review.verdict||review.status),this.el('p',null,text(review.note)),this.el('small',null,text(review.date||review.at)));grid.append(row)}
   if(!entries.length)grid.append(this.el('p','sp-muted','Review ledger not logged.'));
   if(!entries.some(r=>/^(you|sebastian)$/i.test(text(r.reviewer||r.who||r.name,'')))){const row=this.el('article','sp-review');row.append(this.el('strong',null,'Sebastian'),this.el('p',null,'Approval not logged.'));grid.append(row)}parent.append(grid);
  },
  spWork(parent,entries){
   const works=list(entries);if(!works.length){parent.append(this.el('p','sp-muted','Recent work not logged.'));return}
   for(const work of works){const row=this.el('article','sp-work');const status=typeof work.ok==='boolean'?(work.ok?'worked':'failed'):work.status||work.state;
    row.append(this.spChip(status),this.el('h3',null,text(work.title||work.name||work.t)),this.el('p',null,text(work.why||work.summary||work.w)),this.el('small',null,'Last run: '+text(work.date||work.at||work.last_run)+' · Model: '+text(work.model)));parent.append(row)}
  },
  pod(main,which,podId){
   const data=this.spData(which),pod=data.pods.find(p=>p.id===podId),name=pod?.name||podId||'Pod';this.spCrumbs(main,[['Spaces','spaces'],[C.names[which]||which,'space:'+which],[name]]);this.heading(main,name,text(pod?.now),'glass',text(pod?.ted_line,'No pod note logged.'));
   const paper=this.paper(main),layout=this.el('div','sp-layout'),body=this.el('div','sp-main'),side=this.el('aside','sp-side');body.append(this.spChip(pod?.state));this.spTitle(body,'Who sits in '+name);
   const seats=list(pod?.seats),agents=list(pod?.agents);if(!seats.length&&agents.length)for(const agent of agents)seats.push({...agent,staffed:true});if(!seats.length&&pod?.agent)seats.push(typeof pod.agent==='object'?{...pod.agent,staffed:true}:{name:pod.agent,id:pod.agent,staffed:true});
   const grid=this.el('div','sp-seat-grid');if(!seats.length)grid.append(this.el('p','sp-muted','Staffing not logged.'));for(const seat of seats){const row=this.el('article','sp-seat'+(seat.staffed===false?' sp-unfilled':''));const agentId=text(seat.id||seat.agent_id||seat.name,'');row.append(this.spCub(seat.state,34));const copy=this.el('div');if(seat.staffed===false)copy.append(this.el('strong',null,text(seat.name||seat.role)),this.el('p',null,'Not staffed.'));else{copy.append(this.button(text(seat.name||seat.agent,agentId||'Agent not logged'),'sp-text-link',()=>this.select('agent:'+which+'/'+encodeURIComponent(agentId))),this.el('p',null,text(seat.role)),this.el('small',null,'Last run: '+text(seat.last_run)));}row.append(copy);grid.append(row)}body.append(grid);
   this.spTitle(body,'Recent work');this.spWork(body,pod?.work||pod?.runs);this.spTitle(body,'Who checked');this.spReviews(body,pod?.reviews,pod?.approval);
   if(pod?.legacy){this.spTitle(body,'Latest pod pulse');body.append(this.el('p',null,'Updated: '+text(pod.last_update_at)));for(const [title,items]of [['Shipped in snapshot',pod.shipped_today],['Testing',pod.testing]]){body.append(this.el('h3',null,title));if(Array.isArray(items)&&items.length)for(const item of items)body.append(this.el('p',null,text(item)));else body.append(this.el('p','sp-muted','Not logged.'))}}
   this.spTitle(side,(C.names[which]||which)+' pods');for(const sibling of data.pods){const b=this.button(sibling.name,'sp-sibling',()=>this.select('pod:'+which+'/'+encodeURIComponent(sibling.id)));b.setAttribute('aria-current',sibling.id===podId?'page':'false');b.append(this.spChip(sibling.state));side.append(b)}layout.append(body,side);paper.append(layout);
  },
  agent(main,which,agentId){
   const data=this.spData(which);let found=null,pod=null;for(const p of data.pods){const agents=list(p.agents);if(p.agent)agents.push(typeof p.agent==='object'?p.agent:{id:p.agent,name:p.agent});found=agents.find(a=>String(a.id||a.agent_id||a.name)===agentId);if(found){pod=p;break}}if(!found)found=list(data.agents).find(a=>String(a.id||a.name)===agentId);const agent=found||{};
   const crumbs=[['Spaces','spaces'],[C.names[which]||which,'space:'+which]];if(pod)crumbs.push([pod.name,'pod:'+which+'/'+encodeURIComponent(pod.id)]);crumbs.push([text(agent.name,agentId||'Agent')]);this.spCrumbs(main,crumbs);this.heading(main,text(agent.name,agentId||'Agent'),text(agent.now),'glass',text(agent.ted_line,'No agent note logged.'));
   const paper=this.paper(main),layout=this.el('div','sp-layout'),body=this.el('div','sp-main'),side=this.el('aside','sp-side');body.append(this.spChip(agent.state));this.spTitle(body,'Last outputs, and who checked each');
   const outputs=list(agent.outputs||agent.outs);if(!outputs.length)body.append(this.el('p','sp-muted','Outputs not logged.'));for(const output of outputs){const row=this.el('article','sp-output');row.append(this.el('h3',null,text(output.title||output.name||output.t)),this.el('p',null,text(output.why||output.summary||output.w)));let url=null;try{const candidate=new URL(output.url||output.link);if(['https:','http:'].includes(candidate.protocol))url=candidate.href}catch{}if(url){const a=this.el('a','sp-output-link','Open output');a.href=url;a.target='_blank';a.rel='noopener noreferrer';row.append(a)}else row.append(this.el('small',null,'Output link not logged.'));this.spReviews(row,output.reviews,output.approval);body.append(row)}
   this.spTitle(body,'Runs');this.spWork(body,agent.runs);for(const [title,value]of [['Blocked on',Array.isArray(agent.blocked_on)?agent.blocked_on.join(', '):agent.blocked_on||agent.blocked],['Model',agent.model]]){this.spTitle(side,title);side.append(this.el('p',null,text(value)))}const asks=this.needs().filter(c=>this.lineOf(c)===which&&(c.agent===agentId||c.agent_id===agentId||Array.isArray(agent.card_ids)&&agent.card_ids.includes(c.id)));this.spYours(side,asks);layout.append(body,side);paper.append(layout);
  },
  spacesKeydown(e){const route=this.getState().project,match=/^(space|pod|agent):([^/]+)/.exec(route);if(!match)return false;const which=match[2];if(e.key==='Escape'){e.preventDefault();this.select('inbox');return true}if(e.key.toLowerCase()==='r'){e.preventDefault();this.select('roadmap:'+which);return true}if(e.key.toLowerCase()==='p'){e.preventDefault();if(match[1]!=='space')this.select('space:'+which);document.getElementById('sp-pods-heading')?.focus();return true}if(['[',']'].includes(e.key)&&match[1]==='space'){e.preventDefault();const at=C.order.indexOf(which);this.select('space:'+C.order[(at+(e.key===']'?1:-1)+C.order.length)%C.order.length]);return true}return false},
 });};
})();
