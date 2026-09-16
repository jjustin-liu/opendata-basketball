# Experimental movement EPV

The movement marker now displays an estimated **move-then-pass gain**, not the older
geometry score. `~+0.10 EPV` is the mean difference across three specified defensive
responses. Every response must improve by at least 0.01 points to show a marker.
Amber negative markers now also show [defensive position sensitivity](defensive-movement.md).

## Comparison

1. Two candidate generators propose off-ball destinations every 0.4 seconds. The
   geometry heuristic screens 4/6/8-foot moves and retains one per player. The
   [exploitable-space field](space-field.md) adds up to two hole centroids per
   player: empty regions where an attacker would arrive before any defender and
   an open shot is worth more than 0.5 points, between 3 and 20 ft away, at
   10 ft/s. Accepted markers carry `source: "grid"` or `"hole"`. This is a
   restricted search, not optimization over every route or action.
2. Compare that player moving to the candidate versus staying in place. Both wait
   the same movement duration before the holder passes to that player.
3. Test defenders staying, continuing their observed velocity (capped at 12 ft/s),
   or the nearest defender closing toward that branch's receiver location after
   a 0.2-second reaction delay while others continue their velocity.
4. Predict pass flight time with the existing held-out timing model, including the
   0.12-second release. Both branches are scored at the later catch time, so they
   have identical game and shot clocks. The receiver stops at the destination;
   the earlier catch is held until the common horizon.
5. Score the resulting controlled catch with the shooting-aware EPV model and
   multiply by one minus the separately predicted pass-turnover probability.
   Subtract stay value from move value for each defensive response.

The holder and other offensive players stay in place. **This is conditional on
keeping possession during the wait.** It does not account for a turnover while
waiting, movement-induced fouls, or the value of a better alternative action.
The same receiver is used in both branches; teammate benefits are not added as
synthetic points. The simulated catch value is remaining-possession EPV, not PPS.

## Guardrails and validation

- Each replay game is excluded from EPV, shot, pass-risk, and timing training.
  EPV training uses shooting inputs that also exclude each training row's game,
  matching the nested fitting procedure in the existing build.
- Reject invalid catch projections, expired clocks, and scenarios outside the
  training 0.5–99.5 percentiles for shot clock, rim distance, nearest defender
  distance, and teammate spacing. These checks are partial support checks, not
  proof that every simulated state is realistic.
- No future replay positions, movement outcomes, or shot results enter simulation.
  The old screen uses the already-built other-game shot-value surface.
- The viewer holds a source estimate until the next 0.4-second sample and hides it during
  passes, shots, uncertain control, or when the recommended player has the ball.
- Tests cover equal-clock comparisons, zero-movement invariance, clock expiry,
  source immutability, future-history exclusion, all-response filtering, and stale
  UI suppression.

The existing EPV model has not beaten the constant benchmark overall. A positive
scenario gain does **not** establish a causal benefit or validated movement policy.
Output reports count screened, supported, and accepted scenarios only; they are
not outcome-based policy evaluation.

## Rebuild

After the normal model build and `.venv/bin/python -m epv.space_field`:

```sh
node scripts/build_movement_candidates.mjs
.venv/bin/python -m epv.movement
```

For a single game, append `--game 191313`. Results are generated in
`viewer/data/movement/`; model caches and diagnostic reports stay in ignored
`.cache/` and `artifacts/` directories. The full build runs both movement steps.
