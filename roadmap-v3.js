'use strict';
(()=>{
 const lanes=['now','next','later','shipped'],labels={now:'Now',next:'Next',later:'Later',shipped:'Shipped'};
 const list=value=>Array.isArray(value)?value.filter(x=>x&&typeof x==='object'):[];
 const text=(value,fallback='not logged')=>typeof value==='string'&&value.trim()?value:typeof value==='number'?String(value):fallback;
 function normalize(which,snapshots){
  const matching=list(snapshots).filter(s=>s.kind==='roadmap'&&String(s.payload?.line||s.key).toLowerCase()===which),snapshot=matching.at(-1),source=snapshot?.payload||{},result={...source,logged:Boolean(snapshot),health:text(source.health),empty_copy:typeof source.empty_copy==='string'?{shipped:source.empty_copy}:source.empty_copy&&typeof source.empty_copy==='object'?source.empty_copy:{},explicit:{},unplaced:[],generated_at:snapshot?.generated_at};
  for(const lane of lanes){result[lane]=list(source[lane]);result.explicit[lane]=Array.isArray(source[lane])}
  if(Array.isArray(source.items)){for(const item of list(source.items)){const lane=item.lane||item.column;if(lanes.includes(lane))result[lane].push(item);else result.unplaced.push(item)}for(const lane of lanes)result.explicit[lane]=true}
  result.explicitlyEmpty=result.logged&&lanes.every(lane=>result.explicit[lane]&&result[lane].length===0)&&result.unplaced.length===0;
  return result;
 }
 window.RoadmapV3Data={normalize};
 window.installRoadmapV3=function(C){Object.assign(C.prototype,{
  roadData(which){return normalize(which,this.snapshots)},
  roadEmpty(data,lane,which){return text(data.empty_copy[lane],which==='dgc'&&lane==='shipped'&&data.explicitlyEmpty?'Nothing shipped. No PO, no confirmed drop.':data.explicit[lane]?'No items logged.':'Not logged.')},
  roadHealth(which,data){return data.health!=='not logged'?data.health:this.spData?.(which).health||'not logged'},
  roadChip(value){return this.spChip?this.spChip(value):this.el('span','v3-status',text(value))},
  roadCrumbs(main,which){if(this.spCrumbs)this.spCrumbs(main,[['Roadmap','roadmap'],[C.names[which]||which]]);else main.append(this.button('Roadmap / '+(C.names[which]||which),'v3-crumb',()=>this.select('roadmap')))},
  roadShelf(parent){
   const shelves=this.snapshots.filter(s=>s.kind==='roadmap').flatMap(s=>Array.isArray(s.payload?.shelf)?s.payload.shelf:[]).filter(x=>typeof x==='string');
   parent.append(this.el('p','rm-shelf',shelves.length?'On the shelf, no roadmap: '+[...new Set(shelves)].join(', ')+'.':'On the shelf: not logged.'));
  },
  roadWall(main){
   this.heading(main,'EVERY LINE. ONE WALL.',"Every line's roadmap sits on one wall. Now is the next two weeks, Next is two to eight weeks. Every item comes from that line's own records, and gaps say not logged.");
   const paper=this.paper(main),table=this.el('div','rm-wall');table.setAttribute('role','table');table.setAttribute('aria-label','Roadmaps by line');
   const head=this.el('div','rm-wall-row rm-wall-head');head.setAttribute('role','row');for(const title of ['Line','Now','Next','Later','Shipped']){const cell=this.el('div',null,title);cell.setAttribute('role','columnheader');head.append(cell)}table.append(head);
   for(const which of C.order){const data=this.roadData(which),row=this.el('div','rm-wall-row');row.setAttribute('role','row');row.dataset.line=which;if(this.roadSelectedLine===which)row.classList.add('rm-selected');
    const line=this.el('div','rm-line');line.setAttribute('role','rowheader');const open=this.button(C.names[which],'rm-line-button',()=>{this.roadSelectedLine=which;this.select('roadmap:'+which)});line.append(open,this.roadChip(this.roadHealth(which,data)));row.append(line);
    for(const lane of lanes){const cell=this.el('div','rm-wall-cell');cell.setAttribute('role','cell');const count=this.el('span','rm-count',data.explicit[lane]?String(data[lane].length):'?');count.setAttribute('aria-label',(data.explicit[lane]?data[lane].length:'Not logged')+' '+labels[lane]+' items');cell.append(this.el('strong','rm-lane-label',labels[lane]),count);
     const item=data[lane][0];cell.append(this.el('p',null,item?text(item.title||item.name):this.roadEmpty(data,lane,which)));if(item&&lane==='shipped')cell.append(this.el('small',null,'Shipped: '+text(item.date||item.shipped_at)));row.append(cell)}table.append(row)}paper.append(table);this.roadShelf(paper);
  },
  roadItem(item,lane){
   const card=this.getState().cards.find(c=>c.id===(item.card_id||item.approval_card_id)),needs=card?.section==='needs_you'||/waits? on you|waits? on your|needs.?you|awaiting.?approval/i.test(String(item.status||'')),row=this.el('article','rm-item'+(needs?' rm-waits':''));
   const title=this.el('h3',null,text(item.title||item.name));row.append(title);if(item.status)row.append(this.roadChip(item.status));else row.append(this.roadChip('Status not logged'));
   if(item.why||item.description)row.append(this.el('p',null,text(item.why||item.description)));if(lane==='shipped')row.append(this.el('small',null,'Shipped: '+text(item.date||item.shipped_at)));
   if(needs&&card){row.append(this.button('Open your call','',()=>{this.item=card.id;this.split='yours';this.select('inbox')}))}else if(needs)row.append(this.el('small',null,'Approval card not logged.'));
   return row;
  },
  roadmap(main,which){
   if(!which){this.roadWall(main);return}if(!C.order.includes(which)){this.heading(main,'ROADMAP NOT LOGGED');const paper=this.paper(main);paper.append(this.button('Back to Roadmap','',()=>this.select('roadmap')));return}
   const data=this.roadData(which);this.roadCrumbs(main,which);if(this.spSwitch)this.spSwitch(main,which,'roadmap');this.heading(main,C.names[which]+"'S ROADMAP",text(data.summary||data.now_sentence,'Now, Next, Later, and Shipped, from this line\'s own records.'),'flag',text(data.ted_line,'No roadmap note logged.'));
   const paper=this.paper(main);paper.append(this.roadChip(this.roadHealth(which,data)));const columns=this.el('div','rm-columns');
   for(const lane of lanes){const column=this.el('section','rm-column');column.dataset.lane=lane;const title=this.el('h2','rm-column-title',labels[lane]);title.append(this.el('span','rm-count',data.explicit[lane]?String(data[lane].length):'?'));column.append(title);if(!data[lane].length)column.append(this.el('p','rm-empty',this.roadEmpty(data,lane,which)));for(const item of data[lane])column.append(this.roadItem(item,lane));columns.append(column)}paper.append(columns);
   if(data.unplaced.length){const group=this.el('section','rm-unplaced');group.append(this.el('h2',null,'Lane not logged'));for(const item of data.unplaced)group.append(this.roadItem(item,''));paper.append(group)}
   paper.append(this.el('p','rm-shelf','Cards with a red shadow wait on you.'));this.roadShelf(paper);
  },
 });};
})();
