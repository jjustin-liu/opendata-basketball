import test from 'node:test';
import assert from 'node:assert/strict';
import { capOffset } from '../viewer/curved-value.js';

test('EPV cap moves below only when the ball intersects its top label', () => {
  assert.equal(capOffset(2, 3, 1.2, { x: 0, y: -2, radius: 1 }), 2);
  assert.equal(capOffset(2, 3, 1.2, { x: 2, y: -2, radius: 1 }), 2);
  assert.equal(capOffset(2, 3, 1.2, { x: 0, y: 2, radius: 1 }), -2);
  assert.equal(capOffset(2, 3, 1.2, { x: 5, y: -2, radius: 1 }), -2);
  assert.equal(capOffset(2, 3, 1.2, null), -2);
});
