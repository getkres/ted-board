const test = require('node:test');
const assert = require('node:assert/strict');
const E = require('./engine.js');
const q={team:'LA',down:3,distance:8,zone:'open',formation:'shotgun',motion:'yes',personnel:'11',concept:'dagger'};
const rows=Array.from({length:60},(_,i)=>({team:'LA',g:'g'+Math.floor(i/20),w:1+Math.floor(i/20),d:i%2?3:1,dist:i%2?'long':'medium',z:'open',qb:'S',m:1,drop:1,rush:i%3?4:5,blitz:i%3?0:1,box:6}));
test('unknown outcomes stay unavailable rather than become false',()=>{
 const r=E.forecast(rows.map(x=>({...x,rush:null})),q,'rush5');
 assert.equal(r.available,false);assert.equal(r.probability,null);assert.equal(r.exact_n,0);
});
test('unknown team never borrows another team as its own sample',()=>{
 const r=E.forecast(rows,{...q,team:'NOT_A_TEAM'},'rush5');assert.equal(r.available,false);assert.equal(r.n,0);
});
test('unsupported personnel and split alignment are disclosed and do not change the estimate',()=>{
 const a=E.forecast(rows,{...q,personnel:'any',formation:'any'},'rush5');
 const b=E.forecast(rows,{...q,personnel:'12',formation:'bunch'},'rush5');
 assert.equal(a.probability,b.probability);assert.ok(b.ignored_inputs.includes('personnel'));assert.ok(b.ignored_inputs.includes('formation'));
});
test('zero exact matches retain zero support even when a broader forecast exists',()=>{
 const r=E.forecast(rows,{...q,zone:'goal',motion:'no'},'rush5');
 assert.equal(r.exact_n,0);assert.equal(r.low_confidence,true);assert.ok(r.n>0);assert.equal(r.pooled,true);
});
test('blitzer and actual rush count are different labels',()=>{
 const r=rows.map(x=>({...x,rush:4,blitz:1}));
 assert.equal(E.forecast(r,q,'rush5').k,0);assert.equal(E.forecast(r,q,'blitzer').k,E.forecast(r,q,'blitzer').n);
});
test('current coverage and named blitzer predictions remain unavailable',()=>{
 for(const target of ['coverage','shell','who'])assert.equal(E.forecast(rows,q,target).available,false);
});
test('invalid situation values fail clearly',()=>{
 assert.throws(()=>E.normalizeQuery({...q,down:9}),/down/);assert.throws(()=>E.normalizeQuery({...q,distance:-1}),/distance/);
});
test('concept advice is a hypothesis and never pretends to measure success',()=>{
 const r=E.conceptAnswer(q,{rush5:{available:true,probability:.7},box7:{available:true,probability:.3}});
 assert.equal(r.evidence,'hypothesis');assert.equal(r.measured_advantage,null);assert.match(r.suggestion,/slant|stick/i);
});
test('the caller supplies only earlier games to evaluation fitting',()=>{
 const train=rows.filter(x=>x.w<=2);const prediction=E.forecast(train,q,'rush5');
 assert.ok(prediction.training_games.every(g=>g!=='g2'));
});
