// A direct-drive reachability sketch, not a learned probability or EPV model.
export const DRIVE_ASSUMPTIONS = {
  attackerSpeed: 14,
  defenderSpeed: 12,
  reaction: 0.2,
  reach: 2,
  horizon: 1.5,
  cell: 1.5,
};
export function insideArc(x, y) {
  return (
    x >= -45.932 &&
    x <= 0 &&
    Math.abs(y) <= 21.6535 &&
    Math.hypot(x + 40.75, y) <= 22.146
  );
}
export function driveSpace(frame) {
  const holder = frame.offense.find((p) => p[0] === frame.geometry?.handler);
  if (!holder || frame.reason || frame.defense.length !== 5) return [];
  const { attackerSpeed, defenderSpeed, reaction, reach, horizon, cell } =
    DRIVE_ASSUMPTIONS;
  const rimDistance = Math.hypot(holder[1] + 40.75, holder[2]);
  const result = [];
  for (let x = -45; x < -18; x += cell)
    for (let y = -21; y < 21; y += cell) {
      const corners = [
        [x, y],
        [x + cell, y],
        [x + cell, y + cell],
        [x, y + cell],
      ];
      if (!corners.every(([a, b]) => insideArc(a, b))) continue;
      const tx = x + cell / 2,
        ty = y + cell / 2;
      if (Math.hypot(tx + 40.75, ty) > rimDistance - 1) continue;
      const length = Math.hypot(tx - holder[1], ty - holder[2]),
        arrival = length / attackerSpeed;
      if (length < 2 || arrival > Math.min(horizon, frame.shotClock ?? 0))
        continue;
      let margin = Infinity;
      for (let i = 1; i <= 12; i++) {
        const fraction = i / 12,
          px = holder[1] + (tx - holder[1]) * fraction,
          py = holder[2] + (ty - holder[2]) * fraction;
        const time = arrival * fraction;
        for (const d of frame.defense)
          margin = Math.min(
            margin,
            Math.hypot(px - d[1], py - d[2]) -
              reach -
              defenderSpeed * Math.max(0, time - reaction),
          );
        for (const p of frame.offense)
          if (p[0] !== holder[0])
            margin = Math.min(margin, Math.hypot(px - p[1], py - p[2]) - 1.5);
        if (margin <= 0) break;
      }
      if (margin > 0)
        result.push({
          corners,
          alpha: 0.1 + 0.22 * Math.min(1, margin / 3),
          margin,
          arrival,
        });
    }
  return result;
}
