import test from 'node:test';
import assert from 'node:assert/strict';
import {auditShot} from '../viewer/decision-audit.js';
const event={type:'shot',frame:100,player:1,shotClock:10,shotForecast:{quality:{fieldGoalValue:1},secondChancePerShot:.1}};
const frame=(n)=>({frame:n,geometry:{handler:1},offense:[[1],[2]],shot:{shotPlusSecondChance:.9},passOptions:[{player:2,value:1.4,turnoverProbability:.03,route:{reachableDefenders:0}}]});
test('flags sustained advantage over the release shot, independent of shot outcome',()=>{
 const play={frames:[70,75,80].map(frame)};
 const a=auditShot(play,event);assert.equal(a.kind,'missed-pass');assert.equal(a.window.start,70);assert.ok(Math.abs(a.window.gain-.3)<1e-8);
 assert.deepEqual(a,auditShot(play,{...event,label:'Made'}));
});
test('rejects fleeting, obstructed, stale and last-instant windows',()=>{
 for(const frames of [[frame(70),frame(75)],[frame(70),frame(80),frame(90)],[frame(95),frame(100),frame(105)]])assert.equal(auditShot({frames},event).window,null);
 const frames=[70,75,80].map(frame);frames[1].passOptions[0].route.reachableDefenders=1;
 assert.equal(auditShot({frames},event).window,null);
});
test('low-value flag requires clock and is not a missed-pass claim',()=>{
 const e={...event,shotForecast:{quality:{fieldGoalValue:.7},secondChancePerShot:.1}};
 assert.equal(auditShot({frames:[]},e).kind,'low-shot');
 assert.equal(auditShot({frames:[]},{...e,shotClock:2}).kind,'unflagged');
});

test('comparison and rewind identify the exact minimum-edge frame',()=>{
 const frames=[70,75,80].map(frame);
 frames[1].shot.shotPlusSecondChance=1.0;
 frames[1].passOptions[0].value=1.3;
 const w=auditShot({frames},event).window;
 assert.equal(w.frame,75);
 assert.equal(w.shot,frames[1].shot.shotPlusSecondChance);
 assert.equal(w.pass,frames[1].passOptions[0].value);
 assert.notEqual(w.frame,w.start);
});

test('does not flag a pass below the shot the player created',()=>{
 const frames=[70,75,80].map(frame);
 frames.forEach(f=>{f.passOptions[0].value=1.33; f.shot.shotPlusSecondChance=.92;});
 const shot={...event,shotForecast:{quality:{fieldGoalValue:1.25},secondChancePerShot:.14}};
 assert.equal(auditShot({frames},shot).window,null);
 assert.equal(auditShot({frames},shot).kind,'unflagged');
 assert.equal(auditShot({frames},{...shot,shotForecast:null}).kind,'unavailable');
});
