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
export function releaseCard(play, passes, time) {
  const actions = [
    ...(passes || []).filter(p => p.possession === play.id).map(p => ({frame:p.start, player:p.passer, receiver:p.receiver, selected:'PASS'})),
    ...(play.events || []).filter(e => e.type === 'shot').map(e => ({frame:e.frame, player:e.player, selected:'SHOT', releasePps:shotPps(e)})),
  ].filter(a => a.frame <= time && time - a.frame < 25).sort((a,b) => b.frame-a.frame);
  const action = actions[0];
  if (!action) return null;
  const prior = play.frames.filter(f => f.frame < action.frame && action.frame-f.frame <= 10 && !f.reason && f.geometry?.handler === action.player).at(-1);
  if (!prior && action.selected !== 'SHOT') return null;
  const pass = action.selected === 'PASS' ? prior?.passOptions?.find(p => p.player === action.receiver) : prior ? bestPass(prior) : null;
  return {...action, shot:action.selected === 'SHOT' ? action.releasePps : prior?.shot?.shotPlusSecondChance, pass:pass?.value};
}

export function actionCard(ctx, x, y, unit, shot, pass, color, selected = null) {
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
    if (selected === label) {
      ctx.fillStyle = '#368363';
      ctx.beginPath();
      ctx.roundRect(px-width/4+.08*unit, y-height/2+.08*unit, width/2-.16*unit, height-.16*unit, .2*unit);
      ctx.fill();
    }
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
