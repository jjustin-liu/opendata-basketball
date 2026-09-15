import test from 'node:test';
import assert from 'node:assert/strict';
import {shotReview} from '../viewer/shot-review.js';
const event={type:'shot',frame:100,player:1,shotClock:6,shotForecast:{quality:{fieldGoalValue:1.1},secondChancePerShot:.2,offensiveReboundProbability:.3}};
const frame=(n,handler=1)=>({frame:n,geometry:{handler},offense:[[1],[2]],passOptions:[{player:2,value:1.2}]});
test('review uses release values and strictly pre-shot pass, persists after shot',()=>{
 const play={events:[event],frames:[frame(95),{...frame(100),passOptions:[{player:2,value:9}]}]};
 assert.equal(shotReview(play,99),null);
 const review=shotReview(play,500);
 assert.equal(review.clock,6); assert.equal(review.pass.value,1.2);assert.equal(review.passAge,.2);
 assert.ok(Math.abs(review.total-1.3)<1e-10);
});
test('does not borrow stale passes or passes from another ballhandler',()=>{
 assert.equal(shotReview({events:[event],frames:[frame(89)]},100).pass,null);
 assert.equal(shotReview({events:[event],frames:[frame(95,3)]},100).pass,null);
});
