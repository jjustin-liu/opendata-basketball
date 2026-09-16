import test from 'node:test';
import assert from 'node:assert/strict';
import { playRecap, playOutcome, recapMarkup } from '../viewer/play-recap.js';
import { cumulativeRisk } from '../viewer/possession-scoreboard.js';

test('scoreboard, recap and final sorting share pass risk and first-shot cutoff',()=>{
  const frames=Array.from({length:21},(_,i)=>({frame:i*5,turnover2:.1,geometry:{handler:1},passOptions:[{player:2,turnoverProbability:.2}]}));
  const play={id:'p',frames,events:[{type:'shot',frame:50,shotForecast:{shotPlusSecondChance:1.5}}]};
  const passes=[{possession:'p',start:10,end:20,passer:1,receiver:2},{possession:'p',start:75,end:85,passer:1,receiver:2}];
  const risk=cumulativeRisk(play,100,passes);
  const recap=playRecap(play,100,passes);
  assert.equal(risk.passCount,1);
  assert.equal(risk.risk,cumulativeRisk(play,50,passes).risk);
  assert.equal(recap.risk,risk.risk);
  assert.ok(Math.abs(recap.playValue/recap.total+ risk.risk-1)<1e-12);
});

test('cumulative approximation weights time rather than counting overlapping forecasts', () => {
  const frames=Array.from({length:11},(_,i)=>({frame:i*5,turnover2:.1}));
  const play={frames,events:[]};
  assert.ok(Math.abs(playRecap(play,50).risk-.1)<1e-10);
  assert.equal(playRecap(play,50).coverage,1);
  frames.forEach(f=>f.reason='unsupported');
  assert.equal(playRecap(play,50).risk,null);
});
test('play value discounts only risk before first shot, not rebound continuation',()=>{
  const frames=Array.from({length:21},(_,i)=>({frame:i*5,turnover2:i<10?.1:.9}));
  const play={frames,events:[{type:'shot',frame:50,shotForecast:{shotPlusSecondChance:1.5,foulProbability:.2,fouledPps:2.3,notFouledPps:1.3}}]};
  const r=playRecap(play,100);
  assert.ok(Math.abs(r.risk-.1)<1e-10);
  assert.ok(Math.abs(r.playValue-1.35)<1e-10);
  assert.match(recapMarkup(r),/20.0%/);
  assert.match(recapMarkup(r),/80.0%/);
  assert.match(recapMarkup(r),/1.35 <small>EPV/);
  assert.match(recapMarkup(r),/1.50<\/b> PPA/);
  assert.match(recapMarkup(r),/expected survival/);
  assert.equal(playRecap({frames,events:[]},100).playValue,null);
  assert.equal(playRecap({...play,frames:[]},100).playValue,null);
});
test('first shot components stay distinct and are not revealed before release', () => {
  const play={frames:[],events:[{type:'shot',frame:10,label:'Made 2PT',shotForecast:{quality:{fieldGoalValue:1.14},offensiveReboundProbability:.28,secondChancePerShot:.2}}]};
  assert.equal(playRecap(play,9).first,null);
  assert.equal(playRecap(play,9).orb,null);
  assert.equal(playRecap(play,10).orb,.28);
  assert.equal(playRecap(play,10).first,1.14);
  assert.equal(playRecap(play,10).second,.2);
  assert.ok(Math.abs(playRecap(play,10).total-1.34)<1e-10);
  assert.equal(playOutcome(play),'MADE 2PT');
  assert.equal(playOutcome({...play,turnover:true}),'TURNOVER');
});

test('recap separates modeled branches and reports both conditional rebound rates',()=>{
  const r=playRecap({frames:[],events:[{type:'shot',frame:10,shotForecast:{offensiveReboundProbability:.277,ftOffensiveReboundProbability:.113}}]},10);
  assert.equal(r.ftOrb,.113);
  const html=recapMarkup(r);
  assert.match(html,/modeled possibilities, not the result/);
  assert.match(html,/ORB 27.7% on a miss/);
  assert.match(html,/FT ORB 11.3%/);
});
