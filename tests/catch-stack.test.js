import test from 'node:test';
import assert from 'node:assert/strict';
import { drawCatchStack, displayedCatchEpv } from '../viewer/catch-stack.js';

test('catch preview puts EPV above and C&S below with no fabricated missing value',()=>{
  const labels=[];
  const ctx={save(){},restore(){},beginPath(){},roundRect(){},fill(){},measureText(t){return {width:t.length};},fillText(t,x,y){labels.push({t,x,y});}};
  drawCatchStack(ctx,10,20,2,{value:1.11,completedEpv:1.3,catchShot:{pps:1.28}});
  assert.deepEqual(labels.map(v=>v.t),['1.11','EPV','1.28','C&S']);
  assert.ok(labels[1].y<labels[0].y && labels[0].y<20);
  assert.ok(labels[3].y>labels[2].y && labels[2].y>20);
  labels.length=0;
  drawCatchStack(ctx,10,20,2,{});
  assert.equal(labels[0].t,'—');assert.equal(labels[2].t,'—');
  labels.length=0;
  drawCatchStack(ctx,10,20,2,{value:1.11,catchShot:{pps:1.28},turnoverProbability:.085});
  assert.deepEqual(labels.map(v=>v.t),['1.11','EPV','1.28','C&S','8.5%','TOV']);
  assert.ok(labels[4].x>12 && labels[5].x>12);
  assert.ok(labels[4].y<20 && labels[5].y>20);
});

test('EPV begins discounted and eases toward catch value without using outcome',()=>{
  assert.equal(displayedCatchEpv({value:.84,completedEpv:1.2},123),.84);
  const pass={epv:.84,completedEpv:1.2,start:10,end:20};
  assert.equal(displayedCatchEpv(pass,9),.84);
  assert.equal(displayedCatchEpv(pass,10),.84);
  assert.ok(Math.abs(displayedCatchEpv(pass,15)-1.02)<1e-10);
  assert.equal(displayedCatchEpv(pass,20),1.2);
  assert.equal(displayedCatchEpv(pass,21),1.2);
  assert.ok(displayedCatchEpv(pass,10.5)>displayedCatchEpv(pass,10));
  assert.equal(displayedCatchEpv({completedEpv:1.2},15),null);
  assert.equal(displayedCatchEpv({...pass,end:10},15),.84);
});
