import { shootingMotion } from "./shooting-motion.js";
import { heightFeet } from "./player-profile.js?v=pooled-1";
import { interpolateFrame } from "./playback.js";
const smooth = (t) => {
  t = Math.max(0, Math.min(1, t));
  return t * t * (3 - 2 * t);
};
// Center between the illustrated hands; matches the shooting skeleton geometry.
export function shotHandPosition(player, profile, pose) {
  const size = heightFeet(profile) / 6.23,
    dx = -40.75 - player[1],
    dy = -player[2],
    length = Math.hypot(dx, dy) || 1;
  const reach = (0.4 + 0.25 * pose.raise) * size;
  return [
    player[1] + (dx / length) * reach,
    player[2] + (dy / length) * reach,
    (3.05 + 4.1 * pose.raise + pose.jump - pose.crouch) * size,
  ];
}
function atFrame(frames, frame) {
  const i = frames.findIndex((f) => f.frame >= frame);
  if (i < 0) return null;
  if (frames[i].frame === frame) return frames[i];
  const a = frames[i - 1],
    b = frames[i];
  if (!a || b.frame - a.frame > 10 || a.period !== b.period) return null;
  return interpolateFrame(a, b, (frame - a.frame) / (b.frame - a.frame));
}
export function displayBall(frame, frames, events, time, profile) {
  const raw = frame.ball.slice(0, 3);
  const event = events.find(
    (e) => e.type === "shot" && time >= e.frame - 10 && time <= e.frame + 8,
  );
  if (!event || !raw.every(Number.isFinite)) return raw;
  const shooter = frame.offense.find((p) => p[0] === event.player);
  if (!shooter) return raw;
  const t = (time - event.frame) / 25;
  if (t < 0) {
    // Do not attach a pass in flight to the future shooter's hands.
    if (frame.geometry?.handler !== event.player) return raw;
    const hand = shotHandPosition(
      shooter,
      profile(event.player),
      shootingMotion(events, event.player, time),
    );
    const weight = smooth((t + 0.4) / 0.15);
    return raw.map((v, i) => v + (hand[i] - v) * weight);
  }
  const release = atFrame(frames, event.frame);
  const player = release?.offense.find((p) => p[0] === event.player);
  if (!player || !release.ball.slice(0, 3).every(Number.isFinite)) return raw;
  const hand = shotHandPosition(
    player,
    profile(event.player),
    shootingMotion(events, event.player, event.frame),
  );
  const weight = 1 - smooth(t / 0.32);
  return raw.map((v, i) => v + (hand[i] - release.ball[i]) * weight);
}
