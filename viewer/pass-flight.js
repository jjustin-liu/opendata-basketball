// Recorded replay annotations, separate from pre-pass model forecasts.
export function activePass(passes, playId, frame) {
  return (
    (passes || []).find(
      (p) => p.possession === playId && p.start <= frame && frame < p.end,
    ) || null
  );
}
export function flightLabel(pass, player) {
  if (!pass) return null;
  if (pass.passer === player) return "PASS";
  if (pass.receiver === player) return "REC";
  return "";
}

// Freeze the last supported forecast before release; never use the pass outcome.
export function passWithRisk(pass, frames) {
  if (!pass) return null;
  const prior = frames.filter(f => f.frame < pass.start && pass.start - f.frame <= 10
    && !f.reason && f.geometry?.handler === pass.passer).at(-1);
  const option = prior?.passOptions?.find(o => o.player === pass.receiver);
  const value = option?.turnoverProbability;
  return {...pass, epv: Number.isFinite(option?.value) ? option.value : null, turnoverProbability: Number.isFinite(value) ? value : null};
}
