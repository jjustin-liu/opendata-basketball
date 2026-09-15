# Action-specific defensive threat

The chip numbers now describe two different actions, replacing unconditional next-two-second forecasts:

- STL: credited interception on a pass to the selected receiver. With no selection, use the currently highest-valued available pass and identify the recipient in the court legend.
- BLK: credited block on a shot from the holder's current geometry. Unsupported shooting geometry beyond 32 feet shows no estimate.

These are fitted associations among observed actions, applied to hypothetical current actions. They are not validated causal probabilities for forcing a pass or shot. Non-steal pass turnovers belong to the no-interception class; STL is not total pass-turnover probability. Neither risk is added into existing EPV or shot quality, avoiding double counting.

Training uses one tracking snapshot immediately before each pass/shot starts. Targets use the eventual credited defender, never as predictors. Shot data supplies blockerId. Pass outcomes link to turnover events by possession, touch and pass time interval; ambiguous links are excluded. The existing conservative early-flight receiver reconstruction restricts both completed and failed passes. Future flight helps reconstruct training destinations only and is not a live predictor. This creates selection and receiver-identification uncertainty.

Features per defender: actor distance, route clearance, along-route fraction, destination distance, action distance, distance to rim, listed height and a shrunk credited-event rate. Five defender logits plus no event form one coherent softmax distribution. Each whole-game holdout excludes that game from fitting and from all player priors; training priors also exclude their own game.

The accepted pass fit uses L2 0.1 after the initial 0.01 fit failed the Brier check. The block fit uses L2 0.01. This choice makes the following results exploratory model-selection results, not untouched final validation:

| Target | Actions / positives | Joint log loss vs constant | Joint Brier vs constant |
|---|---:|---:|---:|
| Interception | 2,047 / 25 | 0.08192 / 0.08432 | 0.023742 / 0.023789 |
| Block | 1,458 / 51 | 0.16716 / 0.20971 | 0.067207 / 0.068935 |

Scores are equal-game means. The pass improvement is especially small and there are few positive labels. Full reports and exclusions are in viewer/data/action-defense.json. Each model must beat its training-only constant baseline on joint log loss, joint Brier and any-event Brier to be shown.

The six probabilities sum to one for each action. Different pass targets are different scenarios and must not be combined. The visible wings follow the chosen pass and the tail follows the shoot-now scenario. Shape references are fixed from the first supported action forecast in the possession; chip position size is independent. Full precision estimates remain in JSON; the chip displays percentages.

Rebuild with `python -m epv.action_defense`; this also runs at the end of the full build. The earlier next-two-second forecasts remain in data for research, but are not substituted for unsupported action forecasts.
