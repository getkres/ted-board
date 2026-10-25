(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.NFLEngine=value;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const POLICY=Object.freeze({minCell:20,minGames:3,priorWeight:20,minExact:12,trainThroughWeek:4});
  function normalizeQuery(input){
    const q={...input,down:Number(input.down),distance:Number(input.distance)};
    if(!Number.isInteger(q.down)||q.down<1||q.down>4)throw Error('Choose a down from 1 to 4.');
    if(!Number.isFinite(q.distance)||q.distance<0||q.distance>99)throw Error('Enter a distance from 0 to 99 yards.');
    if(!['backed','open','red','goal'].includes(q.zone))throw Error('Choose a field zone.');
    q.dist=q.distance<=3?'short':q.distance<=6?'medium':'long';
    q.qb=({shotgun:'S',under_center:'U',pistol:'P'})[q.formation]||null;
    q.m=q.motion==='yes'?1:q.motion==='no'?0:null;
    return q;
  }
  function label(r,target){
    if((target==='rush5'||target==='blitzer')&&r.drop!==1)return null;
    const v=target==='rush5'?r.rush:target==='blitzer'?r.blitz:target==='box7'?r.box:null;
    if(v===null||v===undefined||!Number.isFinite(v))return null;
    return target==='rush5'?Number(v>=5):target==='blitzer'?Number(v>=1):Number(v>=7);
  }
  function wilson(k,n){
    if(!n)return [null,null];const z=1.96,p=k/n,den=1+z*z/n,center=(p+z*z/(2*n))/den,half=z*Math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;return [center-half,center+half];
  }
  const games=rows=>[...new Set(rows.map(r=>r.g))];
  function forecast(records,input,target){
    const q=normalizeQuery(input),ignored=[];
    if(q.personnel&&q.personnel!=='any')ignored.push('personnel');
    if(q.formation&&q.formation!=='any'&&!q.qb)ignored.push('formation');
    const unavailable={available:false,probability:null,n:0,k:0,exact_n:0,exact_games:0,games:0,pooled:false,low_confidence:true,ignored_inputs:ignored,training_games:[],target};
    if(!['rush5','blitzer','box7'].includes(target))return {...unavailable,reason:'Current public sources do not identify this response.'};
    const rows=records.filter(r=>r.team===q.team&&label(r,target)!==null);
    if(!rows.length)return {...unavailable,reason:'No eligible charted plays for this team and outcome.'};
    const baselineK=rows.reduce((a,r)=>a+label(r,target),0),baselineP=baselineK/rows.length;
    const full=['d','dist','z',...(q.qb?['qb']:[]),...(q.m!==null?['m']:[])];
    const query={d:q.down,dist:q.dist,z:q.zone,qb:q.qb,m:q.m};
    const matches=keys=>rows.filter(r=>keys.every(key=>r[key]===query[key]));
    const exact=matches(full);
    const levels=[{name:'full situation and available look',keys:full},{name:'down, distance, and available look',keys:full.filter(x=>x!=='z')},{name:'down and distance',keys:['d','dist']},{name:'down only',keys:['d']},{name:'team base rate',keys:[]}];
    let selected=levels[levels.length-1],cell=rows;
    for(const level of levels){const c=matches(level.keys);if(c.length>=POLICY.minCell&&games(c).length>=POLICY.minGames){selected=level;cell=c;break;}}
    const n=cell.length,k=cell.reduce((a,r)=>a+label(r,target),0),pooled=selected.keys.length<full.length;
    const probability=selected.keys.length===0?baselineP:(k+POLICY.priorWeight*baselineP)/(n+POLICY.priorWeight);
    return {available:true,target,probability,n,k,raw_rate:k/n,ci:wilson(k,n),games:games(cell).length,
      exact_n:exact.length,exact_games:games(exact).length,exact_k:exact.reduce((a,r)=>a+label(r,target),0),pooled,
      scope:selected.name,used_features:selected.keys,dropped_features:full.filter(x=>!selected.keys.includes(x)),
      low_confidence:exact.length<POLICY.minExact||games(exact).length<POLICY.minGames||ignored.length>0,
      ignored_inputs:ignored,baseline_k:baselineK,baseline_n:rows.length,baseline_probability:baselineP,training_games:games(rows)};
  }
  const RULES=[
    {id:'W01',name:'Third-and-long pressure',target:'rush5',terms:{down:3,minDistance:7},test:r=>r.d===3&&r.dist==='long'},
    {id:'W02',name:'Third-down blitzers',target:'blitzer',terms:{down:3},test:r=>r.d===3},
    {id:'W03',name:'Early-down pressure',target:'rush5',terms:{maxDown:2},test:r=>r.d<=2},
    {id:'W04',name:'Pressure against motion',target:'rush5',terms:{motion:'yes'},test:r=>r.m===1},
    {id:'W05',name:'Pressure against shotgun',target:'rush5',terms:{formation:'shotgun'},test:r=>r.qb==='S'},
    {id:'W06',name:'First-down loaded box',target:'box7',terms:{down:1},test:r=>r.d===1},
    {id:'W07',name:'Pressure in the red zone',target:'rush5',terms:{zones:['red','goal']},test:r=>r.z==='red'||r.z==='goal'}
  ];
  function ruleApplies(rule,input){const q=normalizeQuery(input),t=rule.terms;return (!t.down||q.down===t.down)&&(!t.maxDown||q.down<=t.maxDown)&&(!t.minDistance||q.distance>=t.minDistance)&&(!t.motion||q.motion===t.motion)&&(!t.formation||q.formation===t.formation)&&(!t.zones||t.zones.includes(q.zone));}
  function ruleStats(records,team,rule){
    const eligible=records.filter(r=>r.team===team&&label(r,rule.target)!==null),cell=eligible.filter(rule.test),k=cell.reduce((a,r)=>a+label(r,rule.target),0),n=cell.length,bk=eligible.reduce((a,r)=>a+label(r,rule.target),0);
    return {id:rule.id,name:rule.name,target:rule.target,terms:rule.terms,k,n,games:games(cell).length,rate:n?k/n:null,ci:wilson(k,n),base_k:bk,base_n:eligible.length,base_rate:eligible.length?bk/eligible.length:null,grade:n>=30&&games(cell).length>=3?'observation':'small-sample observation'};
  }
  function conceptAnswer(input,forecasts){
    const q=normalizeQuery(input);let suggestion='Keep the called concept, with a protection check and an outlet.',reason='Coverage and individual rush sources are unknown, so this data cannot rank the best route concept.';
    if(forecasts.rush5?.available&&forecasts.rush5.probability>=.4){suggestion='Rehearse quick slant / stick-replace with a protection answer.';reason='If an extra defender comes, a quick throw may attack the space he leaves. Confirm that another defender has not replaced him. Longer concepts need enough protection time.';}
    if(q.concept==='inside_zone'&&forecasts.box7?.available&&forecasts.box7.probability>=.5){suggestion='Rehearse a quick perimeter or glance answer to a loaded box.';reason='A loaded box can leave fewer defenders outside, but the actual leverage and rotation must confirm the throw. This is a coaching hypothesis.';}
    return {called:q.concept,suggestion,reason,evidence:'hypothesis',measured_advantage:null,limit:'No measured concept win rate, EPA advantage, or optimal-play ranking is available.'};
  }
  return {POLICY,normalizeQuery,label,wilson,forecast,RULES,ruleApplies,ruleStats,conceptAnswer};
});
