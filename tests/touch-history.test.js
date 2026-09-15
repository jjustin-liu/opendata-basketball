import test from 'node:test';
import assert from 'node:assert/strict';
import { touchHistory } from '../viewer/touch-history.js';

const touches=[{id:'a',player:1,start:10,end:30,shotClock:20},{id:'b',player:2,start:35,end:60,shotClock:19}];
const passes=[{possession:'p',passer:1,receiver:2,start:30,end:35}];
const play={id:'p',events:[],frames:[
  {frame:10,geometry:{handler:1},epv:1,turnover2:.04},
  {frame:25,geometry:{handler:1},epv:1.25,turnover2:.08,passOptions:[{player:2,value:1.05,completedEpv:1.5,turnoverProbability:.3}]},
  {frame:35,geometry:{handler:2},epv:1.55,turnover2:.01},
]};
test('stints separate pass risk, projected catch, actual catch and holding change',()=>{
  const rows=touchHistory(play,touches,passes,40);
  assert.equal(rows[0].change,.25);
  assert.equal(rows[0].passEpv,1.05);
  assert.equal(rows[0].projectedCatch,1.5);
  assert.equal(rows[0].passRisk,.3);
  assert.equal(rows[0].peakRisk,.08);
  assert.equal(rows[0].seconds,.8);
  assert.equal(rows[1].catchEpv,1.55);
  assert.equal(rows[1].seconds,.2);
});
test('future receipts and release decisions stay hidden until replay reaches them',()=>{
  const rows=touchHistory(play,touches,passes,20);
  assert.equal(rows.length,1);
  assert.equal(rows[0].action,'HOLDING');
  assert.equal(rows[0].passEpv,null);
  assert.equal(rows[0].peakRisk,.04);
});
test('missing catch estimates are not filled using a later holding value',()=>{
  const p={...play,frames:play.frames.filter(f=>f.frame!==10)};
  const row=touchHistory(p,touches,passes,30)[0];
  assert.equal(row.catchEpv,null);
  assert.equal(row.change,null);
  assert.equal(row.endEpv,1.25);
});
