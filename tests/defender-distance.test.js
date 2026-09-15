import test from 'node:test';
import assert from 'node:assert/strict';
import { nearestDefenderDistance, closestDefenderToBall } from '../viewer/defender-distance.js';

test('ball distance selects a single defender and follows the ball during a pass', () => {
  const frame = { ball: [0, 0, 3], defense: [[3, 3, 4], [4, 12, 0]] };
  assert.equal(closestDefenderToBall(frame).defender[0], 3);
  assert.equal(closestDefenderToBall(frame).distance, 5);
  frame.ball = [10, 0, 6];
  assert.equal(closestDefenderToBall(frame).defender[0], 4);
  assert.equal(closestDefenderToBall(frame).distance, 2);
  assert.equal(closestDefenderToBall({ ball: null, defense: [] }), null);
});

test('nearest distance uses each offensive player and current defender positions', () => {
  const defense = [[3, 3, 4], [4, 12, 0]];
  assert.equal(nearestDefenderDistance([1, 0, 0], defense), 5);
  assert.equal(nearestDefenderDistance([2, 10, 0], defense), 2);
  defense[1][1] = 10;
  assert.equal(nearestDefenderDistance([2, 10, 0], defense), 0);
  assert.equal(nearestDefenderDistance([1, 0, 0], []), null);
});
