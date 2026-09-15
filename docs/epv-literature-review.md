# Basketball expected possession value: research notes

Research date: 2026-09-12. This is a targeted primary-source review, not an exhaustive survey. Paper descriptions below are verified against the linked papers; the implementation and evaluation advice is our recommendation. See [the proposed model design](epv-model-design.md) for the connection to “The Shot That Exists” and the local data audit.

## What the literature establishes

### 1. Cervone, D’Amour, Bornn and Goldsberry — multiresolution EPV (2016)

EPV is the conditional expectation of a possession’s final points given its observed history: `E[X | history through t]`. Their estimator combines fine-scale player movement with discrete pass, shot and turnover transitions, then uses a coarse state model for continuation. This avoids simulating every remaining frame. Hierarchical spatial models share information between players. The full-resolution input is 25 Hz tracking; coarse ball-possession states retain player, court region and defensive pressure.

Crucially, the paper includes offensive-rebound continuation but excludes fouls because the available annotations did not adequately identify foul circumstances. Its terminal reward is therefore restricted to 0, 2 or 3 points. It is not a ready-made specification for all modern possession outcomes. The paper also defines shot satisfaction and EPV-added comparisons; these require an explicit reference action or player.

Its emphasis on stochastic consistency matters: a coherent conditional expectation should not exhibit predictable drift solely from the estimator. Independent frame regressions do not automatically provide that property.

Sources: [full paper, especially §§2–3 and 5](https://arxiv.org/html/1408.0777), [author demonstration code](https://github.com/dcervone/EPVDemo).

### 2. Skinner — The Problem of Shot Selection in Basketball (2012)

This is the closest theoretical companion to the blog’s stopping decision. In a simplified model, a team accepts a current shot when its quality exceeds a continuation threshold. That threshold depends on how many opportunities remain and the risk of losing the ball while waiting. The model initially assumes a uniform opportunity-quality distribution, then discusses generalizations. Its comparison with NBA shooting rates is evidence about that simplified model, not proof that particular observed players should have shot.

The paper explicitly recognizes an identification problem: the data record shots taken, while passed-up opportunities are unobserved. Tracking helps describe those opportunities but does not reveal their unplayed outcomes.

Source: [PLOS ONE paper](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0030776).

### 3. Franks, Miller, Bornn and Goldsberry — spatial defensive skill (2015)

The paper estimates who guards whom with a hidden Markov model, then separates defensive effects on shot frequency from effects on shot efficiency. Its matchup model uses the offensive player, ball and hoop locations and temporal persistence; the nearest defender alone is not necessarily the assigned defender. It allows multiple defenders to cover one attacker.

This is useful precedent for evaluating deterrence, attention and shooting suppression separately. It does not make an individual defender causally responsible for every possession-value change while nearby.

Source: [full paper, especially §§2 and 4](https://arxiv.org/html/1405.0231).

### 4. DeepHoops — micro-action evaluation with learned sequence features (2019)

DeepHoops combines a stacked LSTM over tracking windows with player embeddings. Its labels distinguish field-goal attempts, shooting fouls, non-shooting fouls, turnovers and no terminal action. It uses roughly five-second input windows and studies probability quality, including Brier scores and handling the heavily imbalanced null class.

A key simplification is valuing terminal action types by their average points rather than using a fully contextual shot-success model for every hypothetical shot. Thus, borrow the temporal representation and evaluation ideas; do not assume its scalar value is interchangeable with a shoot-versus-pass decision model that conditions on shooter and contest geometry.

Source: [DeepHoops paper, §§3–4](https://arxiv.org/html/1902.08081).

### 5. GraphEIV — modular graph models (2024)

GraphEIV builds separate graph-based models for shot success, next action type, receiver and turnover. It intentionally estimates immediate value under “shoot now or pass to someone who shoots,” rather than the full remaining possession. The authors explain that tracking/event synchronization problems and missing dribble/drive information motivated this scope.

This is useful evidence for modular heads and relational player geometry, but its immediate-value target omits the very continuation choices the blog highlights. Its authors explicitly distinguish EIV from full EPV. Their stated data limitations are also a reminder that richer neural architecture does not resolve poor labels.

Source: [MLSA workshop paper, especially §§4 and 7](https://dtai.cs.kuleuven.be/events/MLSA24/papers/8.pdf).

### 6. Jutamulia and Hosoi — Expected Action Value (2025)

The authors model shot and pass difficulty and combine them to value immediate potential actions: shoot, or pass to a particular teammate who then shoots. They compare available opportunities with realized actions and distinguish opportunity creation from execution. Neural networks are used for the underlying probability models.

This is a direct reference for a decision dashboard showing alternatives and missed opportunities. Its simplified pass-then-shot construction should not be silently relabeled as the value of arbitrary future dribbling, extra passes, free throws and offensive rebounds.

Source: [journal article](https://journals.sagepub.com/doi/abs/10.1177/22150218251325018).

### 7. Q-Ball — deep reinforcement learning (2022)

Q-Ball models player movements, actions and performance with deep reinforcement learning and reports player/team evaluations and alternative-action recommendations on NBA data. It provides a basketball precedent for action values beyond a static shot model.

Only the publisher abstract was available in this review; the full PDF fetch failed. Accordingly, no claim is made here about its exact training algorithm, causal assumptions, calibration, split design or suitability for the local sample. Its abstract’s recommendation results should not be treated as independently validated causal effects.

Source: [AAAI publisher page](https://ojs.aaai.org/index.php/AAAI/article/view/20861).

### 8. Jiang and Li — doubly robust off-policy evaluation (2016)

This foundational methods paper addresses evaluating a new policy from trajectories generated by another policy. It extends doubly robust estimation to sequential decisions, combining outcome modeling with importance weighting and analyzing bias/variance and theoretical difficulty.

For basketball, adopting such a method would still require checking behavioral-policy support, reliable action probabilities and relevant state information. Naming a model “reinforcement learning” is not itself off-policy validation.

Source: [ICML paper](https://proceedings.mlr.press/v48/jiang16.html).

## Recommended interpretation and model boundaries

The following are design recommendations and mathematical distinctions, not reported empirical findings from the papers.

- **Prediction:** `V^μ(s)` asks what normally happens under the observed playing policy `μ`.
- **A chosen action:** `Q^μ(s,a) = E[r + V^μ(s′) | s, a]` evaluates an action followed by normal continuation, with terminal continuation zero. A causal interpretation additionally requires identification assumptions.
- **One-step improvement:** `max_a Q^μ(s,a)` chooses the best modeled immediate action, then returns to normal play. It is not the same as globally optimal `V*(s)`, which changes subsequent choices too.
- **Descriptive action increment:** `r + V(s′) - V(s)` measures a modeled change across a transition. It is not automatically the causal contribution of the ballhandler, defender or screener; everyone moves and outcomes contain luck.
- **Opportunity regret:** `max_a Q(s,a) - Q(s,a_observed)` is useful only over feasible, adequately supported alternatives. It needs uncertainty, not false precision.

For full-possession value, define the reward and terminal boundary before fitting. Free throws and offensive rebounds must be included consistently. A shot value needs branches for makes, misses, fouls and continued offensive control; a pass value needs failure, catch geometry, elapsed time and continuation. Avoid counting a fouled miss as a normal missed attempt and separately assigning its free throws without a mutually exclusive outcome scheme.

A frozen photograph of an open teammate is insufficient for pass value. Estimate the receiver’s possible state on arrival, including defensive recovery. A drive or creation action needs a duration and a next-state distribution; do not assume that “continue” means cost-free waiting.

## Implications for this SkillCorner sample

The [repository README](../README.md) describes 10 tracked ACB games and season aggregates covering 293 games. It reports 25 Hz positions, some extrapolated locations and position-error metadata. The main-task audit found 1,564 possession records and 1,459 shot records; all 10 local tracking files currently contain Git LFS pointers rather than materialized tracking. Those counts are an audit result, not a literature claim. See the model-design note for full details.

This is sparse game coverage, not sparse nominal frame rate. Adjacent frames do not turn ten games into millions of independent examples. Recommendation: start with pooled, regularized event-level models and a transparent continuation model. Treat a graph/sequence model as a later challenger once tracking is materialized and there are enough independent games.

The season aggregates can support shrinkage priors, but contain the sample games and potentially later-season information. For chronological validation, use strictly earlier data or report that the experiment uses retrospective season priors. They cannot supply missing frame-level alternatives.

Recommended validation:

1. Split whole games, not adjacent frames. Keep related chances/possessions together; report sensitivity across held-out games rather than one flattering split.
2. Evaluate probability heads with log loss, Brier scores and reliability plots; evaluate possession values against held-out realized points. Include uncertainty from the small number of games.
3. Evaluate clock, shot zone, action type, transition/half-court, and tracked/extrapolated slices. A good overall mean can conceal a bad decision threshold.
4. Use only information available at the decision time. Do not use future shot outcomes, retrospective event end fields, or future-smoothed positions as if observed live.
5. Check alternative-action support. Success on selected shots does not establish accuracy on shots players refused, and accuracy on completed passes does not establish intended receiver on interceptions.
6. Report descriptive values first. Test counterfactual recommendations separately with overlap diagnostics, uncertainty, video review and, if the data permit, policy-evaluation methods. Defensive adaptation to a new policy is a further modeling problem.
