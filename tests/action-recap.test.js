import test from 'node:test';
import assert from 'node:assert/strict';
import { actionRecap } from '../viewer/action-recap.js';
import { releaseCard } from '../viewer/action-display.js';

test('release card keeps pass feedback only until catch or half a second', () => {
  const play = {id:'p',events:[],frames:[{frame:8,offense:[[1,0,0],[2,1,1]],geometry:{handler:1},shot:{shotPlusSecondChance:1.54},passOptions:[{player:2,value:1.14}]}]};
  const passes=[{possession:'p',passer:1,receiver:2,start:10,end:15}];
  const card=releaseCard(play,passes,12);
  assert.equal(card.selected,'PASS');
  assert.equal(card.shot,1.54);
  assert.equal(card.pass,1.14);
  assert.equal(releaseCard(play,passes,15),null);
  assert.equal(releaseCard(play,passes,35),null);
  play.events=[{type:'shot',player:1,frame:10,shotForecast:{quality:{fieldGoalValue:1},secondChancePerShot:.14}}];
  assert.deepEqual(actionRecap(play,[],1,12),['SHOT','1.14','PPS']);
  assert.equal(releaseCard(play,[],12).selected,'SHOT');
  assert.ok(Math.abs(releaseCard(play,[],12).shot-1.14)<1e-10);
});

test('pass recap freezes the chosen receiver forecast before release and expires', () => {
  const play = {id:'p',events:[],frames:[
    {frame:8,geometry:{handler:1},passOptions:[{player:2,value:1.14,turnoverProbability:.08}]},
    {frame:11,geometry:{handler:1},passOptions:[{player:2,value:2,turnoverProbability:.9}]},
  ]};
  const passes=[{possession:'p',passer:1,receiver:2,start:10,end:15}];
  assert.equal(actionRecap(play,passes,1,9),null);
  assert.deepEqual(actionRecap(play,passes,1,12),['1.14','PASS']);
  assert.equal(actionRecap(play,passes,1,15),null);
  assert.equal(actionRecap(play,passes,1,20),null);
  assert.equal(actionRecap(play,passes,2,20),null);
  assert.equal(actionRecap(play,passes,1,61),null);
});

test('long passes cannot keep historical feedback over live labels for two seconds',()=>{
 const play={id:'p',events:[],frames:[{frame:8,geometry:{handler:1},passOptions:[{player:2,value:1.09}]}]};
 const passes=[{possession:'p',passer:1,receiver:2,start:10,end:50}];
 assert.ok(actionRecap(play,passes,1,22));
 assert.equal(actionRecap(play,passes,1,23),null);
 assert.equal(releaseCard(play,passes,23),null);
});
