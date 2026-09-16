// Exploratory arrival-time surface; not a calibrated control or scoring model.
// Mirrors epv/space.py: reaction drift, bang-bang acceleration to a speed cap,
// Gaussian arrival-time noise, Clark (1961) minimum over each team, control =
// P(first attacker arrives before first defender). Off-ball attackers only.
export const MOTION = {
  vMax: 20, aMax: 16, reaction: 0.2, sigma0: 0.15, vRef: 10, kappa: 0.10,
  extrapInflate: 1.5, errorToSd: 2.146, tau: 0.5,
};
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
// Abramowitz & Stegun 7.1.26, |error| < 1.5e-7.
export function erf(x) {
  const s = x < 0 ? -1 : 1, a = Math.abs(x), t = 1 / (1 + 0.3275911 * a);
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-a * a);
  return s * y;
}
export const ndtr = (x) => 0.5 * (1 + erf(x / Math.SQRT2));
const pdf = (x) => Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);

export function velocity(p, old, dt, maxDt = 0.4) {
  if (!old || !(dt > 0) || dt > maxDt) return [0, 0];
  return [(p[1] - old[1]) / dt, (p[2] - old[2]) / dt];
}

// Arrival time and its standard deviation for one player at (x, y).
export function arrival(p, v, x, y, m = MOTION) {
  const px = p[1] + v[0] * m.reaction, py = p[2] + v[1] * m.reaction;
  const dx = x - px, dy = y - py, d = Math.hypot(dx, dy);
  const s0 = d > 1e-6 ? clamp((v[0] * dx + v[1] * dy) / d, -m.vMax, m.vMax) : 0;
  const neg = s0 < 0;
  const tStop = neg ? -s0 / m.aMax : 0;
  const dEff = d + (neg ? (s0 * s0) / (2 * m.aMax) : 0);
  const s = neg ? 0 : s0;
  const dAcc = (m.vMax * m.vMax - s * s) / (2 * m.aMax);
  const t = m.reaction + tStop + (dEff <= dAcc
    ? (-s + Math.sqrt(s * s + 2 * m.aMax * dEff)) / m.aMax
    : (m.vMax - s) / m.aMax + (dEff - dAcc) / m.vMax);
  const err = (Number.isFinite(p[4]) && p[4] >= 0 ? p[4] : 4) / m.errorToSd * (p[3] === false || p[3] === 0 ? m.extrapInflate : 1);
  const sigma = Math.hypot(m.sigma0, err / m.vRef, m.kappa * t);
  return { t, sigma };
}

// Moment-matched minimum of independent normals.
export function clarkMin(items) {
  let m1 = items[0].t, s1 = items[0].sigma;
  for (let i = 1; i < items.length; i++) {
    const m2 = items[i].t, s2 = items[i].sigma;
    const a = Math.hypot(s1, s2) + 1e-6, alpha = (m1 - m2) / a;
    const phi = pdf(alpha), Phi = ndtr(alpha);
    const mmin = m1 * (1 - Phi) + m2 * Phi - a * phi;
    const m2nd = (m1 * m1 + s1 * s1) * (1 - Phi) + (m2 * m2 + s2 * s2) * Phi - (m1 + m2) * a * phi;
    s1 = Math.sqrt(Math.max(m2nd - mmin * mmin, 1e-8));
    m1 = mmin;
  }
  return { t: m1, sigma: s1 };
}

export function spaceControl(frame, previous, grid, m = MOTION) {
  if (frame.reason || frame.offense.length !== 5 || frame.defense.length !== 5 || !grid) return { cells: [], area: 0 };
  const offBall = frame.offense.filter((p) => p[0] !== frame.geometry?.handler);
  if (!frame.offense.some((p) => p[0] === frame.geometry?.handler) || !offBall.length) return { cells: [], area: 0 };
  const dt = (frame.frame - (previous?.frame ?? frame.frame)) / 25;
  const samePeriod = !previous || previous.period === frame.period;
  const prep = (side, list) => list.map((p) => [p, samePeriod ? velocity(p, previous?.[side]?.find((q) => q[0] === p[0]), dt) : [0, 0]]);
  const off = prep('offense', offBall), def = prep('defense', frame.defense);
  const horizon = Math.min(2, frame.shotClock ?? 2);
  let area = 0; const cells = [];
  for (const [x, y, value] of grid.cells) {
    const cx = x + 0.5, cy = y + 0.5;
    const o = clarkMin(off.map(([p, v]) => arrival(p, v, cx, cy, m)));
    if (o.t > horizon) continue;
    const d = clarkMin(def.map(([p, v]) => arrival(p, v, cx, cy, m)));
    const control = ndtr((d.t - o.t) / Math.hypot(o.sigma, d.sigma));
    const score = control * value;
    if (score < m.tau) continue;
    area += 1;
    cells.push({ corners: [[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1]], alpha: 0.10 + 0.18 * clamp((score - m.tau) / 0.9, 0, 1), score, control });
  }
  return { cells, area };
}
