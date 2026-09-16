import test from 'node:test';
import assert from 'node:assert/strict';
import {shotPps, releaseCard} from '../viewer/action-display.js';
import {playRecap} from '../viewer/play-recap.js';
test('release card and recap share FT-inclusive PPS without adding FT twice',()=>{
  const event={type:'shot',frame:10,player:1,shotForecast:{quality:{fieldGoalValue:1},freeThrowValue:.2,secondChancePerShot:.16,shotPlusSecondChance:1.36}};
  const play={events:[event],frames:[]};
  assert.equal(shotPps(event),1.36);
  assert.equal(releaseCard(play,[],11).shot,1.36);
  assert.equal(playRecap(play,11).total,1.36);
  assert.equal(playRecap(play,11).freeThrows,.2);
});
