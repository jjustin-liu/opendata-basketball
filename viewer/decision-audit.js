import { shotPps } from "./action-display.js";
export const AUDIT_RULES = {
  lookback: 2,
  commitment: 0.3,
  minWindow: 0.4,
  minGain: 0.15,
  maxTurnover: 0.12,
  lowShot: 0.95,
  minClock: 5,
};
export function auditShot(play, event) {
  if (event.fouled) return {shotFrame:event.frame, shooter:event.player, clock:event.shotClock ?? null, total:null, window:null, kind:"foul", priority:0};
  const total = shotPps(event),
    r = AUDIT_RULES;
  const runs = new Map(),
    windows = [];
  const finish = (id) => {
    const run = runs.get(id);
    if (run && (run.end - run.start) / 25 >= r.minWindow - 1e-8)
      windows.push(run);
    runs.delete(id);
  };
  for (const f of play.frames.filter(
    (f) =>
      f.frame >= event.frame - r.lookback * 25 &&
      f.frame <= event.frame - r.commitment * 25,
  )) {
    const eligible =
      !f.reason &&
      f.geometry?.handler === event.player &&
      Number.isFinite(total);
    const options = eligible
      ? (f.passOptions || []).filter(
          (o) =>
            Number.isFinite(o.value) &&
            Number.isFinite(o.turnoverProbability) &&
            o.turnoverProbability <= r.maxTurnover &&
            o.route?.reachableDefenders === 0 &&
            o.player !== event.player &&
            f.offense.some((p) => p[0] === o.player) &&
            o.value - total >= r.minGain,
        )
      : [];
    for (const id of [...runs.keys()])
      if (
        !options.some((o) => o.player === id) ||
        f.frame - runs.get(id).end > 6
      )
        finish(id);
    for (const o of options) {
      const gain = o.value - total;
      const run = runs.get(o.player);
      if (run) {
        run.end = f.frame;
        if (gain < run.gain) {
          run.gain = gain;
          run.frame = f.frame;
          run.pass = o.value;
          run.shot = (f.shot?.shotPlusSecondChance ?? null);
        }
        run.maxTo = Math.max(run.maxTo, o.turnoverProbability);
      } else
        runs.set(o.player, {
          player: o.player,
          start: f.frame,
          frame: f.frame,
          end: f.frame,
          gain,
          pass: o.value,
          shot: (f.shot?.shotPlusSecondChance ?? null),
          maxTo: o.turnoverProbability,
        });
    }
  }
  for (const id of [...runs.keys()]) finish(id);
  const window =
    windows.sort(
      (a, b) => b.gain - a.gain || b.end - b.start - (a.end - a.start),
    )[0] || null;
  const low =
    Number.isFinite(total) &&
    total < r.lowShot &&
    Number.isFinite(event.shotClock) &&
    event.shotClock > r.minClock;
  return {
    shotFrame: event.frame,
    shooter: event.player,
    clock: event.shotClock ?? null,
    total,
    window,
    kind: window
      ? "missed-pass"
      : low
        ? "low-shot"
        : Number.isFinite(total)
          ? "unflagged"
          : "unavailable",
    priority: window?.gain ?? (low ? r.lowShot - total : 0),
  };
}
