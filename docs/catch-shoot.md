# In-flight receiver forecast

Before release, the receiver displays risk-discounted pass EPV (`value`). During
flight, a smoothstep transition moves from the frozen pre-release pass EPV to
`completedEpv`, the conditional catch value, over the recorded flight interval.
Both endpoints come from the last supported pre-release option within 0.4 seconds.
This is a visual interpolation, not a fitted conditional interception-risk model;
it does not use the eventual pass outcome. C&S remains conditional on a catch.

`epv.catch_shoot` separately scores the projected catch coordinates and clock,
followed by a 0.5-second stationary gather/release. The nearest defender at catch
reacts after 0.2 seconds, closes at 12 ft/s, and stops two feet away. Other players
stay at projected catch positions during release. No actual future catch or
defender coordinates enter scoring. Other-game SQ and rebound models
produce the shot estimate. C&S now excludes all foul and free-throw value:
`P(make) × shot points + (1 − P(make)) × P(ORB | miss) × continuation`.
The rebound term is not reduced by a foul model. First-chance points, second-chance
value and ORB probability are exported separately. Threes require 20 other-game season attempts.

This is an approximate C&S scenario, not a validated action policy. C&S PPS can
exceed catch EPV: these are separately fitted models, not a Bellman-consistent
optimal-action model. Season inputs remain retrospective rather than pregame.

Rebuild with `.venv/bin/python -m epv.catch_shoot` after profiles and foul value;
the normal build includes it. Forecasts are stored on manifest recorded passes.

The floor stamp is replay-only: the half-distance point along the recorded ball
path projected onto the floor, with interpolated release/end boundaries. Tracking
gaps over 0.4 seconds suppress it. Future replay samples locate the annotation but
never supply its risk, conditional catch EPV, or C&S forecast.
# Perimeter previews

Supported three-point pass options now carry the same conditional catch-and-shoot forecast on every controlled-ball frame, not just at recorded pass releases. The court shows conditional catch EPV above and C&S PPS below the off-ball player. Existing evidence gates remain: at least 20 season three-point attempts outside the tracked games, projected distance at most 32 feet, and enough shot clock for delivery plus release. Missing estimates are not filled from future frames.
