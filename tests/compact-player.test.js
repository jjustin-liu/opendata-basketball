import test from 'node:test';
import assert from 'node:assert/strict';
import {highVolumeThree, frequentDriver, tendencyLabels} from '../viewer/compact-player.js';
test('3P badge needs established shooting volume',()=>{
  assert.equal(highVolumeThree({possessions:100,threePer100:6}),true);
  assert.equal(highVolumeThree({possessions:99,threePer100:12}),false);
  assert.equal(highVolumeThree({possessions:500,threePer100:5}),false);
  assert.equal(highVolumeThree({possessions:500,threePer100:null}),false);
});
test('driver label requires season exposure and can share the arc with 3P',()=>{
  assert.equal(frequentDriver({drivePossessions:500,drivesPer100:20}),true);
  assert.equal(frequentDriver({drivePossessions:499,drivesPer100:30}),false);
  assert.equal(frequentDriver({drivePossessions:1000,drivesPer100:19}),false);
  assert.equal(tendencyLabels({possessions:1000,threePer100:8,drivePossessions:1000,drivesPer100:22}),'3P · DRIVER');
});
