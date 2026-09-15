# Valuable space overlay

Enable **Valuable space** in the court toolbar (views 1–4 and 6). Blue cells show arrival advantage multiplied by empirical field-goal value, at a threshold of 0.5. The readout counts their area in square feet. This is exploratory geometry, not an EPV input or calibrated scoring probability.

- One-foot cells within the offensive half court, with a two-second offensive arrival horizon, shortened by the shot clock.
- Current velocity estimated from adjacent replay samples no more than 0.4 seconds apart. Directional speed is capped at 14 ft/s. Constant acceleration 10 ft/s² up to 14 ft/s for either team; identical assumptions avoid inventing player-specific mobility.
- The fastest nominal arrival on each team determines the arrival margin. A logistic approximation softens it using the two players' position errors. Conversion from SkillCorner's 90% radial error bound assumes isotropic Gaussian location error (divide by 2.146); timing noise has a 0.12-second floor. This approximation does not model the joint distribution of all ten arrival times or validate real control probability.
- Shot values are spatial Gaussian-weighted averages of SkillCorner expected field-goal points from the other nine games. Use matching 2PT/3PT class, 8-foot neighborhood, bandwidth 3 feet, minimum total kernel weight 3. There are 1,225 eligible non-fouled release samples with replay position within five frames. Unsupported cells are omitted.
- These are observed-shot values, not isolated open-shot quality. Player-specific shooting ability, pass delivery, interception, route obstruction, fouls, and rebounds are not included. Consequently the overlay must not be interpreted as a pass recommendation or added to possession EPV.
- The area is the sum of qualifying cell areas, not a sum of expected possession points across mutually exclusive destinations.

Rebuild source grids with `.venv/bin/python scripts/build_space_value.py`. This standalone exploratory grid is not yet part of the main EPV build. Checks cover reversed team arrival advantage and missing-state suppression; browser verification confirmed the toggle and area readout.
