# Valuable space overlay

Valuable space considers off-ball teammates only, excluding the identified ball handler. Frames without an identified handler are suppressed. Its soft blue surface can appear together with the ball handler's stronger orange drive-space surface.

Enable **Valuable space** in the court toolbar (views 1–4 and 6). Blue cells show the probability that an off-ball attacker reaches the cell before any defender, multiplied by the open-shot value of the cell, at a threshold of 0.5 points. The readout counts their area in square feet. This is exploratory geometry, not an EPV input or calibrated scoring probability.

- One-foot cells within the offensive half court, with a two-second offensive arrival horizon, shortened by the shot clock.
- Movement and uncertainty follow the [exploitable-space field](space-field.md): 0.2 s reaction, 16 ft/s² acceleration, 20 ft/s cap, a player moving away must stop first. Velocity comes from the previous replay sample only (no more than 0.4 s earlier), never from future frames.
- Each team's first arrival is the Clark moment-matched minimum of its arrival-time distributions; control is the normal probability that the offensive minimum precedes the defensive one. Timing noise combines a 0.15 s floor, SkillCorner's 90 % radial error bound (divided by 2.146 for an isotropic Gaussian, inflated 1.5× when extrapolated) at 10 ft/s, and 10 % of the arrival time.
- Cell values are open or lightly contested shot points from the other nine games, kernel-smoothed within the same 2/3-point zone, mirrored across the court axis and shrunk toward a parametric prior so every cell has a value. They score the spot, not the ball: pass delivery, interception, fouls and rebounds are not included, so the overlay is not a pass recommendation and must not be added to possession EPV.
- The area is the sum of qualifying cell areas, not a sum of expected possession points across mutually exclusive destinations.

Rebuild the grids with `.venv/bin/python -m epv.space_field` (part of the full build). Checks cover handler exclusion, arrival-time monotonicity, the Clark minimum, control following the nearer team, and causal velocity (`tests/space-control.test.js`).
