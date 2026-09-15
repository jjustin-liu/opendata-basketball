// Illustrative pose synchronized to recorded events; never a model input.
const clamp = (v) => Math.max(0, Math.min(1, v));
const smooth = (v) => {
  const t = clamp(v);
  return t * t * (3 - 2 * t);
};
export function shootingMotion(events, player, frame) {
  const event = (events || []).find(
    (e) =>
      e.type === "shot" &&
      e.player === player &&
      frame >= e.frame - 10 &&
      frame <= e.frame + 25,
  );
  if (!event) return null;
  const t = (frame - event.frame) / 25;
  const raise = t < 0 ? smooth((t + 0.4) / 0.4) : 1 - smooth((t - 0.35) / 0.65);
  const jump =
    t < 0 ? 0.55 * smooth((t + 0.18) / 0.18) : 0.55 * (1 - smooth(t / 0.45));
  const crouch = t < 0 ? 0.3 * Math.sin(clamp((t + 0.4) / 0.4) * Math.PI) : 0;
  return { raise, jump, crouch };
}
