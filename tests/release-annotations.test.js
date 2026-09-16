import test from 'node:test';
import assert from 'node:assert/strict';
import {passAnnotation,shotBall,passPathMidpoint} from '../viewer/release-annotations.js';
test('pass annotation freezes pre-release risk and expires after one second',()=>{
  const play={id:'p',frames:[{frame:8,geometry:{handler:1},offense:[[1,0,0],[2,10,0]],passOptions:[{player:2,turnoverProbability:.12}]},{frame:10,ball:[0,0]},{frame:15,ball:[5,0]},{frame:20,ball:[10,0]}]};
  const passes=[{possession:'p',start:10,end:20,passer:1,receiver:2}];
  const note=passAnnotation(play,passes,12);
  assert.equal(note.x,5);assert.equal(note.y,0);assert.equal(note.risk,.12);
  assert.equal(note.delta,null);
  play.frames[0].epv=1.1;
  play.frames[0].passOptions[0].value=1.14;
  assert.ok(Math.abs(passAnnotation(play,passes,12).delta-.04)<1e-10);
  assert.equal(passAnnotation(play,passes,35).alpha,1);
  assert.equal(passAnnotation(play,passes,40),null);
});
test('stamp follows curved ball path by distance, not player midpoint or mid-time',()=>{
 assert.deepEqual(passPathMidpoint([{frame:0,ball:[0,0]},{frame:5,ball:[0,8]},{frame:10,ball:[2,8]}],0,10),[0,5]);
 assert.equal(passPathMidpoint([{frame:0,ball:[0,0]},{frame:20,ball:[2,8]}],0,20),null);
});
test('shot ball uses release PPS only during the shot flight',()=>{
  const play={events:[{type:'shot',frame:10,shotForecast:{endFrame:30,quality:{fieldGoalValue:1},secondChancePerShot:.14}}]};
  assert.equal(shotBall(play,9),null);
  assert.ok(Math.abs(shotBall(play,20).pps-1.14)<1e-10);
  assert.equal(shotBall(play,31),null);
});
