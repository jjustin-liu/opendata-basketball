# Shooting-foul audit

Game-held-out audit of 1,431 eligible attempts (136 fouls). The current model is
approximately right overall: 9.44% predicted versus 9.50% observed. That masks a
three-point overprediction:

| Group | Attempts / fouls | Observed | Predicted |
|---|---:|---:|---:|
| Threes | 527 / 8 | 1.52% | 2.69% |
| Threes, defender <3 ft | 47 / 2 | 4.26% | 6.55% |
| Threes, defender ≥3 ft | 480 / 6 | 1.25% | 2.32% |

Predicted rates mix conditional made/missed-shot predictions using vendor SQ.
These release-sample checks do not validate projected C&S states. Eight three-point
fouls are far too few to establish fine player/contest-specific rates.

## Structural concerns

- The same conditional logistic models pool twos and threes. Continuous location
  features can approximate shot type, but there is no explicit three-point indicator.
- Shooter effects and season FTA/FGA apply across shot types. They can transfer
  a player's interior foul-drawing tendency to perimeter attempts.
- Geometry lacks shot subtype (C&S versus drive), contest hand/body orientation,
  and closing momentum. C&S imposes a two-foot stopping gap; proximity alone
  cannot distinguish a legal contest from contact.
- The fit's target is shooting fouls at recorded attempts, not the success of
  hypothetical catch-and-shoot actions. Overall Brier improvement is not proof
  of calibrated three-point or C&S foul rates.

## Candidate tested, not deployed

Adding an explicit three-point indicator lowers held-out conditional Brier from
0.078091 to 0.077728 overall and from 0.015487 to 0.015096 on threes. However, a
simple held-out shot-type/make-miss baseline scores 0.015090 on threes—essentially
the same. This does not justify claiming a reliable individualized three-point
foul model. A separate, strongly pooled three-point foul component is a sensible
next candidate, but needs held-out validation before deployment.

## Display change

C&S now uses field-goal points plus field-goal rebound continuation only; no foul
or FT value. In game 191313, possession 2-60, frame 47910, Dubljević's preview was
1.1911 with foul value. The old components were 0.8842 field-goal points, 0.1929 FT
points, 0.1118 foul-adjusted FG rebound points, and 0.0022 FT rebound points.
The no-foul version is approximately 1.01 (0.8842 FG + 0.1258 rebounds).
The main shooting-foul model and foul-inclusive SHOT/recap values remain unchanged.

Reproduce with `.venv/bin/python -m epv.foul_audit`. The numerical diagnostic is
written to `artifacts/foul-audit.json`; it does not modify model outputs.
