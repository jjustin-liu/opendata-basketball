// Display context only; never feeds the prediction models.
export function playerProfile(game, id) {
  const player = game?.players[String(id)] || {};
  const fga = player.sampleFga || 0,
    three = player.sampleThreePa || 0;
  return {
    ...player,
    position: player.position || "?",
    fga,
    three,
    possessions: player.sampleOffPossessions || 0,
    threePer100: player.sampleOffPossessions
      ? (100 * three) / player.sampleOffPossessions
      : null,
    made: player.sampleThreePm || 0,
    rate: fga ? three / fga : null,
  };
}
export function heightFeet(profile) {
  return Number.isFinite(profile?.heightCm) && profile.heightCm > 0
    ? profile.heightCm / 30.48
    : 6.5;
}
// Color encodes observed shot selection, not a calibrated shooting/gravity model.
export function shootingCue(profile) {
  const strength = Math.max(0, Math.min(1, (profile.threePer100 || 0) / 10));
  // Fade small samples instead of turning one three into a strong signal.
  const evidence = Math.min(1, profile.possessions / 100);
  const t = strength * evidence;
  const mix = (a, b) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
  return {
    color: `rgb(${mix([127, 143, 148], [85, 225, 147]).join(",")})`,
    strength,
    evidence,
  };
}
export function profileTab(ctx, x, y, unit, profile, offense) {
  const text = offense ? `${profile.position} · 3PT` : profile.position;
  ctx.save();
  ctx.font = `500 ${unit * 0.57}px monospace`;
  const width = ctx.measureText(text).width + unit * 0.6,
    height = unit * 0.95;
  const cue = shootingCue(profile);
  ctx.fillStyle = offense && profile.rate > 0 ? "#172a23" : "#202b30";
  ctx.strokeStyle = offense ? cue.color : "#84959b";
  ctx.lineWidth = unit * 0.045;
  ctx.setLineDash([]);
  ctx.fillRect(x - width / 2, y - height / 2, width, height);
  // No bright outline around every label.
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  if (offense && profile.threePer100 != null) {
    ctx.fillStyle = "#367559";
    ctx.globalAlpha = 0.7;
    ctx.fillRect(x-width/2, y-height/2, width*cue.strength*cue.evidence, height);
    ctx.globalAlpha = 1;
  }
  ctx.fillStyle = offense ? "#b3c6bf" : "#d5dddd";
  ctx.fillText(text, x, y);
  ctx.restore();
}

// Lineup slots: use listed position, with height to resolve shared/unknown roles.
export function defenderNumbers(players, profile) {
  const rank = { PG: 1, SG: 2, SF: 3, PF: 4, C: 5 };
  const ordered = players.map(p => {
    const bio = profile(p[0]);
    const height = bio.heightCm || 200;
    const inferred = height < 190 ? 1 : height < 197 ? 2 : height < 203 ? 3 : height < 210 ? 4 : 5;
    return { id: p[0], rank: rank[bio.position] || inferred, height };
  }).sort((a,b) => a.rank-b.rank || a.height-b.height || a.id-b.id);
  return new Map(ordered.map((p,i) => [p.id, String(i+1)]));
}

// Visual position cue only; not physical reach or a defensive probability.
export function defenderChipScale(position) {
  return [0.84, 0.92, 1, 1.09, 1.18][Number(position) - 1] || 1;
}
