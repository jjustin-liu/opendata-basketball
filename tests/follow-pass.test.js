import test from 'node:test';
import assert from 'node:assert/strict';
import {followPass} from '../viewer/follow-pass.js';
const pass={start:20,end:30,passer:1,receiver:2};
test('follows ball in flight then hands off at catch',()=>{
 let state=followPass(null,1,pass,20); assert.equal(state.ball,true);assert.equal(state.player,1);
 state=followPass(state,1,pass,25);assert.equal(state.ball,true);
 state=followPass(state,1,null,30);assert.equal(state.ball,false);assert.equal(state.player,2);
});
test('overhead, unrelated player, failed pass and backward seek do not switch receiver',()=>{
 assert.equal(followPass(null,null,pass,20).ball,false);
 assert.equal(followPass(null,3,pass,20).ball,false);
 let state=followPass(null,1,{...pass,receiver:null},20);
 assert.equal(followPass(state,1,null,30).player,1);
 state=followPass(null,1,pass,25);
 assert.equal(followPass(state,1,null,10).pending,null);
 assert.equal(followPass(state,3,pass,26).pending,null);
});
