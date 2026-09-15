# Movement exploration

Enable **Movement ideas** in views 1–4 or 6 and click an off-ball teammate. The search is restricted to that player, including players without a currently supported pass option. Without a selected teammate, the best candidate across offense is shown. Selection also controls the existing pass preview.

Blue arrows indicate **Clear improvement** within the heuristic; amber arrows indicate **Worth exploring**, with a response-dependent benefit. The toolbar names the player and opportunity. Hover the explanation for move length, duration and tradeoffs. No positive supported alternative produces no arrow. This does not prove that staying is optimal.

## Evaluation

Sample 16 directions at 4, 6 and 8 ft from each eligible player. Retain the existing boundary, shot clock, tracking quality, stationary path obstruction, teammate crowding and shooting-volume checks. Assume player movement at 10 ft/s and ball flight at 40 ft/s plus 0.12s release delay. Use the other-game empirical shot-value grid described in valuable-space.md.

Compare moving versus staying over the same horizon under three defensive responses: hold, continue capped current velocity, and nearest defender closeout after 0.2s. Closeout targets the candidate for moving and the original position for staying. Other defenders continue their motion. Defender speed is capped at 12 ft/s. Ballholder and other teammates remain stationary.

The player's own score combines observed shot value, receiver separation and pass-route clearance. Teammate benefit is the change in the mean of the two highest shot-value × separation scores among the remaining offensive players, including the holder. It can capture space opened when a defender follows the mover, but is not a full team-action model and does not include pass delivery to those teammates. Team benefit receives a fixed heuristic weight of 0.6; scenario means assume equal weights, not learned response probabilities.

**Worth exploring** requires positive mean composite gain greater than 0.015, with at least one scenario improving by more than 0.02. Ranking uses mean gain plus 0.25 times negative worst-case gain. Some responses may erase the benefit or leave a pass contested; the explanation flags this.

**Clear improvement** additionally retains the original robust thresholds: own gain at least 0.12, separation gain at least 1.5 ft and modeled route margin at least 0.3 ft under every response, with minimum composite gain above 0.05. These thresholds do not establish a validated causal improvement.

The previous consecutive-frame winner gate was removed for interactive exploration. Results can change as the state changes. Unsupported control, short clock, recorded pass flight and recent shots still suppress arrows. Nothing uses future tracking or actual play outcomes.

## Limits and verification

This is an exploratory geometric heuristic, not a learned policy, a calibrated counterfactual or an EPV improvement claim. Existing model values remain unchanged. Fixed motion assumptions, sparse shooting evidence, no screens or moving collisions and incomplete teammate action valuation limit recommendations.

Checks verified selected-player isolation, three response outputs, positive mean-gain selection and missing-state suppression. On possession 114243-1-0, a fixed permissive shooting-profile fixture yields 50 candidate frames versus 11 under the previous strict search; this is coverage, not evidence of recommendation accuracy. Browser verification confirmed the new confidence/tradeoff text.
