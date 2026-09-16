import { activePass, passWithRisk } from './pass-flight.js?v=catch-3';

export function scoreboardEstimate(play, frame, time, passes, key) {
  const flight=activePass(passes,play.id,time);
  const prior=flight ? play.frames.filter(f=>f.frame<flight.start && flight.start-f.frame<=10
    && !f.reason && f.geometry?.handler===flight.passer).at(-1) : null;
  const held=!!prior && (!Number.isFinite(frame[key]) || !Number.isFinite(frame.turnoverRest));
  return {epv:Number.isFinite(frame[key])?frame[key]:prior?.[key],
    rest:Number.isFinite(frame.turnoverRest)?frame.turnoverRest:prior?.turnoverRest,held};
}

// Approximate exposure ledger, not a calibrated probability for the realized play.
export function cumulativeRisk(play,time,passes=[]) {
  // The scoring attempt already includes rebound continuation value. Stop its
  // survival discount at the first shot, shared by scoreboard and recap.
  const firstShot=(play.events||[]).filter(e=>e.type==='shot').reduce((at,e)=>Math.min(at,e.frame),Infinity);
  time=Math.min(time,firstShot);
  const actions=passes.filter(p=>p.possession===play.id && p.start<=time);
  let survival=1,covered=0,elapsed=0,passCount=0;
  for(let i=0;i<play.frames.length-1;i++) {
    const f=play.frames[i],next=play.frames[i+1];if(f.frame>=time)break;
    const end=Math.min(time,next.frame),span=end-f.frame;
    elapsed+=span/25;
    if(span<=0 || next.frame-f.frame>10 || f.reason || !Number.isFinite(f.turnover2))continue;
    const overlaps=actions.map(p=>[Math.max(f.frame,p.start),Math.min(end,p.end)])
      .filter(([a,b])=>b>a).sort((a,b)=>a[0]-b[0]);
    let flightFrames=0,last=-Infinity;
    for(const [a,b] of overlaps){flightFrames+=Math.max(0,b-Math.max(a,last));last=Math.max(last,b);}
    const dt=(span-flightFrames)/25;
    survival*=Math.pow(1-Math.max(0,Math.min(1,f.turnover2)),dt/2);covered+=dt;
  }
  const seen=new Set();
  for(const p of actions) {
    const id=`${p.start}:${p.passer}:${p.receiver}`;if(seen.has(id))continue;seen.add(id);
    const risk=passWithRisk(p,play.frames)?.turnoverProbability;
    if(!Number.isFinite(risk))continue;
    survival*=1-Math.max(0,Math.min(1,risk));passCount++;
  }
  return {risk:covered||passCount?1-survival:time<=play.frames[0]?.frame?0:null,
    covered,elapsed,passCount};
}
