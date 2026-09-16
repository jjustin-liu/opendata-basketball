import test from 'node:test';
import assert from 'node:assert/strict';
import {simulatedMovement,defensiveMovement} from '../viewer/movement-simulation.js';
test('only robust current estimates for off-ball players are shown',()=>{
  const f={frame:105,geometry:{handler:1},offense:[[1,0,0],[2,1,1],[3,2,2]]};
  const data={plays:{p:{100:[{player:2,low:.08,gain:.1},{player:3,low:.04,gain:.3}]}}};
  assert.equal(simulatedMovement(data,'p',f).player,2);
  assert.equal(simulatedMovement(data,'p',f,3).player,3);
  assert.equal(simulatedMovement(data,'p',{...f,frame:109}).player,2);
  assert.equal(simulatedMovement(data,'p',{...f,frame:110}),null);
  assert.equal(simulatedMovement(data,'p',{...f,reason:'shot'}),null);
});

test('defense selects EPV reduction and rejects stale shifted positions',()=>{
 const f={frame:105,geometry:{handler:1},ball:[-20,0],offense:[[1,-20,0],[2,-25,5],[3,-30,10],[4,-32,-10],[5,-35,-5]],defense:[[8,-22,2],[9,-28,5],[10,-31,10],[11,-33,-10],[12,-36,-5]]};
 const data={version:2,plays:{p:{100:[{player:8,responseChecked:true,gain:.02,origin:[-22,2],ball:[-20,0],to:[-24,2]}]}}};
 assert.equal(defensiveMovement(data,'p',f).side,'defense');
 assert.equal(defensiveMovement(data,'p',f).gain,.02);
 assert.equal(defensiveMovement({...data,version:1},'p',f),null);
 assert.equal(defensiveMovement(data,'p',{...f,frame:115}),null);
 assert.equal(defensiveMovement(data,'p',{...f,defense:[[8,8,8]]}),null);
 assert.equal(defensiveMovement(data,'p',{...f,reason:'pass'}),null);
 assert.equal(defensiveMovement(data,'p',{...f,offense:f.offense.map((p,i)=>i===4?[5,2,0]:p)}),null);
 assert.equal(defensiveMovement(data,'p',{...f,defense:f.defense.map((p,i)=>i===0?[8,-10,2]:p)}),null);
});
