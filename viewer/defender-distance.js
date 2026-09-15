// Recompute from the displayed/interpolated positions, not a stale frame's ID.
export function nearestDefenderDistance(player, defenders) {
  const distances = defenders.map(d => Math.hypot(d[1] - player[1], d[2] - player[2])).filter(Number.isFinite);
  return distances.length ? Math.min(...distances) : null;
}

export function closestDefenderToBall(frame) {
  if (!frame.ball || !Number.isFinite(frame.ball[0]) || !Number.isFinite(frame.ball[1])) return null;
  let nearest = null;
  for (const defender of frame.defense) {
    const distance = Math.hypot(defender[1] - frame.ball[0], defender[2] - frame.ball[1]);
    if (Number.isFinite(distance) && (!nearest || distance < nearest.distance)) nearest = { defender, distance };
  }
  return nearest;
}

export function drawDefenderDistance(ctx, x, y, unit, player, frame) {
  const nearest = closestDefenderToBall(frame);
  if (!nearest || nearest.defender[0] !== player[0]) return;
  const { distance } = nearest;
  const text = `${distance.toFixed(1)} ft`;
  ctx.save();
  ctx.font = `600 ${unit * .65}px monospace`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const width = ctx.measureText(text).width + unit * .5;
  ctx.fillStyle = '#202a2e';
  ctx.fillRect(x - width / 2, y - unit * .47, width, unit * .94);
  ctx.fillStyle = '#e0e7eb';
  ctx.fillText(text, x, y);
  ctx.restore();
}

export function closestDefender(frame) {
  const holder = frame.offense.find((p) => p[0] === frame.geometry?.handler);
  if (!holder || !frame.defense.length) return null;
  let defender,
    distance = Infinity;
  for (const p of frame.defense) {
    const d = Math.hypot(p[1] - holder[1], p[2] - holder[2]);
    if (d < distance) {
      defender = p;
      distance = d;
    }
  }
  const rx = -40.75 - holder[1],
    ry = -holder[2],
    rimDistance = Math.hypot(rx, ry);
  const dx = defender[1] - holder[1],
    dy = defender[2] - holder[2];
  const signedAngle =
    distance > 0.01 && rimDistance > 0.01
      ? Math.atan2(rx * dy - ry * dx, rx * dx + ry * dy)
      : null;
  const rimBearing = Math.atan2(ry, rx);
  const along = rimDistance > 0.01 ? (rx * dx + ry * dy) / rimDistance : null;
  const lateral =
    rimDistance > 0.01 ? Math.abs(rx * dy - ry * dx) / rimDistance : null;
  return {
    holder,
    defender,
    distance,
    signedAngle,
    rimBearing,
    along,
    lateral,
  };
}
