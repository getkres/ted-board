/* SVG rendering only. Coordinates and fall lines come from the model/provider. */
(function(root) {
  'use strict';
  const ns='http://www.w3.org/2000/svg', g=root.GolfGeometry,m=root.GolfMinimap;
  function node(tag,attrs={},text) {
    const e=document.createElementNS(ns,tag);
    Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));
    if(text!==undefined)e.textContent=text;
    return e;
  }
  const path=points=>points.map((p,i)=>`${i?'L':'M'}${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(' ')+'Z';
  function render(svg,{player,pin,ring,terrain=null,terrainMode='arrows'}) {
    svg.setAttribute('aria-label',`${terrain ? (terrainMode==='heat' ? 'Demo terrain heat, ' : 'Demo terrain downhill arrows, ') : ''}green outline, cyan player dot, and white pin. Pin above player, or north up when coincident.`);
    svg.replaceChildren();
    const f=m.frame(player,pin,ring),pinXY=f.toScreen(pin),playerXY=f.toScreen(player);
    const outline=path(ring.map(f.toScreen));
    if(terrain) {
      // Clip the raster footprints and arrows to the same rotated green outline.
      const clipId=svg.id+'-terrain-clip',defs=node('defs'),clip=node('clipPath',{id:clipId});
      clip.append(node('path',{d:outline}));defs.append(clip);svg.append(defs);
      const layer=node('g',{'clip-path':`url(#${clipId})`});
      if(terrainMode==='heat') {
        const colors={flat:'#72edff',medium:'#fff477',steep:'#ff9c68'};
        for(const sample of terrain.samples)layer.append(node('path',{
          d:path(sample.cell.map(f.toScreen)),fill:colors[m.slopeBand(sample.slopePercent)],
          'fill-opacity':.65,class:'heat-cell'
        }));
      } else {
        // 50 SVG units = 20 native pixels; keep the glyphs clear of both markers.
        const samples=terrain.samples.filter(sample=>{
          const xy=f.toScreen(sample.position);
          return sample.edgeClearanceM>=2 && Math.hypot(xy[0]-playerXY[0],xy[1]-playerXY[1])>58
            && Math.hypot(xy[0]-pinXY[0],xy[1]-pinXY[1])>65;
        });
        for(const sample of m.arrowSamples({...terrain,samples})) {
          const xy=f.toScreen(sample.position),v=f.vector(sample.downhill),angle=Math.atan2(v[1],v[0])*180/Math.PI;
          const arrow=node('path',{d:'M-25 0H25M7 -15L25 0L7 15',
            transform:`translate(${xy}) rotate(${angle})`,fill:'none',stroke:'#fff477',
            'stroke-width':7,'stroke-linecap':'round','stroke-linejoin':'round',class:'fall-arrow'});
          layer.append(arrow);
        }
      }
      svg.append(layer,node('text',{x:300,y:101,'text-anchor':'middle','font-size':30,'font-weight':600,fill:'#fff'},'Demo Terrain'));
    }
    svg.append(node('path',{d:outline,fill:'none',stroke:'#fff','stroke-width':5,'stroke-linejoin':'round'}));
    svg.append(node('circle',{cx:playerXY[0],cy:playerXY[1],r:12,fill:'#64d8ff',stroke:'#fff','stroke-width':3,class:'map-player'}));
    const pinGroup=node('g',{transform:`translate(${pinXY})`,class:'map-pin'});
    pinGroup.append(node('circle',{r:6,fill:'#fff'}),node('path',{d:'M0 0V-32L25 -25L0 -17',fill:'none',stroke:'#fff','stroke-width':4,'stroke-linejoin':'round'}));svg.append(pinGroup);
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
