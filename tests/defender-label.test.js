import test from 'node:test';
import assert from 'node:assert/strict';
import { defenderProbability } from '../viewer/defender-label.js';
test('reads separate player probabilities without mixing steal and block', () => {
  const frame = {stealForecast:{enabled:true,defenders:[{player:1,probability:.02}]},blockForecast:{enabled:true,defenders:[{player:1,probability:0},{player:2,probability:.03}]}};
  assert.equal(defenderProbability(frame,'steal',1),.02);
  assert.equal(defenderProbability(frame,'block',1),0);
  assert.equal(defenderProbability(frame,'block',2),.03);
  assert.equal(defenderProbability(frame,'steal',2),null);
  frame.blockForecast.enabled=false;
  assert.equal(defenderProbability(frame,'block',2),null);
});

import {defenderThreatReference, defenderThreatStrength} from '../viewer/defender-label.js';
test('reference is fixed at initial supported state, independent of later risks', () => {
  const frames=[{}, {stealForecast:{enabled:true,defenders:[{probability:.002},{probability:.004}]}}];
  const reference=defenderThreatReference(frames);
  assert.equal(reference.steal,.003);
  frames.push({stealForecast:{enabled:true,defenders:[{probability:.9}]}});
  assert.equal(defenderThreatReference(frames).steal,.003);
});
test('relative threat grows with probability but negligible risks stay small', () => {
  assert.ok(defenderThreatStrength(.004,.003,'steal') > defenderThreatStrength(.001,.003,'steal'));
  assert.ok(defenderThreatStrength(.00001,.00001,'block') < .02);
  assert.equal(defenderThreatStrength(null,.003,'steal'),0);
  assert.equal(defenderThreatStrength(1,.003,'steal'),1);
});

import {rimWingAngle} from '../viewer/defender-label.js';
test('wings are perpendicular to rim bearing before camera projection', () => {
  const project=(x,y)=>[x,y];
  for (const [x,y] of [[0,0],[-20,15],[-35,-20]]) {
    const angle=rimWingAngle(project,x,y);
    assert.ok(Math.abs(Math.cos(angle)*(-40.75-x)+Math.sin(angle)*(-y))<1e-10);
  }
});
test('wing orientation follows tilted court projection and stays finite at rim', () => {
  const project=(x,y)=>[x+.12*y,-.66*y];
  assert.ok(Math.abs(rimWingAngle(project,0,0)-Math.atan2(.66,-.12))<1e-10);
  assert.ok(Number.isFinite(rimWingAngle(project,-40.75,0)));
});

import {drawDefenderLabel} from '../viewer/defender-label.js';
test('equal threat geometry is independent of position chip radius', () => {
  const frame={stealForecast:{enabled:true,defenders:[{player:1,probability:.002}]},blockForecast:{enabled:true,defenders:[{player:1,probability:.0005}]}};
  function capture(radius,wings) {
    const paths=[];let chipStarted=false;
    const ctx=new Proxy({}, {get(_,key) {
      if(key==='measureText')return text=>({width:text.length*5});
      if(key==='getTransform')return ()=>({a:1,b:0});
      return (...args)=>{if(key==='arc')chipStarted=true;if(!chipStarted&&['moveTo','lineTo','bezierCurveTo'].includes(key))paths.push([key,...args]);};
    },set(){return true;}});
    drawDefenderLabel(ctx,0,0,radius,{name:'Test'},frame,1,'1',true,{unit:20,wings,reference:{steal:.002,block:.0005}});
    return paths;
  }
  for(const wings of [true,false]) {
    assert.ok(capture(16,wings).length>0);
    assert.deepEqual(capture(16,wings),capture(24,wings));
  }
});

import {defenderForecast} from '../viewer/defender-label.js';
test('action threat follows selected pass and never silently falls back to two-second risk', () => {
  const make=(receiver,p)=>({enabled:true,receiver,defenders:[{player:1,probability:p}]});
  const frame={actionDefense:{passes:[make(2,.02),make(3,.08)],shot:make(null,.12)},passOptions:[{player:2,value:1.2},{player:3,value:1}],stealForecast:make(null,.9)};
  assert.equal(defenderProbability(frame,'steal',1),.02);
  assert.equal(defenderProbability(frame,'steal',1,3),.08);
  assert.equal(defenderProbability(frame,'block',1,3),.12);
  frame.actionDefense.passes=[];
  assert.equal(defenderForecast(frame,'steal'),null);
});
