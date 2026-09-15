import test from "node:test";
import assert from "node:assert/strict";
import { playerProfile, heightFeet } from "../viewer/player-profile.js";
test("3PR uses full sample consistently at every replay time", () => {
  const game = {
    players: { 1: { position: "C", sampleFga: 20, sampleThreePa: 7, sampleOffPossessions: 100 } },
  };
  for (const frame of [0, 20, 10000]) {
    const p = playerProfile(game, 1, frame);
    assert.equal(p.fga, 20);
    assert.equal(p.rate, 0.35);
    assert.equal(p.threePer100, 7);
  }
  assert.equal(playerProfile(game, 3, 20).rate, null);
});
test("listed heights scale proportionately in court feet", () => {
  assert.equal(
    heightFeet({ heightCm: 217 }) / heightFeet({ heightCm: 189 }),
    217 / 189,
  );
  assert.equal(heightFeet({}), 6.5);
});
