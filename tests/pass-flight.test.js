import test from 'node:test';
import assert from 'node:assert/strict';
import {activePass,flightLabel} from '../viewer/pass-flight.js';
test('pass annotation spans release to catch only',()=>{
 const p={possession:'a',start:20,end:34,passer:1,receiver:2};
 assert.equal(activePass([p],'a',19),null);
 assert.equal(activePass([p],'b',25),null);
 assert.equal(activePass([p],'a',20),p);
 assert.equal(activePass([p],'a',33.9),p);
 assert.equal(activePass([p],'a',34),null);
 assert.equal(flightLabel(p,1),'PASS');assert.equal(flightLabel(p,2),'REC');assert.equal(flightLabel(p,3),'');
 assert.equal(flightLabel({...p,receiver:null},2),'');
});
