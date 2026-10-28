"use strict";
// Glass sky: the night or day sky, the Sky switch, and Still sky.
// Runs in the head so the saved sky paints first; the controls join the masthead once the board is built.
(()=>{
const SKY_KEY='ted-sky', STILL_KEY='ted-sky-still', root=document.documentElement;
const memory=new Map();
const read=k=>{if(memory.has(k))return memory.get(k);try{return localStorage.getItem(k)}catch{return null}};
const write=(k,v)=>{memory.set(k,v);try{localStorage.setItem(k,v)}catch{}};
const darkQuery=matchMedia('(prefers-color-scheme: dark)'), calmQuery=matchMedia('(prefers-reduced-motion: reduce)');
// Painted star positions in assets/sky/night.webp: x and y percent of the 2880 by 1920 painting, then local brightness. 68 of its 823 stars, about 1 in 12.
const STARS=[[47.569,13.438,221],[17.604,10.469,220],[87.361,33.021,210],[45.139,36.51,210],[41.667,46.771,209],[75.938,32.969,208],[50.972,44.844,206],[35.312,62.76,204],[8.125,65.156,204],[41.528,69.167,201],[68.507,49.427,197],[25.868,69.635,195],[94.653,34.375,192],[91.424,17.865,190],[64.792,46.51,188],[54.688,43.177,177],[89.097,67.917,176],[70.66,40.0,175],[71.146,43.698,175],[20.174,9.844,170],[69.792,5.0,168],[34.826,40.365,167],[83.507,41.354,167],[16.111,52.708,164],[57.674,33.594,163],[47.917,60.208,162],[29.549,71.979,154],[57.604,18.958,153],[61.944,48.021,153],[48.194,49.427,151],[28.715,61.354,151],[58.576,59.323,144],[18.16,74.479,142],[26.771,13.177,141],[17.639,71.094,138],[4.132,70.521,134],[89.028,11.875,126],[97.986,62.865,123],[37.188,63.594,120],[9.583,19.531,117],[46.84,25.417,117],[20.139,16.823,108],[44.965,19.427,107],[9.653,18.438,106],[81.632,30.938,106],[99.201,52.24,87],[34.097,67.656,84],[88.16,39.115,83],[67.257,45.99,82],[26.493,47.344,82],[29.722,77.552,82],[92.049,71.927,80],[42.188,60.208,79],[32.535,10.938,78],[46.076,17.865,78],[88.299,33.698,76],[3.611,74.167,74],[30.66,28.594,73],[81.042,32.708,73],[85.833,20.26,71],[76.111,31.042,70],[35.382,61.979,70],[30.035,24.896,67],[80.903,39.115,62],[96.701,79.323,61],[59.896,73.542,60],[48.646,58.229,58],[39.861,70.885,56]];
const ART_W=2880, ART_H=1920;
const preferred=()=>read(SKY_KEY)==='day'||read(SKY_KEY)==='night'?read(SKY_KEY):darkQuery.matches?'night':'day';
const isStill=()=>calmQuery.matches||read(STILL_KEY)==='1';
let mode=preferred(), radios=[], stillButton=null, layer=null, stars=null;
function paint(){
 root.dataset.sky=mode;
 root.dataset.theme=mode==='day'?'light':'dark';
 root.classList.toggle('sky-still',isStill());
 for(const meta of document.querySelectorAll('meta[name=theme-color]'))meta.content=mode==='day'?'#1667a0':'#0b1230';
 for(const radio of radios){const on=radio.dataset.sky===mode;radio.setAttribute('aria-checked',String(on));radio.tabIndex=on?0:-1;}
 if(stillButton){stillButton.setAttribute('aria-pressed',String(isStill()));stillButton.disabled=calmQuery.matches;stillButton.title=calmQuery.matches?'Your system asks for reduced motion, so the sky stays still.':'';}
}
function choose(next,focus){
 if(next!==mode){mode=next;write(SKY_KEY,mode);paint();}
 if(focus)radios.find(r=>r.dataset.sky===mode)?.focus();
}
// Twinkle dots follow the painting under background-size:cover, so each one sits on a painted star.
function placeStars(){
 if(!stars)return;
 const w=innerWidth,h=innerHeight,scale=Math.max(w/ART_W,h/ART_H),ox=(w-ART_W*scale)/2,oy=(h-ART_H*scale)/2;
 for(const dot of stars.children){dot.style.left=(ox+Number(dot.dataset.x)/100*ART_W*scale)+'px';dot.style.top=(oy+Number(dot.dataset.y)/100*ART_H*scale)+'px';}
}
function buildSky(){
 layer=document.createElement('div');layer.className='sky-layer';layer.setAttribute('aria-hidden','true');
 const night=document.createElement('div');night.className='sky-art sky-night';
 const day=document.createElement('div');day.className='sky-art sky-day';
 stars=document.createElement('div');stars.className='sky-stars';
 STARS.forEach(([x,y,lift],i)=>{const dot=document.createElement('i');dot.dataset.x=x;dot.dataset.y=y;
  // Never in sync: 4 to 9 second cycles, 15 to 35 percent lift, staggered starts.
  const period=4+((i*37)%50)/10, amp=.15+((i*53)%21)/100;
  dot.style.setProperty('--period',period+'s');dot.style.setProperty('--delay',(-((i*71)%90)/10)+'s');dot.style.setProperty('--lift',String(Math.min(.35,amp+(lift>150?.04:0))));
  stars.append(dot);});
 night.append(stars);layer.append(night,day);document.body.prepend(layer);placeStars();
 addEventListener('resize',placeStars,{passive:true});
}
function buildControls(){
 const host=document.querySelector('.ted-controls')||document.querySelector('.masthead');
 if(!host||document.querySelector('.sky-controls'))return;
 const wrap=document.createElement('div');wrap.className='sky-controls';
 // Native button activation remains intact, but global card and Mockups shortcuts must not run here.
 wrap.addEventListener('keydown',e=>{if(!e.metaKey&&!e.ctrlKey&&!e.altKey)e.stopPropagation();});
 const group=document.createElement('div');group.className='sky-switch';group.setAttribute('role','radiogroup');group.setAttribute('aria-label','Sky');
 radios=[['night','Night','☾'],['day','Day','☀']].map(([value,label,icon])=>{
  const b=document.createElement('button');b.type='button';b.setAttribute('role','radio');b.dataset.sky=value;
  const glyph=document.createElement('span');glyph.className='sky-icon';glyph.setAttribute('aria-hidden','true');glyph.textContent=icon;
  b.append(glyph,document.createTextNode(label));b.addEventListener('click',()=>choose(value,false));group.append(b);return b;});
 group.addEventListener('keydown',e=>{
  const order=['night','day'],step={ArrowRight:1,ArrowDown:1,ArrowLeft:-1,ArrowUp:-1}[e.key];
  if(e.key==='Home'||e.key==='End'){e.preventDefault();choose(e.key==='Home'?'night':'day',true);return;}
  if(!step)return;e.preventDefault();e.stopPropagation();choose(order[(order.indexOf(mode)+step+2)%2],true);});
 stillButton=document.createElement('button');stillButton.type='button';stillButton.className='sky-still-toggle';stillButton.textContent='Still sky';
 stillButton.addEventListener('click',()=>{write(STILL_KEY,isStill()?'0':'1');paint();});
 wrap.append(group,stillButton);host.append(wrap);paint();
}
paint();
const watch=(query,fn)=>query.addEventListener?query.addEventListener('change',fn):query.addListener(fn);
watch(darkQuery,()=>{if(read(SKY_KEY)===null){mode=preferred();paint();}});
watch(calmQuery,paint);
addEventListener('storage',e=>{if(e.key===null||e.key===SKY_KEY||e.key===STILL_KEY){if(e.key===null)memory.clear();else if(e.newValue===null)memory.delete(e.key);else memory.set(e.key,e.newValue);mode=preferred();paint();}});
const ready=()=>{buildSky();buildControls();};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ready,{once:true});else ready();
window.TedSky={mode:()=>mode,set:next=>choose(next,false),still:isStill};
})();
