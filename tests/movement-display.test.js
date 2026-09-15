import test from 'node:test';
import assert from 'node:assert/strict';
import { smoothMovement } from '../viewer/movement-ideas.js';
test('movement display eases destinations and resets on a seek, player change, or missing idea',()=>{
  const old={player:1,to:[0,0]}, next={player:1,to:[8,0]};
  const initial=smoothMovement(null,old,10,'p');
  const eased=smoothMovement(initial,next,12,'p');
  assert.ok(eased.idea.to[0]>0 && eased.idea.to[0]<8);
  assert.deepEqual(smoothMovement(eased,next,5,'p').idea.to,[8,0]);
  assert.equal(smoothMovement(eased,null,13,'p'),null);
  assert.deepEqual(smoothMovement(eased,{...next,player:2},13,'p').idea.to,[8,0]);
});
