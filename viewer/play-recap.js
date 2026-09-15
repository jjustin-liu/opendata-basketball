export function playRecap(play, time) {
  let survival = 1, covered = 0, elapsed = 0;
  for (let i = 0; i < play.frames.length - 1; i++) {
    const f = play.frames[i], next = play.frames[i+1];
    if (f.frame >= time) break;
    const dt = Math.max(0, (Math.min(time, next.frame) - f.frame) / 25);
    elapsed += dt;
    if (next.frame-f.frame > 10 || f.reason || !Number.isFinite(f.turnover2)) continue;
    survival *= Math.pow(1-Math.max(0,Math.min(1,f.turnover2)),dt/2);
    covered += dt;
  }
  const first = (play.events || []).filter(e=>e.type==='shot' && e.frame<=time).sort((a,b)=>a.frame-b.frame)[0];
  const firstPps=first?.shotForecast?.quality?.fieldGoalValue;
  const secondPps=first?.shotForecast?.secondChancePerShot;
  return { risk:covered ? 1-survival : null, coverage:elapsed ? covered/elapsed : 0,
    total:Number.isFinite(firstPps)&&Number.isFinite(secondPps)?firstPps+secondPps:null,
    first:first?.shotForecast?.quality?.fieldGoalValue ?? null,
    second:first?.shotForecast?.secondChancePerShot ?? null };
}

export function playOutcome(play) {
  if (play.turnover) return 'TURNOVER';
  const shots=(play.events || []).filter(e=>e.type==='shot');
  const last=shots.at(-1);
  if (last?.label?.startsWith('Made')) return last.label.toUpperCase();
  if (last) return `MISSED SHOT · ${play.points} POINT${play.points===1?'':'S'}`;
  return `PLAY COMPLETE · ${play.points} POINT${play.points===1?'':'S'}`;
}
