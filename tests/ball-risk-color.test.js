import test from 'node:test';
import assert from 'node:assert/strict';
import { ballRiskColor } from '../viewer/ball-risk-color.js';

test('ball risk blends gradually above six percent and clamps at fifteen', () => {
  assert.equal(ballRiskColor(null), 'rgb(242,180,64)');
  assert.equal(ballRiskColor(.06), 'rgb(242,180,64)');
  assert.equal(ballRiskColor(.105), 'rgb(241,119,61)');
  assert.equal(ballRiskColor(.15), 'rgb(239,57,57)');
  assert.equal(ballRiskColor(.8), ballRiskColor(.15));
  assert.notEqual(ballRiskColor(.09), ballRiskColor(.11));
});
