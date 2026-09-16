import { passWithRisk } from './pass-flight.js?v=recap-2';
import { shotPps } from './action-display.js?v=foul-4';
import { passFeedbackActive } from './pass-feedback.js';

export function actionRecap(play, passes, player, time) {
  const pass = (passes || []).filter(p => p.possession === play.id && p.passer === player && p.start <= time && time - p.start <= 50).sort((a,b) => b.start-a.start)[0];
  const shot = (play.events || []).filter(e => e.type === 'shot' && e.player === player && e.frame <= time && time-e.frame <= 50).sort((a,b) => b.frame-a.frame)[0];
  if (shot && (!pass || shot.frame >= pass.start)) {
    const value = shotPps(shot);
    return ['SHOT', Number.isFinite(value) ? value.toFixed(2) : '', 'PPS'];
  }
  if (!pass || !passFeedbackActive(pass,time)) return null;
  const forecast = passWithRisk(pass, play.frames);
  return [Number.isFinite(forecast.epv) ? forecast.epv.toFixed(2) : '', 'PASS'];
}

export function drawActionRecap(ctx, x, y, radius, lines) {
  ctx.save();
  ctx.fillStyle = '#182126';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const centerX = x + radius + 1.25;
  lines.forEach((line, i) => {
    ctx.font = `${i === 0 ? 700 : 600} ${i === 0 ? .85 : .65}px "IBM Plex Mono", monospace`;
    ctx.fillText(line, centerX, y + (i - (lines.length - 1) / 2) * .85);
  });
  ctx.restore();
}
