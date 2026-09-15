import test from "node:test";
import assert from "node:assert/strict";
import { interpolateFrame } from "../viewer/playback.js";
const a = {
  frame: 100,
  period: 1,
  gameClock: 200,
  shotClock: 12,
  epv: 1.1,
  turnover2: 0.05,
  offense: [
    [1, 0, 0, 1, 1, "1"],
    [2, 10, 0, 1, 1, "2"],
  ],
  defense: [[3, 5, 5, 1, 1, "3"]],
  ball: [0, 0, 3, 1, 0.5],
};
const b = {
  ...a,
  frame: 105,
  gameClock: 199.8,
  shotClock: 11.8,
  epv: 1.3,
  turnover2: 0.1,
  offense: [
    [2, 12, 0, 1, 1, "2"],
    [1, 2, 4, 1, 1, "1"],
  ],
  defense: [[3, 7, 5, 1, 1, "3"]],
  ball: [2, 2, 5, 1, 0.5],
};
test("interpolates player identities and ball between 5 Hz samples", () => {
  const f = interpolateFrame(a, b, 0.5);
  assert.deepEqual(f.offense[0].slice(0, 3), [1, 1, 2]);
  assert.deepEqual(f.offense[1].slice(0, 3), [2, 11, 0]);
  assert.deepEqual(f.ball.slice(0, 3), [1, 1, 4]);
  assert.equal(f.shotClock, 11.9);
});
test("never invents interpolated EPV or turnover predictions", () => {
  const f = interpolateFrame(a, b, 0.5);
  assert.equal(f.epv, a.epv);
  assert.equal(f.turnover2, a.turnover2);
});
test("does not interpolate over missing tracking or period boundaries", () => {
  assert.equal(interpolateFrame(a, { ...b, frame: 150 }, 0.5), a);
  assert.equal(interpolateFrame(a, { ...b, period: 2 }, 0.5), a);
});
test("does not mutate source frames or interpolate a shot-clock reset", () => {
  const source = JSON.stringify(a);
  const f = interpolateFrame(a, { ...b, shotClock: 24 }, 0.5);
  assert.equal(f.shotClock, 12);
  assert.equal(JSON.stringify(a), source);
});
