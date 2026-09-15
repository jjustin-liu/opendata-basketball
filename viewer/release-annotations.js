import { passWithRisk } from './pass-flight.js?v=recap-2';
import { shotPps } from './action-display.js';
import { ballRiskColor } from './ball-risk-color.js';

export function passAnnotation(play, passes, time) {
  const pass=(passes || []).filter(p=>p.possession===play.id && p.start<=time && time-p.start<30).sort((a,b)=>b.start-a.start)[0];
  if (!pass) return null;
  const risk=passWithRisk(pass,play.frames).turnoverProbability;
  const frame=play.frames.filter(f=>f.frame<=pass.start).at(-1);
  const from=frame?.offense.find(p=>p[0]===pass.passer), to=frame?.offense.find(p=>p[0]===pass.receiver);
  if (!from || !to) return null;
  const dx=to[1]-from[1],dy=to[2]-from[2],length=Math.hypot(dx,dy)||1;
  return {x:(from[1]+to[1])/2-dy/length*1.3,y:(from[2]+to[2])/2+dx/length*1.3,risk,alpha:Math.min(1,(30-(time-pass.start))/5)};
}

export function shotBall(play,time) {
  const shot=(play.events || []).filter(e=>e.type==='shot' && e.frame<=time).at(-1);
  if (!shot) return null;
  const end=shot.shotForecast?.endFrame ?? shot.frame+50;
  if (time>end) return null;
  return {pps:shotPps(shot)};
}

export function drawPassAnnotation(ctx,x,y,unit,annotation) {
  ctx.save();
  ctx.globalAlpha=annotation.alpha;
  ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.fillStyle=ballRiskColor(annotation.risk);
  ctx.beginPath();
  ctx.roundRect(x-unit*1.55,y-unit*1.5,unit*3.1,unit*3,unit*.3);
  ctx.fill();
  ctx.strokeStyle='#805219';
  ctx.lineWidth=unit*.09;
  ctx.stroke();
  ctx.fillStyle='#191919';
  ctx.font=`700 ${unit*1.08}px monospace`;
  ctx.fillText(Number.isFinite(annotation.risk) ? `${Math.round(annotation.risk*100)}%` : '',x,y-unit*.75);
  ctx.font=`700 ${unit*.7}px monospace`;
  ctx.fillStyle='#191919';
  ctx.fillText('PASS',x,y+unit*.12);
  ctx.font=`600 ${unit*.57}px monospace`;
  ctx.fillStyle='#392c20';
  ctx.fillText('TOV%',x,y+unit*.87);
  ctx.restore();
}
