(function(root,factory){const p=factory();if(typeof module==='object'&&module.exports)module.exports=p;else root.NFLPlay=p;})(globalThis,function(){
'use strict';
const choices={zone:['backed','open','red','goal'],personnel:['any','10','11','12','13','21'],formation:['any','shotgun','under_center','pistol','empty','2x2','3x1','bunch'],motion:['any','yes','no'],concept:['dagger','flood','mesh','slant_stick','four_verticals','screen','inside_zone']};
function parsePlay(text,teams){
 if(text.length>100000)throw Error('Use one structured play under 100 KB.');
 let p;try{p=JSON.parse(text)}catch{throw Error('Choose a JSON play file. Download the sample for the format.')}
 if(!p||Array.isArray(p)||typeof p!=='object')throw Error('The file must contain one play object.');
 if(!teams.includes(p.team))throw Error('Choose a valid opponent team code.');
 if(!Number.isInteger(p.down)||p.down<1||p.down>4||typeof p.distance!=='number'||!Number.isFinite(p.distance)||p.distance<0||p.distance>99)throw Error('Down must be 1-4, and distance must be 0-99.');
 const out={team:p.team,down:p.down,distance:p.distance};
 for(const [k,allowed]of Object.entries(choices)){if(!allowed.includes(p[k]))throw Error('Invalid or missing '+k+'. Use the sample play values.');out[k]=p[k]}
 return out;
}
function hasEdge(m){return !!m&&m.n>0&&Number.isFinite(m.brier)&&Number.isFinite(m.baseline_brier)&&m.brier<m.baseline_brier}
return {parsePlay,hasEdge};
});
