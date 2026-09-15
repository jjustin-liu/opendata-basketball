import test from 'node:test';
import assert from 'node:assert/strict';
import {displayBall,shotHandPosition} from '../viewer/ball-display.js';
import {shootingMotion} from '../viewer/shooting-motion.js';
const events=[{type:'shot',player:1,frame:100}],profile=()=>({heightCm:200});
const f=n=>({frame:n,period:1,geometry:{handler:1},offense:[[1,-20,0,true,0,1]],defense:[],ball:[-25,2,8,1,0],gameClock:10,shotClock:5});
test('release begins at hands and returns to original tracking without mutation',()=>{
 const frames=[f(95),f(100),f(105),f(110)];
 const before=JSON.stringify(frames);
 const hand=shotHandPosition(frames[1].offense[0],profile(),shootingMotion(events,1,100));
 assert.deepEqual(displayBall(frames[1],frames,events,100,profile),hand);
 assert.deepEqual(displayBall(frames[3],frames,events,108,profile),frames[3].ball.slice(0,3));
 const left=displayBall(frames[0],frames,events,99.999,profile);
 assert.ok(Math.hypot(...left.map((v,i)=>v-hand[i]))<.001);
 assert.equal(JSON.stringify(frames),before);
});
test('does not attach incoming pass or unrelated tracking to a shooter',()=>{
 const frame=f(95);frame.geometry.handler=2;
 assert.deepEqual(displayBall(frame,[frame],events,95,profile),frame.ball.slice(0,3));
 assert.deepEqual(displayBall(frame,[frame],[],95,profile),frame.ball.slice(0,3));
});
