import { passWithRisk } from './pass-flight.js?v=recap-2';
import { shotPps } from './action-display.js?v=foul-4';

export function passAnnotation(play, passes, time) {
  const pass=(passes || []).filter(p=>p.possession===play.id && p.start<=time && time-p.start<30).sort((a,b)=>b.start-a.start)[0];
  if (!pass) return null;
  const forecast=passWithRisk(pass,play.frames);
  const risk=forecast.turnoverProbability;
  const prior=play.frames.filter(f=>f.frame<pass.start && pass.start-f.frame<=10 && !f.reason && f.geometry?.handler===pass.passer).at(-1);
  const delta=Number.isFinite(forecast.epv)&&Number.isFinite(prior?.epv)?forecast.epv-prior.epv:null;
  const midpoint=passPathMidpoint(play.frames,pass.start,pass.end);
  if (!midpoint) return null;
  return {x:midpoint[0],y:midpoint[1],risk,delta,alpha:Math.min(1,(30-(time-pass.start))/5)};
}

// Replay-only annotation: midpoint by traveled floor distance, not player positions.
export function passPathMidpoint(frames,start,end) {
  if (!Number.isFinite(end) || end<=start) return null;
  const sample=t=>{
    const a=frames.filter(f=>f.frame<=t).at(-1),b=frames.find(f=>f.frame>=t);
    if (!a || !b || b.frame-a.frame>10 || !a.ball || !b.ball) return null;
    const u=b.frame===a.frame?0:(t-a.frame)/(b.frame-a.frame);
    const point=[0,1].map(i=>a.ball[i]+(b.ball[i]-a.ball[i])*u);
    return point.every(Number.isFinite)?point:null;
  };
  const times=[start,...frames.filter(f=>f.frame>start && f.frame<end).map(f=>f.frame),end];
  if(times.some((t,i)=>i && t-times[i-1]>10))return null;
  const points=times.map(sample);
  if(points.some(p=>!p))return null;
  const lengths=points.slice(1).map((p,i)=>Math.hypot(p[0]-points[i][0],p[1]-points[i][1]));
  let remaining=lengths.reduce((a,b)=>a+b,0)/2;
  for(let i=0;i<lengths.length;i++){
    if(remaining<=lengths[i]) {const u=lengths[i]?remaining/lengths[i]:0;return points[i].map((v,j)=>v+(points[i+1][j]-v)*u);}
    remaining-=lengths[i];
  }
  return points[0];
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
  if (!Number.isFinite(annotation.risk) && !Number.isFinite(annotation.delta)) { ctx.restore(); return; }
  ctx.globalAlpha=annotation.alpha;
  ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.strokeStyle='#f3eddb';ctx.lineWidth=unit*.22;ctx.lineJoin='round';
  ctx.fillStyle='#1b302b';
  const lines=Number.isFinite(annotation.risk)?[[`${(annotation.risk*100).toFixed(1)}%`,1.2,-.45],['TOV',.7,.48]]:[];
  if(Number.isFinite(annotation.delta)) {
    const rounded=Math.round(annotation.delta*100)/100;
    lines.push([`${rounded>=0?'+':''}${rounded.toFixed(2)} EPV`,.9,1.5]);
  }
  for (const [text,size,offset] of lines) {
    ctx.font=`700 ${unit*size}px monospace`;
    ctx.strokeText(text,x,y+unit*offset);
    ctx.fillText(text,x,y+unit*offset);
  }
  ctx.restore();
}
