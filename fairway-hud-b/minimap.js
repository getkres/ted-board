/* Geographic mini-map model and provider boundary, independent of the DOM. */
(function (root) {
  'use strict';
  const g = typeof module !== 'undefined' && module.exports ? require('./geometry.js') : root.GolfGeometry;
  function edgeDistance(location, ring) {
    const pts = ring.map(p=>g.project(p,location));
    if (g.contains([0,0],pts)) return 0;
    return Math.min(...pts.map((a,i)=>{
      const b=pts[(i+1)%pts.length], dx=b[0]-a[0], dy=b[1]-a[1];
      const t=Math.max(0,Math.min(1,-(a[0]*dx+a[1]*dy)/(dx*dx+dy*dy || 1)));
      return Math.hypot(a[0]+t*dx,a[1]+t*dy);
    }));
  }
  function greenMode(location,ring,previous) {
    return edgeDistance(location,ring) <= (previous ? 35 : 30)*.9144;
  }
  function frame(player,pin,ring) {
    const p=g.project(player,pin), length=Math.hypot(...p), coincident=length<.5;
    const up=coincident ? [0,1] : [-p[0]/length,-p[1]/length], right=[up[1],-up[0]];
    const rotate=v=>[v[0]*right[0]+v[1]*right[1],-(v[0]*up[0]+v[1]*up[1])];
    const points=[...ring,player,pin].map(point=>rotate(g.project(point,pin)));
    const xs=points.map(v=>v[0]), ys=points.map(v=>v[1]);
    const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
    const scale=Math.min(504/Math.max(1,maxX-minX),332/Math.max(1,maxY-minY));
    const cx=(minX+maxX)/2,cy=(minY+maxY)/2;
    return {
      coincident,scale,
      toScreen(point) { const q=rotate(g.project(point,pin));return [300+(q[0]-cx)*scale,278+(q[1]-cy)*scale]; },
      vector(eastNorth) { return rotate(eastNorth); },
      toGeo(screen) {
        const x=(screen[0]-300)/scale+cx,y=(screen[1]-278)/scale+cy;
        return g.unproject([x*right[0]-y*up[0],x*right[1]-y*up[1]],pin);
      }
    };
  }
  function provider(data) {
    if (!data || data.schemaVersion!==1 || typeof data.greenId!=='string' || !Array.isArray(data.samples)) throw new Error('Unsupported slope provider schema.');
    const coord=p=>Array.isArray(p) && p.length===2 && p.every(Number.isFinite) && Math.abs(p[0])<=180 && Math.abs(p[1])<=90;
    for(const s of data.samples) {
      if (!coord(s.position) || !Array.isArray(s.downhill) || s.downhill.length!==2 || !s.downhill.every(Number.isFinite) || Math.abs(Math.hypot(...s.downhill)-1)>.001 || !Number.isFinite(s.slopePercent) || s.slopePercent<0 || !Array.isArray(s.cell) || s.cell.length!==4 || !s.cell.every(coord) || !Number.isFinite(s.edgeClearanceM) || s.edgeClearanceM<0) throw new Error('Invalid terrain sample.');
    }
    return {
      getGreen(id,ring) {
        if(id!==data.greenId || !ring || !data.samples.length) return null;
        const center=g.center(ring),polygon=ring.map(p=>g.project(p,center));
        const registered=data.samples.every(s=>g.contains(g.project(s.position,center),polygon)
          && g.contains([0,0],s.cell.map(p=>g.project(p,s.position))));
        return registered ? data : null;
      },
      getRead: ()=>null
    };
  }
  function slopeBand(percent) { return percent<1 ? 'flat' : percent<3 ? 'medium' : 'steep'; }
  function arrowSamples(data) {
    if (!data) return [];
    const candidates=data.samples.filter(s=>s.edgeClearanceM>=2);
    if (!candidates.length) return [];
    const origin=candidates[0].position, xy=s=>g.project(s.position,origin);
    const points=candidates.map(xy), center=points.reduce((a,p)=>[a[0]+p[0]/points.length,a[1]+p[1]/points.length],[0,0]);
    let first=candidates.reduce((best,s)=>Math.hypot(...xy(s).map((v,i)=>v-center[i]))<Math.hypot(...xy(best).map((v,i)=>v-center[i])) ? s : best,candidates[0]);
    const chosen=[first];
    while(chosen.length<5 && chosen.length<candidates.length) {
      const distance=s=>Math.min(...chosen.map(c=>Math.hypot(...g.project(s.position,c.position))));
      const next=candidates.reduce((best,s)=>distance(s)>distance(best) ? s : best,candidates[0]);
      if(distance(next)<5) break;
      chosen.push(next);
    }
    return chosen;
  }
  const api={edgeDistance,greenMode,frame,provider,slopeBand,arrowSamples};
  if(typeof module!=='undefined' && module.exports) module.exports=api;else root.GolfMinimap=api;
})(typeof window!=='undefined' ? window : this);
