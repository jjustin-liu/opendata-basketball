/** Visual interpolation only: model values stay on the earlier observed state. */
export function interpolateFrame(a, b, t) {
  if (!b || t <= 0 || b.frame - a.frame > 10 || a.period !== b.period) return a;
  const lerp = (x, y) => x + (y - x) * t;
  const players = (side) =>
    a[side].map((p) => {
      const q = b[side].find((q) => q[0] === p[0]);
      return q
        ? [p[0], lerp(p[1], q[1]), lerp(p[2], q[2]), p[3], p[4], p[5]]
        : p;
    });
  return {
    ...a,
    offense: players("offense"),
    defense: players("defense"),
    ball: a.ball.map((v, i) => (i < 3 ? lerp(v, b.ball[i]) : v)),
    gameClock: lerp(a.gameClock, b.gameClock),
    shotClock:
      a.shotClock != null &&
      b.shotClock != null &&
      Math.abs(a.shotClock - b.shotClock) < 1
        ? lerp(a.shotClock, b.shotClock)
        : a.shotClock,
  };
}
