import test from 'node:test';
import assert from 'node:assert/strict';
import { spaceControl, arrival, clarkMin, ndtr, MOTION } from '../viewer/space-control.js';

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

test('arrival time grows with distance, shrinks when moving toward the target', () => {
  const still = [2, 5, 10, 20].map((d) => arrival([1, -30, 0, true, 2], [0, 0], -30 - d, 0).t);
  for (let i = 1; i < still.length; i++) assert.ok(still[i] > still[i - 1]);
  assert.ok(arrival([1, -30, 0, true, 2], [-10, 0], -40, 0).t < still[2]);
  assert.ok(arrival([1, -30, 0, true, 2], [10, 0], -40, 0).t > still[2]);
  assert.ok(still[3] >= MOTION.reaction + 20 / MOTION.vMax - 1e-9);
  // extrapolated positions carry more timing noise
  assert.ok(arrival([1, -30, 0, false, 6], [0, 0], -40, 0).sigma > arrival([1, -30, 0, true, 6], [0, 0], -40, 0).sigma);
});

test('clark minimum sits below every input mean and ndtr is a CDF', () => {
  const items = [{ t: 1.0, sigma: 0.3 }, { t: 1.2, sigma: 0.2 }, { t: 3.0, sigma: 0.5 }];
  const { t, sigma } = clarkMin(items);
  assert.ok(t < 1.0 && t > 0.7);
  assert.ok(sigma > 0 && sigma < 0.3);
  assert.ok(Math.abs(ndtr(0) - 0.5) < 1e-6);
  assert.ok(Math.abs(ndtr(1.96) - 0.975) < 1e-4);
  assert.ok(Math.abs(ndtr(-1.96) - 0.025) < 1e-4);
});

test('control follows the nearer team and velocity is causal', () => {
  const grid = { cells: [[-40, 0, 1.5]] };
  const base = {
    frame: 5, period: 1, shotClock: 10, geometry: { handler: 1 },
    offense: [[1, -20, 0, true, 2], [2, -38, 0, true, 2], [3, 0, 20, true, 2], [4, 0, -20, true, 2], [5, 0, 0, true, 2]],
    defense: [[6, -30, 0, true, 2], [7, 0, 21, true, 2], [8, 0, -21, true, 2], [9, 0, 1, true, 2], [10, 0, -1, true, 2]],
  };
  const near = spaceControl(base, null, grid);
  assert.equal(near.area, 1);
  assert.ok(near.cells[0].control > 0.8);
  const swapped = { ...base, offense: base.offense.map((p) => p[0] === 2 ? [2, -30, 0, true, 2] : p), defense: base.defense.map((p) => p[0] === 6 ? [6, -38, 0, true, 2] : p) };
  assert.equal(spaceControl(swapped, null, grid).area, 0);
  // the previous sample only: a defender sprinting toward the cell wins it back
  const previous = { ...base, frame: 0, defense: base.defense.map((p) => p[0] === 6 ? [6, -27, 0, true, 2] : p) };
  const moving = spaceControl(base, previous, grid);
  assert.ok((moving.cells[0]?.control ?? 0) < near.cells[0].control);
});
