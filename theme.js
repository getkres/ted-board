"use strict";
(()=>{
// Static copy describes controls only. Operational status belongs to authenticated data.
const LINES = {
 decided: "Review the recorded calls, and veto a proposal from its controls.",
 routines: "Open a routine to read its recorded status and output.",
 roadmap: "Now, next, later, and shipped, as recorded in the roadmap.",
 mk: "Open a batch to review its frames.",
 round: "Choose a direction, and record why it works.",
 cmp: "Compare the versions, then review the selected frame.",
 mkup: "Draw or pin the change you want to explain.",
 triage: "Right for good, left for needs work, or up to scrap.",
};
const bearBase = function(size=120, opts={}){
 const fur=opts.fur||'#7a4e2d', belly=opts.belly||'#e9c49a', lamp=opts.lamp!==false;
 const arm = opts.pose==='wave'
  ? `<path d="M128 112 q22 -26 30 -48" stroke="${fur}" stroke-width="18" stroke-linecap="round" fill="none"/><circle cx="160" cy="60" r="11" fill="${fur}"/>`
  : `<path d="M126 120 q18 10 22 30" stroke="${fur}" stroke-width="18" stroke-linecap="round" fill="none"/>`;
 const prop = opts.prop||'';
 return `<svg class="bear" width="${size}" height="${size*1.05}" viewBox="0 0 180 190" aria-hidden="true">
  <ellipse cx="90" cy="178" rx="56" ry="9" fill="rgba(0,0,0,.12)"/>
  <ellipse cx="90" cy="138" rx="50" ry="44" fill="${fur}"/>
  <ellipse cx="90" cy="146" rx="31" ry="30" fill="${belly}"/>
  <path d="M54 120 q-18 10 -22 30" stroke="${fur}" stroke-width="18" stroke-linecap="round" fill="none"/>
  ${arm}
  <ellipse cx="66" cy="178" rx="15" ry="9" fill="${fur}"/><ellipse cx="114" cy="178" rx="15" ry="9" fill="${fur}"/>
  <circle cx="46" cy="40" r="17" fill="${fur}"/><circle cx="46" cy="40" r="8" fill="${belly}"/>
  <circle cx="134" cy="40" r="17" fill="${fur}"/><circle cx="134" cy="40" r="8" fill="${belly}"/>
  <circle cx="90" cy="70" r="46" fill="${fur}"/>
  ${lamp?`<rect x="52" y="34" width="76" height="9" rx="4.5" fill="#2b2b3a"/><circle cx="90" cy="36" r="10" fill="#fff3a8" stroke="#2b2b3a" stroke-width="4"/><circle cx="90" cy="36" r="4" fill="#fff"/>`:''}
  <ellipse cx="90" cy="88" rx="22" ry="17" fill="${belly}"/>
  <ellipse cx="90" cy="80" rx="8" ry="6" fill="#2b1a10"/>
  <path d="M84 92 q6 6 12 0" stroke="#2b1a10" stroke-width="3" fill="none" stroke-linecap="round"/>
  <circle cx="72" cy="64" r="5.5" fill="#2b1a10"/><circle cx="108" cy="64" r="5.5" fill="#2b1a10"/>
  <circle cx="74" cy="62" r="1.8" fill="#fff"/><circle cx="110" cy="62" r="1.8" fill="#fff"/>
  <ellipse cx="62" cy="80" rx="8" ry="5" fill="#ff8fa3" opacity=".55"/><ellipse cx="118" cy="80" rx="8" ry="5" fill="#ff8fa3" opacity=".55"/>
  ${prop}
 </svg>`;
};
const cubBase = (st, size=30, letter='') => { const c=({moving:'#ffffff',waiting:'#9a9a9a',stuck:'#e2402a'})[st]||'#ffffff'; return `<svg width="${size}" height="${size}" viewBox="0 0 40 40" style="flex:none;overflow:visible" aria-hidden="true">
 <circle cx="10" cy="12" r="6" fill="#7a4e2d"/><circle cx="30" cy="12" r="6" fill="#7a4e2d"/><circle cx="10" cy="12" r="2.6" fill="#e9c49a"/><circle cx="30" cy="12" r="2.6" fill="#e9c49a"/>
 <circle cx="20" cy="22" r="15" fill="#7a4e2d"/>
 <path d="M6.5 15 Q20 2 33.5 15 Z" fill="${c}" stroke="#2b2b3a" stroke-width="1.6"/><circle cx="20" cy="10.5" r="3" fill="#fff3a8" stroke="#2b2b3a" stroke-width="1.4"/>
 <ellipse cx="20" cy="27" rx="7" ry="5.5" fill="#e9c49a"/><ellipse cx="20" cy="24.5" rx="2.6" ry="2" fill="#2b1a10"/>
 <circle cx="14.5" cy="20" r="1.8" fill="#2b1a10"/><circle cx="25.5" cy="20" r="1.8" fill="#2b1a10"/>
 ${st==='stuck'?'<path d="M16.5 30.5 q3.5 -2.4 7 0" stroke="#2b1a10" stroke-width="1.3" fill="none" stroke-linecap="round"/>':'<path d="M17 29.5 q3 2.4 6 0" stroke="#2b1a10" stroke-width="1.3" fill="none" stroke-linecap="round"/>'}
 ${letter?`<text x="20" y="44" text-anchor="middle" font-family="Avenir Next" font-weight="700" font-size="9" fill="#2b2b3a">${letter}</text>`:''}
</svg>`; };
const PROPS = {
 stamp: `<g transform="translate(150 6) rotate(18)"><rect x="6" y="-10" width="10" height="26" rx="3" fill="#111"/><circle cx="11" cy="-12" r="9" fill="#111"/><rect x="-6" y="14" width="34" height="14" fill="#e2402a" stroke="#111" stroke-width="3"/></g>`,
 sign: (t) => `<g transform="translate(160 -34)"><path d="M0 34 V100" stroke="#111" stroke-width="6"/><rect x="-34" y="-6" width="68" height="40" fill="#e2402a" stroke="#111" stroke-width="4"/><text x="0" y="23" text-anchor="middle" font-family="Archivo" font-weight="900" font-stretch="62%" font-size="22" fill="#fff">${t}</text></g>`,
 glass: `<g transform="translate(150 10) rotate(-25)"><circle cx="18" cy="0" r="17" fill="#fff" stroke="#111" stroke-width="6"/><path d="M18 17 V48" stroke="#111" stroke-width="8" stroke-linecap="round"/><path d="M10 -6 q6 -6 12 -2" stroke="#e2402a" stroke-width="3" fill="none"/></g>`,
 flag: `<g transform="translate(160 -40)"><path d="M0 0 V104" stroke="#111" stroke-width="6"/><path d="M3 2 H52 L42 16 L52 30 H3 Z" fill="#e2402a" stroke="#111" stroke-width="4"/></g>`,
 marker: `<g transform="translate(148 -4) rotate(28)"><rect x="0" y="0" width="14" height="52" rx="3" fill="#e2402a" stroke="#111" stroke-width="3"/><path d="M2 52 L7 66 L12 52 Z" fill="#111"/><rect x="0" y="0" width="14" height="12" fill="#111"/></g>`,
};

// The take A art uses the same black, white, and red as the poster.
const recolor = svg => svg.replaceAll('#7a4e2d','#111111').replaceAll('#e9c49a','#ffffff').replaceAll('#fff3a8','#e2402a').replaceAll('#ff8fa3','#e2402a').replaceAll('#2b1a10','#111111').replaceAll('#2b2b3a','#111111').replaceAll('rgba(0,0,0,.12)','none');
window.TedTheme = {
 lines: LINES,
 bear(size=120,{prop='stamp'}={}) { const art=prop.startsWith('sign:')?PROPS.sign(prop.slice(5)):PROPS[prop]||''; return recolor(bearBase(size,{pose:'wave',prop:art})); },
 cub(state,size=36) {return recolor(cubBase(state,size));},
 eye(n) {
  const count=Number.isFinite(Number(n))?Math.max(0,Math.trunc(Number(n))):0;
  const digits=String(count).length, size=digits>2?54:digits>1?78:110;
  return `<svg class="v3-eye" viewBox="0 0 130 130" role="img" aria-label="${count} needs you"><rect width="130" height="130" fill="#e2402a"/><text x="65" y="106" text-anchor="middle" fill="#fff" font-size="${size}" font-family="Archivo" font-stretch="62%" font-weight="900">${count}</text></svg>`;
 }

};
})();
