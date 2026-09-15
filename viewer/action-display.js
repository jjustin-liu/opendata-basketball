export function bestPass(frame) {
  if (frame.reason || !frame.geometry?.handler) return null;
  return (frame.passOptions || [])
    .filter(
      (o) =>
        Number.isFinite(o.value) &&
        frame.offense.some((p) => p[0] === o.player) &&
        o.player !== frame.geometry.handler,
    )
    .reduce((best, o) => (!best || o.value > best.value ? o : best), null);
}
export function shotPps(event) {
  const f = event?.shotForecast;
  return Number.isFinite(f?.quality?.fieldGoalValue) &&
    Number.isFinite(f?.secondChancePerShot)
    ? f.quality.fieldGoalValue + f.secondChancePerShot
    : null;
}
// One compact attached card: action labels on top, point values beneath.
export function actionCard(ctx, x, y, unit, shot, pass, color) {
  ctx.save();
  const width = unit * 5.6,
    height = unit * 2;
  ctx.fillStyle = "#121a20ed";
  ctx.strokeStyle = "#82918d66";
  ctx.lineWidth = unit * 0.07;
  ctx.beginPath();
  ctx.roundRect(x - width / 2, y - height / 2, width, height, unit * 0.3);
  ctx.fill();
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x, y - height * 0.32);
  ctx.lineTo(x, y + height * 0.32);
  ctx.stroke();
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (const [i, label, value] of [
    [-1, "SHOT", shot],
    [1, "PASS", pass],
  ]) {
    const px = x + (i * width) / 4;
    ctx.fillStyle = i === 1 ? "#83cfa1" : "#b4bdb9";
    ctx.font = `500 ${unit * 0.48}px monospace`;
    ctx.fillText(label, px, y - unit * 0.45);
    ctx.fillStyle = color(value);
    ctx.font = `600 ${unit * 0.85}px monospace`;
    ctx.fillText(
      Number.isFinite(value) ? value.toFixed(2) : "—",
      px,
      y + unit * 0.35,
    );
  }
  ctx.restore();
}
