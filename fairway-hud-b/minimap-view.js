/* SVG rendering only. Coordinates and fall lines come from the model/provider. */
(function(root) {
  'use strict';
  // Smooth heat in the classic green read colors (Sebastian 2026-11-16: "the reds and the greens").
  // Flat ground under 1.6 percent stays clear, so the real grass shows through the lens.
  const HEAT_STYLE='smooth';
  // How the hill is drawn: 'grid' = wavy grid on a tilted view, 'contour' = height lines that brighten uphill.
  const TERRAIN_LINES=(typeof location!=='undefined'&&/[?&]lines=grid/.test(location.search))?'grid':'contour';
  const HEAT_BINS=[1.6,2.6,3.6,4.6],HEAT_COLORS=['#2BD95C','#FFE135','#FF8A1E','#FF3426'],HEAT_OPACITY=.7;
  // Chaikin corner cutting: rounds the OSM polygon so the outline reads as a clean line, not a scribble.
  function smoothRing(points,passes=3) {
    let pts=points.slice();
    if(pts.length>2&&pts[0][0]===pts[pts.length-1][0]&&pts[0][1]===pts[pts.length-1][1])pts.pop();
    for(let k=0;k<passes;k++) {
      const out=[];
      pts.forEach((a,i)=>{const b=pts[(i+1)%pts.length];
        out.push([a[0]*.75+b[0]*.25,a[1]*.75+b[1]*.25],[a[0]*.25+b[0]*.75,a[1]*.25+b[1]*.75]);});
      pts=out;
    }
    return pts;
  }
  // Rebuild relative height from the slope samples (slope percent plus downhill direction),
  // so the lens can show where the high side is, not just how steep it is.
  const heightCache=new WeakMap();
  function heightField(terrain) {
    if(heightCache.has(terrain))return heightCache.get(terrain);
    const s=terrain.samples,o=s[0].position,P=s.map(x=>root.GolfGeometry.project(x.position,o));
    const G=s.map(x=>[-x.downhill[0]*x.slopePercent/100,-x.downhill[1]*x.slopePercent/100]);
    const nb=P.map((p,i)=>{const out=[];P.forEach((q,j)=>{if(i!==j&&Math.hypot(q[0]-p[0],q[1]-p[1])<1.5)out.push(j);});return out;});
    const z=new Float64Array(s.length);
    for(let it=0;it<900;it++)for(let i=0;i<s.length;i++) {
      if(!nb[i].length)continue;let sum=0;
      for(const j of nb[i]){const gx=(G[i][0]+G[j][0])/2,gy=(G[i][1]+G[j][1])/2;sum+=z[j]+gx*(P[i][0]-P[j][0])+gy*(P[i][1]-P[j][1]);}
      z[i]=sum/nb[i].length;
    }
    let min=Infinity,max=-Infinity;z.forEach(v=>{min=Math.min(min,v);max=Math.max(max,v);});
    const xs=P.map(p=>p[0]),ys=P.map(p=>p[1]);
    const span=Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys));
    const field={z:[...z].map(v=>v-min),range:max-min,span};
    heightCache.set(terrain,field);return field;
  }
  const inside=(pt,poly)=>{let c=false;for(let i=0,j=poly.length-1;i<poly.length;j=i++){const a=poly[i],b=poly[j];
    if((a[1]>pt[1])!==(b[1]>pt[1])&&pt[0]<(b[0]-a[0])*(pt[1]-a[1])/(b[1]-a[1])+a[0])c=!c;}return c;};
  // Equal-height lines (marching squares on the 1 m sample grid). Returns segments in lon/lat.
  function contours(terrain,field,interval) {
    const s=terrain.samples,G=root.GolfGeometry,o=s[0].position,P=s.map(x=>G.project(x.position,o));
    const c0=s[0].cell.map(p=>G.project(p,o)),ax=[c0[1][0]-c0[0][0],c0[1][1]-c0[0][1]],ay=[c0[3][0]-c0[0][0],c0[3][1]-c0[0][1]];
    const dot=(u,v)=>u[0]*v[0]+u[1]*v[1],key=(i,j)=>i+','+j,idx=new Map();
    P.forEach((p,n)=>idx.set(key(Math.round(dot(p,ax)/dot(ax,ax)),Math.round(dot(p,ay)/dot(ay,ay))),n));
    const out=[];
    idx.forEach((n,k)=>{
      const [i,j]=k.split(',').map(Number),q=[n,idx.get(key(i+1,j)),idx.get(key(i+1,j+1)),idx.get(key(i,j+1))];
      if(q.some(v=>v===undefined))return;
      const zs=q.map(v=>field.z[v]),lo=Math.min(...zs),hi=Math.max(...zs);
      for(let L=Math.ceil(lo/interval)*interval;L<hi;L+=interval) {
        const hits=[];
        for(let e=0;e<4;e++){const a=q[e],b=q[(e+1)%4],za=field.z[a],zb=field.z[b];
          if((za-L)*(zb-L)<0){const t=(L-za)/(zb-za),pa=s[a].position,pb=s[b].position;hits.push([pa[0]+(pb[0]-pa[0])*t,pa[1]+(pb[1]-pa[1])*t]);}}
        for(let h=0;h+1<hits.length;h+=2)out.push({level:L,a:hits[h],b:hits[h+1]});
      }
    });
    return out;
  }
  const ns='http://www.w3.org/2000/svg', g=root.GolfGeometry,m=root.GolfMinimap;
  function node(tag,attrs={},text) {
    const e=document.createElementNS(ns,tag);
    Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));
    if(text!==undefined)e.textContent=text;
    return e;
  }
  const path=points=>points.map((p,i)=>`${i?'L':'M'}${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(' ')+'Z';
  // Fit only the green. The paired phone can be in the cart, so its position
  // must never imply a ball location on the putting surface.
  function lensFrame(player,ring,onGreen,approachBearing,width,height,lift=0) {
    const center=g.center(ring);
    const source=onGreen && Number.isFinite(approachBearing)
      ? g.demoLocation(ring,100,approachBearing) : player;
    const approach=g.project(source,center),length=Math.hypot(...approach);
    const up=length<.5 ? [0,1] : [-approach[0]/length,-approach[1]/length];
    const right=[up[1],-up[0]];
    // With terrain the ground tilts away from you (seen from the front of the green), so raised ground reads as a hill.
    const squash=lift?.58:1;
    const rotate=v=>[v[0]*right[0]+v[1]*right[1],-(v[0]*up[0]+v[1]*up[1])*squash];
    const points=ring.map(p=>rotate(g.project(p,center)));
    const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
    const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
    const top=32,bottom=onGreen?8:30,pad=8;
    const scale=Math.min((width-2*pad)/(maxX-minX),(height-top-bottom)/(maxY-minY+lift));
    return {
      scale,
      toScreen(point){const q=rotate(g.project(point,center));return [width/2+(q[0]-(minX+maxX)/2)*scale,top+(height-top-bottom)/2+(q[1]-(minY+maxY)/2+lift/2)*scale];},
      vector:rotate
    };
  }
  function render(svg,{player,ring,terrain=null,onGreen=false,approachBearing}) {
    const width=220,height=onGreen?270:196;
    svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
    svg.dataset.state=onGreen?'on':'near';
    svg.dataset.heatStyle=HEAT_STYLE;
    svg.setAttribute('aria-label',`${terrain ? `Demo terrain slope heat from green to red, ${TERRAIN_LINES==='grid'?'a raised grid':'height lines that brighten uphill'} showing the high ground, and white downhill arrows, ` : ''}smooth green outline. ${onGreen ? 'Whole green viewed from the fairway approach.' : 'Blue approach chevron.'} No pin or ball position.`);
    svg.replaceChildren();
    // The hill: heights are raised on screen (exaggerated) so high ground sits higher in the lens.
    const field=terrain?heightField(terrain):null;
    const exag=field&&TERRAIN_LINES==='grid'&&field.range>.05?Math.min(16,Math.max(4,.32*field.span/field.range)):0;
    const f=lensFrame(player,ring,onGreen,approachBearing,width,height,field?field.range*exag:0);
    const flat=smoothRing(ring.map(f.toScreen));
    let raise=p=>p;
    if(terrain) {
      const S=terrain.samples.map(x=>f.toScreen(x.position)),r2=Math.pow(1.6*f.scale,2);
      const zAt=pt=>{let w=0,sum=0,best=Infinity,bz=0;
        S.forEach((q,i)=>{const d=(q[0]-pt[0])**2+(q[1]-pt[1])**2;if(d<best){best=d;bz=field.z[i];}
          if(d<r2){const k=1/(d+.5);w+=k;sum+=k*field.z[i];}});return w?sum/w:bz;};
      raise=pt=>[pt[0],pt[1]-zAt(pt)*exag*f.scale];
    }
    const outline=path(flat.map(raise));
    if(terrain) {
      const clipId=svg.id+'-terrain-clip',defs=node('defs'),clip=node('clipPath',{id:clipId});
      clip.append(node('path',{d:outline}));defs.append(clip);svg.append(defs);
      const layer=node('g',{'clip-path':`url(#${clipId})`});
      const firstCell=terrain.samples[0].cell.map(f.toScreen);
      const cellPx=Math.hypot(firstCell[1][0]-firstCell[0][0],firstCell[1][1]-firstCell[0][1]);
      const blurId=svg.id+'-heat-blur',blur=node('filter',{id:blurId,filterUnits:'userSpaceOnUse',x:0,y:0,width,height});
      blur.append(node('feGaussianBlur',{stdDeviation:(cellPx*.9).toFixed(2)}));defs.append(blur);
      const heat=node('g',{filter:`url(#${blurId})`,opacity:HEAT_OPACITY,class:'heat-layer'});
      terrain.samples.forEach((sample,index)=>{
        let band=-1;
        HEAT_BINS.forEach((threshold,i)=>{if(sample.slopePercent>=threshold)band=i;});
        if(band<0)return;
        // Cells grow a hair so neighbors overlap and the blur has no seams.
        const lift=field.z[index]*exag*f.scale;
        const cell=sample.cell.map(f.toScreen).map(p=>[p[0],p[1]-lift]),c=cell.reduce((v,p)=>[v[0]+p[0]/4,v[1]+p[1]/4],[0,0]);
        const grown=cell.map(p=>[c[0]+(p[0]-c[0])*1.15,c[1]+(p[1]-c[1])*1.15]);
        heat.append(node('path',{d:path(grown),fill:HEAT_COLORS[band],class:'heat-cell','data-band':band}));
      });
      layer.append(heat);
      // Wavy grid: straight lines every 2 m on the ground, bent up over the high spots.
      if(exag) {
        const xs=flat.map(p=>p[0]),ys=flat.map(p=>p[1]),gap=Math.max(14,3*f.scale),step=2.5;
        const grid=node('g',{class:'contour-grid',fill:'none',stroke:'#FFFFFF','stroke-opacity':.75,'stroke-width':1.3,'stroke-linejoin':'round'});
        const line=pts=>{let run=[];const flush=()=>{if(run.length>1)grid.append(node('path',{d:run.map((p,i)=>`${i?'L':'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(''),class:'grid-line'}));run=[];};
          pts.forEach(p=>{if(inside(p,flat))run.push(raise(p));else flush();});flush();};
        for(let y=Math.min(...ys)+gap/2;y<Math.max(...ys);y+=gap){const pts=[];for(let x=Math.min(...xs);x<=Math.max(...xs);x+=step)pts.push([x,y]);line(pts);}
        for(let x=Math.min(...xs)+gap/2;x<Math.max(...xs);x+=gap){const pts=[];for(let y=Math.min(...ys);y<=Math.max(...ys);y+=step)pts.push([x,y]);line(pts);}
        layer.append(grid);
      }
      if(TERRAIN_LINES==='contour'&&field.range>.05) {
        // 8 height bands give 7 lines. Uphill lines get much brighter and thicker (0.2 to 1.0 opacity,
        // 1.0 to 2.6 px), so the bright, thick side is the high side at a glance (review 2026-11-17).
        const BANDS=8,interval=field.range/BANDS,lines=node('g',{class:'contour-lines',fill:'none',stroke:'#FFFFFF','stroke-linecap':'round','stroke-linejoin':'round'});
        const byLevel=new Map();
        for(const seg of contours(terrain,field,interval)) {
          const k=Math.round(seg.level/interval),a=f.toScreen(seg.a),b=f.toScreen(seg.b);
          if(!byLevel.has(k))byLevel.set(k,[]);
          byLevel.get(k).push(`M${a[0].toFixed(1)},${a[1].toFixed(1)}L${b[0].toFixed(1)},${b[1].toFixed(1)}`);
        }
        // One path per level, so overlapping round caps do not bead on the faint lines.
        [...byLevel.keys()].sort((x,y)=>x-y).forEach(k=>{
          const u=Math.min(1,Math.max(0,(k-1)/(BANDS-2)));
          lines.append(node('path',{d:byLevel.get(k).join(''),'stroke-opacity':(.2+.8*u).toFixed(2),'stroke-width':(1+1.6*u).toFixed(2),class:'contour-line','data-level':k}));
        });
        layer.append(lines);
      }
      for(const sample of m.arrowSamples(terrain)) {
        const xy=raise(f.toScreen(sample.position)),v=f.vector(sample.downhill),angle=Math.atan2(v[1],v[0])*180/Math.PI;
        layer.append(node('path',{d:'M-11 0H11M3.14 -4.3L11 0L3.14 4.3',
          transform:`translate(${xy}) rotate(${angle})`,fill:'none',stroke:'#ffffff',
          'stroke-width':2.8,'stroke-linecap':'round','stroke-linejoin':'round',class:'fall-arrow'}));
      }
      svg.append(layer,node('text',{x:width/2,y:18,'text-anchor':'middle','font-size':18,
        'font-style':'italic','font-stretch':'120%','font-weight':700,fill:'#FFD400'},'Demo Terrain'));
    }
    svg.append(node('path',{d:outline,fill:'none',stroke:'#FFFFFF','stroke-opacity':.6,'stroke-width':2,'stroke-linejoin':'round',class:'green-outline'}));
    if(!onGreen)svg.append(node('path',{d:`M${width/2-11} ${height-8}L${width/2} ${height-20}L${width/2+11} ${height-8}`,
      stroke:'#B9DCFF','stroke-width':3.2,fill:'none','stroke-linecap':'round','stroke-linejoin':'round',class:'approach-chevron'}));
    return f;
  }
  function editor(svg,ring,pin,manual) {
    const center=g.center(ring),f=m.frame(center,center,ring),p=f.toScreen(pin);
    svg.replaceChildren(node('path',{d:path(ring.map(f.toScreen)),fill:'#d9e8cf',stroke:'#285a49','stroke-width':4}),
      node('text',{x:30,y:60,'font-size':26,fill:'#163e35'},'North ↑'),
      node('circle',{cx:p[0],cy:p[1],r:11,fill:'#163e35'}),
      node('text',{x:p[0]+20,y:p[1]+8,'font-size':25,fill:'#163e35'},manual?'Pin':'Center'));
    return f;
  }
  root.GolfMinimapView={render,editor};
})(window);
