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
 reset(){this.generation=(this.generation||0)+1;this.snapshots=[];this.capabilities={};this.split='yours';this.item=null;this.focusIndex=0;}
 accept(data){this.capabilities=data.capabilities||{};if(Array.isArray(data.snapshots))this.snapshots=data.snapshots;}
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
 feed(kind){return this.snapshots.filter(s=>s.kind===kind).flatMap(s=>{const p=s.payload;return Array.isArray(p)?p:Array.isArray(p?.items)?p.items:p?[{...p,key:s.key,generated_at:s.generated_at}]:[]});}
 heading(parent,title,description='',prop='stamp',line=''){
  const hero=this.el('section','v3-hero'),text=this.el('div','v3-hero-copy');text.append(this.el('h1','v3-headline',title));if(description)text.append(this.el('p','v3-sub',description));hero.append(text);if(line)hero.append(this.say(line,prop));parent.append(hero);return hero;
 }
 say(line,prop='stamp'){const box=this.el('div','v3-ted');box.append(this.el('p','v3-bubble',line));const art=this.el('div','v3-bear');art.innerHTML=TedTheme.bear(130,{prop});box.append(art);return box;}
 paper(parent){const p=this.el('section','v3-paper');parent.append(p);return p;}
 empty(parent,text='Not logged.'){parent.append(this.el('p','v3-empty',text));}
 tools(parent){const details=this.el('details','v3-tools'),summary=this.el('summary',null,'Rules, sprint, batches, and jobs');details.append(summary);const row=this.el('div','v3-actions');for(const name of ['Veto','Rules','Sprint','Batches'])row.append(this.button(name,'',()=>controlCenter.open(name)));row.append(this.button('Jobs','',()=>this.select('Jobs')));details.append(row);parent.append(details);}
 render(main,route){
  if(!['inbox','spaces','roadmap'].includes(route)&&!route.includes(':'))return false;
  main.classList.add('v3');
  if(ControlCenterV3.isMockups(route)){this.mockups.render(main);return true;}
  this.heading(main,route==='inbox'?'NEED YOU':route==='spaces'?'TEN LINES. ONE BOARD.':route.toUpperCase(),'Your calls, what Ted is on, and what comes next.','stamp','The board is open. Your calls stay yours.');
  const p=this.paper(main);if(route==='inbox'){const cards=this.getState().cards.filter(c=>c.section==='needs_you');if(!cards.length)this.empty(p,'Nothing on you right now.');cards.forEach(c=>p.append(this.renderCard(c)));this.tools(p);}else this.empty(p,'Not logged. This view is waiting for its live feed.');return true;
 }
}
