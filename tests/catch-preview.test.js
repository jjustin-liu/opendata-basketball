import test from 'node:test';
import assert from 'node:assert/strict';
import {passWithRisk} from '../viewer/pass-flight.js';
test('catch EPV is frozen before release and distinct from discounted pass value',()=>{
 const pass={start:10,passer:1,receiver:2,catchShot:{pps:1.3}};
 const frame={frame:8,geometry:{handler:1},passOptions:[{player:2,value:.9,completedEpv:1,turnoverProbability:.1}]};
 const future={...frame,frame:11,passOptions:[{player:2,value:9,completedEpv:9}]};
 const p=passWithRisk(pass,[frame,future]);
 assert.equal(p.completedEpv,1);assert.equal(p.epv,.9);assert.equal(p.catchShot.pps,1.3);
});
