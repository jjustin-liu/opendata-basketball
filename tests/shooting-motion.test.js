import test from 'node:test';
import assert from 'node:assert/strict';
import {shootingMotion} from '../viewer/shooting-motion.js';
test('shot pose gathers, extends at release, and returns to rest',()=>{
 const e=[{type:'shot',player:1,frame:100}];
 assert.equal(shootingMotion(e,2,100),null);
 assert.equal(shootingMotion(e,1,89),null);
 assert.equal(shootingMotion(e,1,126),null);
 assert.equal(shootingMotion(e,1,90).raise,0);
 assert.equal(shootingMotion(e,1,100).raise,1);
 assert.equal(shootingMotion(e,1,100).jump,.55);
 assert.equal(shootingMotion(e,1,125).raise,0);
 assert.equal(shootingMotion(e,1,125).jump,0);
 for(let f=90;f<=125;f+=.25){const p=shootingMotion(e,1,f);assert.ok(p.raise>=0 && p.raise<=1);assert.ok(p.jump>=0 && p.jump<=.55);}
});
