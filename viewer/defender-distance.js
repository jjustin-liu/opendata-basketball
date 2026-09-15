// Recompute from the displayed/interpolated positions, not a stale frame's ID.
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
