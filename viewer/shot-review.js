import { bestPass, shotPps } from "./action-display.js?v=foul-4";
export function shotReview(play, time) {
  const event = (play.events || [])
    .filter((e) => e.type === "shot" && e.frame <= time)
    .at(-1);
  if (!event) return null;
  // Latest supported decision state, strictly before release, at most 0.4s old.
  const prior = play.frames
    .filter(
      (f) =>
        f.frame < event.frame &&
        event.frame - f.frame <= 10 &&
        !f.reason &&
        f.geometry?.handler === event.player,
    )
    .at(-1);
  const pass = prior ? bestPass(prior) : null;
  const forecast = event.shotForecast;
  return {
    event,
    first: forecast?.quality?.fieldGoalValue ?? null,
    second: Number.isFinite(forecast?.secondChancePerShot) ? forecast.secondChancePerShot+(forecast.ftSecondChancePerShot??0) : null,
    freeThrows: forecast?.freeThrowValue ?? null,
    foulProbability: forecast?.foulProbability ?? null,
    ftPercentage: forecast?.freeThrowMakeProbability ?? null,
    orb: forecast?.offensiveReboundProbability ?? null,
    perMiss: forecast?.secondChancePerMiss ?? null,
    total: shotPps(event),
    clock: event.shotClock ?? null,
    pass,
    passAge: pass ? (event.frame - prior.frame) / 25 : null,
  };
}
