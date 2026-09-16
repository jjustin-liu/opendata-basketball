import test from 'node:test';
import assert from 'node:assert/strict';
import {playerColor} from '../viewer/player-color.js';
test('missing estimates keep color briefly and fade to neutral without returning a value',()=>{
 let s=playerColor(null,'rgb(180,65,59)',0,'p');
 s=playerColor(s,null,5,'p');
 assert.ok(s.shown[0]>150);
 for(let t=10;t<=50;t+=5)s=playerColor(s,null,t,'p');
 assert.ok(Math.abs(s.shown[0]-112)<2);
 assert.equal(s.value,undefined);
});
test('catch colors blend and seeks and new possessions reset memory',()=>{
 const a=playerColor(null,'rgb(180,65,59)',10,'p');
 const b=playerColor(a,'rgb(26,135,85)',11,'p');
 assert.ok(b.shown[0]>26 && b.shown[0]<180);
 assert.equal(playerColor(a,null,9,'p').fill,'rgb(112,119,117)');
 assert.equal(playerColor(a,null,11,'q').fill,'rgb(112,119,117)');
});
