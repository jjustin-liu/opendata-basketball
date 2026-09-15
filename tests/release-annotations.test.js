import test from 'node:test';
import assert from 'node:assert/strict';
import {passAnnotation,shotBall} from '../viewer/release-annotations.js';
test('pass annotation freezes pre-release risk and expires after one second',()=>{
  const play={id:'p',frames:[{frame:8,geometry:{handler:1},offense:[[1,0,0],[2,10,0]],passOptions:[{player:2,turnoverProbability:.12}]}]};
  const passes=[{possession:'p',start:10,passer:1,receiver:2}];
  const note=passAnnotation(play,passes,12);
  assert.equal(note.x,5);assert.equal(note.y,1.3);assert.equal(note.risk,.12);
  assert.equal(passAnnotation(play,passes,35).alpha,1);
  assert.equal(passAnnotation(play,passes,40),null);
});
test('shot ball uses release PPS only during the shot flight',()=>{
  const play={events:[{type:'shot',frame:10,shotForecast:{endFrame:30,quality:{fieldGoalValue:1},secondChancePerShot:.14}}]};
  assert.equal(shotBall(play,9),null);
  assert.ok(Math.abs(shotBall(play,20).pps-1.14)<1e-10);
  assert.equal(shotBall(play,31),null);
});
