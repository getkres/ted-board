'use strict';
/* Private backend contract, NOT deployed here:
 * POST action:'stroke', mockup_id, frame_id, operation_id (UUID), tool
 * ('draw','arrow','box','text'), path (normalized M/L/Z data, never SVG markup),
 * color, crop:{x,y,width,height}, optional pin_id, and optional text_content.
 * Require page authentication, rate limits, same-image pin validation, atomic
 * receipt/routing, and operation_id deduplication. GET advertises strokes_enabled
 * only after those hooks exist. Success must return {ok:true,stroke:{id,...all
 * submitted fields}}. An absent, mismatched, or rejected acknowledgement keeps
 * the draft. Crop is normalized image bounds for the private worker to render.
 */
(()=>{
 const NS='http://www.w3.org/2000/svg',COLORS=['#c52b35','#1f6b4f','#181818'];
 const round=n=>Math.round(n*1e6)/1e6;
 const clamp=n=>{if(!Number.isFinite(n))throw Error('Coordinates must be finite');return round(Math.max(0,Math.min(1,n)))};
 function point(x,y,rect){if(!Number.isFinite(rect.width)||!Number.isFinite(rect.height)||rect.width<=0||rect.height<=0)throw Error('Image is not ready');return {x:clamp((x-rect.left)/rect.width),y:clamp((y-rect.top)/rect.height)}}
 function validPath(value){
  if(typeof value!=='string'||value.length>50000||!/^M\s/.test(value))return false;
  const tokens=value.trim().split(/\s+/);let cursor=0,points=0;
  while(cursor<tokens.length){const command=tokens[cursor++];if(command==='Z')continue;if(!['M','L'].includes(command))return false;for(let i=0;i<2;i++){const token=tokens[cursor++];if(!/^(?:0(?:\.\d{1,6})?|1(?:\.0{1,6})?)$/.test(token||''))return false;const number=Number(token);if(!Number.isFinite(number)||number<0||number>1)return false}points++}return points>0;
 }
 const command=(name,p)=>name+' '+p.x+' '+p.y;
 function stroke(tool,points,color=COLORS[0],content=''){
  if(!['Draw','Arrow','Box','Text'].includes(tool)||!COLORS.includes(color)||!Array.isArray(points)||!points.length||points.length>1000)throw Error('Invalid stroke');
  const p=points.map(p=>({x:clamp(p.x),y:clamp(p.y)})),a=p[0],b=p.at(-1);let path;
  if(tool==='Box'){path=[command('M',a),command('L',{x:b.x,y:a.y}),command('L',b),command('L',{x:a.x,y:b.y}),'Z'].join(' ')}
  else if(tool==='Arrow'){const angle=Math.atan2(b.y-a.y,b.x-a.x),length=Math.min(.04,Math.hypot(b.x-a.x,b.y-a.y)*.3),wing=delta=>({x:clamp(b.x-length*Math.cos(angle+delta)),y:clamp(b.y-length*Math.sin(angle+delta))});const c=wing(.55),d=wing(-.55);p.push(c,d);path=[command('M',a),command('L',b),command('M',c),command('L',b),command('L',d)].join(' ')}
  else path=p.map((p,i)=>command(i?'L':'M',p)).join(' ');
  const crop={x:clamp(Math.min(...p.map(p=>p.x))-.025),y:clamp(Math.min(...p.map(p=>p.y))-.025)},right=clamp(Math.max(...p.map(p=>p.x))+.025),bottom=clamp(Math.max(...p.map(p=>p.y))+.025);
  crop.width=round(right-crop.x);crop.height=round(bottom-crop.y);
  if(tool==='Text'){if(typeof content!=='string'||!content.trim()||content.length>1200)throw Error('Enter text before placing it');crop.width=round(Math.min(1-crop.x,Math.max(crop.width,.035*Math.min(25,content.length))));crop.height=round(Math.min(1-crop.y,Math.max(.07,crop.height)))}
  if(!validPath(path))throw Error('Invalid path');return {tool:tool.toLowerCase(),path,color,crop,...(tool==='Text'?{text_content:content.trim()}:{})};
 }
 window.MarkupV3Data={point,stroke,validPath};
 window.installMarkupV3=function(C){
  if(C.prototype.markupInstalled)return;const original={};for(const method of ['open','close','reset','installPointers','drawPins','applyTransform'])original[method]=C.prototype[method];
  const svg=(name,attrs={})=>{const node=document.createElementNS(NS,name);for(const [key,value]of Object.entries(attrs))node.setAttribute(key,String(value));return node};
  Object.assign(C.prototype,{
   markupInstalled:true,
   markupEnsureOwner(){const owner=this.getKey();if(this.markupOwner!==owner){this.markupOwner=owner;this.markupEpoch=(this.markupEpoch||0)+1;this.markupDrafts=new Map();this.markupSaved=new Map();this.markupSaving=new Set();this.markupTextContent=''}this.markupDrafts||=new Map();this.markupSaved||=new Map();this.markupSaving||=new Set()},
   markupFrame(m=this.active){return m?String(m.id)+'/'+String(m.frame_id||m.id):''},
   markupCurrentDrafts(){return this.markupDrafts?.get(this.markupFrame())||[]},
   markupCancelGesture(){clearTimeout(this.markupLongPress);this.markupGesture=null;this.markupPreview=null;this.markupTouchPoints?.clear()},
   open(m,pinId=null){this.markupEnsureOwner();this.markupCancelGesture();this.markupTool='Pan';this.markupColor||=COLORS[0];const result=original.open.call(this,m,pinId);this.dialog.classList.add('mkup-dialog');this.installMarkupTools();this.paintMarkup();return result},
   close(){this.markupCancelGesture();return original.close.call(this)},
   reset(){this.markupCancelGesture();this.markupEpoch=(this.markupEpoch||0)+1;this.markupOwner=null;this.markupDrafts?.clear();this.markupSaved?.clear();this.markupSaving?.clear();this.markupTextContent='';return original.reset.call(this)},
   setMarkupTool(tool){if(!['Pan','Pin','Draw','Arrow','Box','Text'].includes(tool))return;this.markupCancelGesture();this.markupTool=tool;this.pinMode=tool==='Pin';this.viewport?.setAttribute('data-markup-tool',tool.toLowerCase());this.updateMarkupTools();this.paintMarkup();if(tool==='Text')this.markupTextInput?.focus()},
   installMarkupTools(){
    const bar=this.el('section','mkup-tools');bar.setAttribute('aria-label','Markup tools');const tools=this.el('div','mkup-tool-buttons');
    for(const tool of ['Pin','Draw','Arrow','Box','Text']){const b=this.button(tool,'',()=>this.setMarkupTool(tool));b.dataset.markupTool=tool;b.setAttribute('aria-pressed','false');tools.append(b)}
    tools.append(this.button('Pan','',()=>this.setMarkupTool('Pan')));bar.append(tools);const controls=this.el('div','mkup-controls');
    for(const [i,color]of COLORS.entries()){const b=this.button('','mkup-color',()=>{this.markupColor=color;this.updateMarkupTools()});b.style.setProperty('--markup-color',color);b.dataset.color=color;b.setAttribute('aria-label',['Red ink','Green ink','Black ink'][i]);controls.append(b)}
    this.markupUndoButton=this.button('Undo','',()=>this.undoMarkup());this.markupSaveButton=this.button('Save markup','primary',()=>this.saveMarkup());controls.append(this.markupUndoButton,this.markupSaveButton);bar.append(controls);
    const label=this.el('label','mkup-text-label','Text to place '),input=this.el('input','mkup-text-input');input.type='text';input.maxLength=1200;input.value=this.markupTextContent||'';input.setAttribute('aria-label','Text to place');input.oninput=()=>this.markupTextContent=input.value;label.append(input);bar.append(label);this.markupTextInput=input;this.markupTextLabel=label;
    this.markupStatus=this.el('p','mkup-status');this.markupStatus.setAttribute('role','status');bar.append(this.markupStatus);this.markupToolbar=bar;this.dialog.querySelector('.mockup-tools').after(bar);this.updateMarkupTools();
   },
   updateMarkupTools(){
    if(!this.markupToolbar)return;const count=this.markupCurrentDrafts().length,saving=this.markupSaving?.has(this.markupFrame());
    this.markupToolbar.querySelectorAll('[data-markup-tool]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.markupTool===this.markupTool)));this.markupToolbar.querySelectorAll('[data-color]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.color===this.markupColor)));
    this.markupUndoButton.disabled=!count||saving;this.markupSaveButton.disabled=!count||saving||this.capabilities?.strokes!==true;this.markupSaveButton.title=this.capabilities?.strokes?'Save normalized feedback':'Waiting for reviewed backend support';this.markupTextLabel.hidden=this.markupTool!=='Text';
    this.markupStatus.textContent=(saving?'Saving. ':count?count+' draft '+(count===1?'stroke. ':'strokes. '):'No draft strokes. ')+(this.capabilities?.strokes?'Drafts stay here until a save is confirmed.':'Drawing stays local until the reviewed backend update. Pins still use existing feedback.')+' Two fingers pan and pinch to zoom.';
   },
   markupAddStroke(tool,points){
    if(!this.active||this.active.status==='archived'||this.verdict(this.active)==='scrapped')return;this.markupEnsureOwner();const value=stroke(tool,points,this.markupColor||COLORS[0],this.markupTextContent||''),frame=this.markupFrame(),draft={...value,operation_id:crypto.randomUUID(),mockup_id:this.active.id,frame_id:String(this.active.frame_id||this.active.id)};
    if(this.selected&&this.imagePins(this.active.id).some(p=>p.id===this.selected))draft.pin_id=this.selected;
    const drafts=this.markupDrafts.get(frame)||[];if(drafts.length>=100)throw Error('Save or undo a draft before adding more');drafts.push(draft);this.markupDrafts.set(frame,drafts);this.paintMarkup();this.updateMarkupTools();return draft;
   },
   undoMarkup(){const frame=this.markupFrame();if(this.markupSaving?.has(frame))return;const drafts=this.markupDrafts?.get(frame);if(drafts?.length){drafts.pop();this.paintMarkup();this.updateMarkupTools()}},
   async saveMarkup(){
    if(!this.active||this.capabilities?.strokes!==true){this.notify('Markup is a local draft until the reviewed backend update.',true);return false}
    this.markupEnsureOwner();const frame=this.markupFrame(),owner=this.getKey(),epoch=this.markupEpoch;if(this.markupSaving.has(frame))return false;const pending=this.markupCurrentDrafts().slice();if(!pending.length)return false;this.markupSaving.add(frame);this.updateMarkupTools();
    try{for(const draft of pending){if(owner!==this.getKey()||epoch!==this.markupEpoch)return false;const result=await this.api('POST',{action:'stroke',...draft});if(owner!==this.getKey()||epoch!==this.markupEpoch)return false;
      const ack=result.stroke;if(result.ok!==true||!ack||typeof ack.id!=='string'||!ack.id||['mockup_id','frame_id','operation_id','path','tool','color','pin_id','text_content'].some(key=>ack[key]!==draft[key])||['x','y','width','height'].some(key=>ack.crop?.[key]!==draft.crop[key]))throw Error('Markup was not confirmed. Your draft is retained.');
      const remaining=this.markupDrafts.get(frame)||[];this.markupDrafts.set(frame,remaining.filter(d=>d.operation_id!==draft.operation_id));const saved=this.markupSaved.get(frame)||[];saved.push({...draft,id:ack.id});this.markupSaved.set(frame,saved);
     }if(owner===this.getKey()&&epoch===this.markupEpoch)this.notify('Markup saved.');return true;
    }catch(error){if(owner===this.getKey()&&epoch===this.markupEpoch)this.notify(error.message||'Could not save markup. Your draft is retained.',true);return false}
    finally{if(owner===this.getKey()&&epoch===this.markupEpoch){this.markupSaving.delete(frame);this.paintMarkup();this.updateMarkupTools()}}
   },
   drawPins(){const result=original.drawPins.call(this);this.paintMarkup();return result},
   applyTransform(){const result=original.applyTransform.call(this);this.paintMarkup();return result},
   paintMarkup(){
    if(!this.active||!this.canvas)return;this.canvas.querySelector('.mkup-overlay')?.remove();const overlay=svg('svg',{class:'mkup-overlay',viewBox:'0 0 1 1',preserveAspectRatio:'none','aria-hidden':'true'});
    const known=[...(Array.isArray(this.active.strokes)?this.active.strokes:[]),...(this.markupSaved?.get(this.markupFrame())||[])],drafts=this.markupCurrentDrafts(),rows=[...known,...drafts,...(this.markupPreview?[this.markupPreview]:[])];
    for(const row of rows){const path=row.path||row.svg_path;if(!validPath(path)||!COLORS.includes(row.color))continue;const attrs={d:path,fill:'none',stroke:row.color,'stroke-width':2.5,'vector-effect':'non-scaling-stroke','stroke-linecap':'round','stroke-linejoin':'round'};if(drafts.includes(row))attrs['stroke-dasharray']='6 3';overlay.append(svg('path',attrs));if(row.tool==='text'&&typeof row.text_content==='string'){const numbers=path.match(/\d+(?:\.\d+)?/g),content=row.text_content.slice(0,1200),lines=content.match(/[\s\S]{1,22}/g)||[''],font=Math.min(.035,.9/(lines.length*1.25)),x=clamp(Math.min(Number(numbers[0]),1-22*font*.65-.015)),y=clamp(Math.min(Number(numbers[1]),1-lines.length*font*1.25-.015)),label=svg('text',{fill:row.color,'font-size':font,'font-family':'Archivo, sans-serif','font-weight':700});lines.forEach((line,i)=>{const part=svg('tspan',{x,y:y+font*(1+i*1.25)});part.textContent=line;label.append(part)});overlay.append(label)}}
    const rect=this.canvas.getBoundingClientRect(),pins=[...this.imagePins(this.active.id),...(this.pending?[this.pending]:[])],buttons=this.canvas.querySelectorAll('.mockup-pin');
    pins.forEach((pin,i)=>{const button=buttons[i],x=Number(pin.x??pin.x_pct/100),y=Number(pin.y??pin.y_pct/100);if(!button||!Number.isFinite(x)||!Number.isFinite(y)||!rect.width||!rect.height)return;const dx=x>.7?-30:30,dy=y<.15?30:-30,px=clamp(x+dx/rect.width),py=clamp(y+dy/rect.height);button.style.left=px*100+'%';button.style.top=py*100+'%';overlay.append(svg('line',{x1:x,y1:y,x2:px,y2:py,stroke:'#181818','stroke-width':1.5,'vector-effect':'non-scaling-stroke'}),svg('circle',{cx:x,cy:y,r:.004,fill:'#c52b35'}))});
    this.canvas.append(overlay);
   },
   installPointers(){
    const viewport=this.viewport,points=new Map();this.markupTouchPoints=points;let multi=false,replay=false;
    const inside=e=>{const r=this.canvas.getBoundingClientRect();return r.width>0&&r.height>0&&e.clientX>=r.left&&e.clientX<=r.right&&e.clientY>=r.top&&e.clientY<=r.bottom};
    const normalized=e=>point(e.clientX,e.clientY,this.canvas.getBoundingClientRect());
    const cancelLong=()=>{clearTimeout(this.markupLongPress);this.markupLongPress=null};
    const preview=()=>{const g=this.markupGesture;if(!g)return;try{this.markupPreview=stroke(g.tool,g.points,this.markupColor,this.markupTextContent||'');this.paintMarkup()}catch{}};
    viewport.addEventListener('pointerdown',e=>{
     if(replay||e.button>0||e.target.closest('button'))return;points.set(e.pointerId,{x:e.clientX,y:e.clientY,pointerType:e.pointerType});
     if(points.size>=2){cancelLong();this.markupGesture=null;this.markupPreview=null;multi=true;this.paintMarkup();for(const [pointerId,p]of points){if(pointerId!==e.pointerId&&!this.pointers.has(pointerId)){replay=true;viewport.dispatchEvent(new PointerEvent('pointerdown',{pointerId,clientX:p.x,clientY:p.y,pointerType:p.pointerType,bubbles:true,button:0}));replay=false}}return}
     multi=false;const tool=this.markupTool||'Pan';
     if(['Draw','Arrow','Box','Text'].includes(tool)&&inside(e)){e.preventDefault();e.stopImmediatePropagation();this.markupGesture={pointerId:e.pointerId,tool,points:[normalized(e)]};try{viewport.setPointerCapture(e.pointerId)}catch{}preview();return}
     if(tool==='Pin'&&e.pointerType!=='mouse'&&inside(e)){const start={x:e.clientX,y:e.clientY},owner=this.getKey(),frame=this.markupFrame();this.markupLongPress=setTimeout(()=>{if(points.size!==1||!points.has(e.pointerId)||owner!==this.getKey()||frame!==this.markupFrame())return;const current=points.get(e.pointerId);if(Math.hypot(current.x-start.x,current.y-start.y)>8)return;if(this.gesture)this.gesture.moved=true;clearTimeout(this.tapTimer);const p=normalized({clientX:start.x,clientY:start.y});this.newPin(p.x,p.y)},550)}
    },true);
    viewport.addEventListener('pointermove',e=>{
     if(!points.has(e.pointerId))return;const previous=points.get(e.pointerId);if(Math.hypot(e.clientX-previous.x,e.clientY-previous.y)>8)cancelLong();points.set(e.pointerId,{x:e.clientX,y:e.clientY,pointerType:e.pointerType});const g=this.markupGesture;
     if(!g||multi||points.size>=2)return;e.preventDefault();e.stopImmediatePropagation();const p=normalized(e);if(g.points.length<999)g.points.push(p);else g.points[g.points.length-1]=p;preview();
    },true);
    const finish=(e,cancel=false)=>{cancelLong();const g=this.markupGesture,wasDraw=g&&g.pointerId===e.pointerId&&!multi;points.delete(e.pointerId);if(wasDraw){e.preventDefault();e.stopImmediatePropagation();this.markupGesture=null;this.markupPreview=null;if(!cancel){try{g.points.push(normalized(e));this.markupAddStroke(g.tool,g.points)}catch(error){this.notify(error.message,true)}}this.paintMarkup()}if(!points.size)multi=false};
    viewport.addEventListener('pointerup',e=>finish(e),true);viewport.addEventListener('pointercancel',e=>finish(e,true),true);viewport.addEventListener('lostpointercapture',e=>finish(e,true),true);
    viewport.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'&&!e.target.closest('input,textarea')){e.preventDefault();e.stopPropagation();this.undoMarkup()}});
    return original.installPointers.call(this);
   },
  });
 };
})();
