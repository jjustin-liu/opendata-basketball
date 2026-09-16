import test from 'node:test';
import assert from 'node:assert/strict';
import {scoreboardEstimate,cumulativeRisk} from '../viewer/possession-scoreboard.js';

test('scoreboard holds prior values only during a supported pass, never future catch',()=>{
 const play={id:'p',frames:[{frame:5,epv:1.1,turnoverRest:.2,geometry:{handler:1}},{frame:20,epv:9,turnoverRest:.9}]};
 const passes=[{possession:'p',start:10,end:20,passer:1,receiver:2}];
 assert.deepEqual(scoreboardEstimate(play,{},15,passes,'epv'),{epv:1.1,rest:.2,held:true});
 assert.equal(scoreboardEstimate(play,{},21,passes,'epv').epv,undefined);
 assert.equal(scoreboardEstimate(play,{epv:1.3,turnoverRest:.1},20,passes,'epv').epv,1.3);
});

test('risk accumulates holding exposure and each released pass once',()=>{
 const frames=Array.from({length:11},(_,i)=>({frame:i*5,turnover2:.1,geometry:{handler:1},passOptions:[{player:2,turnoverProbability:.2}]}));
 const play={id:'p',frames};
 const pass={possession:'p',start:20,end:30,passer:1,receiver:2};
 assert.equal(cumulativeRisk(play,0,[pass]).risk,0);
 assert.ok(Math.abs(cumulativeRisk(play,50).risk-.1)<1e-10);
 const r=cumulativeRisk(play,50,[pass,pass]);
 assert.equal(r.passCount,1);
 assert.ok(Math.abs(r.risk-(1-.8*Math.pow(.9,1.6/2)))<1e-10);
 assert.ok(cumulativeRisk(play,20,[pass]).risk>cumulativeRisk(play,19,[pass]).risk);
 assert.equal(cumulativeRisk({...play,id:'other'},0,[pass]).risk,0);
});

test('unsupported exposure is not reported as zero risk',()=>{
 const play={id:'p',frames:[{frame:0,reason:'missing'},{frame:100}]};
 assert.equal(cumulativeRisk(play,100).risk,null);
});
