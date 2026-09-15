import test from 'node:test';
import assert from 'node:assert/strict';
import { spaceControl } from '../viewer/space-control.js';

test('valuable space excludes the handler and follows off-ball teammates', () => {
  const frame = {
    frame: 0, shotClock: 10, geometry: { handler: 1 },
    offense: [[1, -30, 0], [2, 20, 20], [3, 21, 20], [4, 22, 20], [5, 23, 20]],
    defense: [[6, 0, 20], [7, 1, 20], [8, 2, 20], [9, 3, 20], [10, 4, 20]],
  };
  const grid = { cells: [[-30, 0, 2]] };
  assert.equal(spaceControl(frame, null, grid).area, 0);
  frame.geometry.handler = 2;
  assert.equal(spaceControl(frame, null, grid).area, 1);
  frame.geometry.handler = null;
  assert.equal(spaceControl(frame, null, grid).area, 0);
});
