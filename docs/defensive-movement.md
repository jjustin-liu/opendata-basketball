# Defensive position sensitivity

The viewer only displays defensive shifts in set half-court states: all ten
players across midcourt and the ballhandler at least ten feet into the attacking
half. The defender and destination must be no more than two feet behind the
ballhandler toward midcourt. Transition and trailing-defender hints are hidden.

The movement overlay evaluates each tracked defender shifted 2 or 4 feet in
each cardinal direction. The held-out pooled-shot EPV model scores the original
and shifted geometry at the same clock as a first-stage screen. Candidates
outside the court, colliding with players, or outside model-support bounds are
excluded. Every surviving candidate then gets an offensive-response stress test:

- Compare staying versus shifting at the same two-second horizon.
- Score the holder staying, a pass to every teammate, and each teammate cutting
  4 or 8 feet toward the rim before receiving a pass (when there is room to cut).
- Include pass-turnover risk and budget 0.2s reaction, defender movement at
  12 ft/s, cuts at 10 ft/s, and a 40 ft/s pass plus 0.12s release.
- Reject if any modeled pass/cut gains more than 0.005 EPV from the defensive
  shift, or if any feasible response is unsupported or cannot fit the horizon.
- Compare the best tested offensive response before and after the shift; show
  only reductions of at least 0.01 EPV. Old untested files are never displayed.

This is a local sensitivity experiment, not a recommended defensive policy.
No defensive recovery or uncertainty in the estimated gain is modeled. Retaining
possession during the setup is assumed. These cuts do not exhaust offensive
responses or establish a causal benefit. Negative labels refer to offensive EPV.
Candidates are sampled once per
second and expire after 0.4 seconds or appreciable defender/ball movement.

Offensive movement retains its three response scenarios but now accepts a gain
of 0.01 rather than 0.05 EPV in every scenario. Its markers persist to the next
0.4-second simulation sample, rather than disappearing halfway between samples.
