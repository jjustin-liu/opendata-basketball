import test from 'node:test';
import assert from 'node:assert/strict';
import { playRecap, playOutcome } from '../viewer/play-recap.js';

test('cumulative approximation weights time rather than counting overlapping forecasts', () => {
  const frames=Array.from({length:11},(_,i)=>({frame:i*5,turnover2:.1}));
  const play={frames,events:[]};
  assert.ok(Math.abs(playRecap(play,50).risk-.1)<1e-10);
  assert.equal(playRecap(play,50).coverage,1);
  frames.forEach(f=>f.reason='unsupported');
  assert.equal(playRecap(play,50).risk,null);
});
test('first shot components stay distinct and are not revealed before release', () => {
  const play={frames:[],events:[{type:'shot',frame:10,label:'Made 2PT',shotForecast:{quality:{fieldGoalValue:1.14},secondChancePerShot:.2}}]};
  assert.equal(playRecap(play,9).first,null);
  assert.equal(playRecap(play,10).first,1.14);
  assert.equal(playRecap(play,10).second,.2);
  assert.ok(Math.abs(playRecap(play,10).total-1.34)<1e-10);
  assert.equal(playOutcome(play),'MADE 2PT');
  assert.equal(playOutcome({...play,turnover:true}),'TURNOVER');
});
