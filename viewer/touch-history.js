import { shotPps } from './action-display.js?v=foul-4';

// A catch estimate is the first supported sample within 0.4s of receipt.
// All rows are cut off at replay time; release values use pre-release samples.
export function touchHistory(play, touches, passes, time, epvKey = 'epv') {
  return (touches || []).filter(t=>t.start<=time).map(t=>{
    const ended=time>=t.end;
    const samples=play.frames.filter(f=>f.frame>=t.start && f.frame<Math.min(t.end,time+.001)
      && !f.reason && f.geometry?.handler===t.player);
    const first=samples.find(f=>f.frame-t.start<=10 && Number.isFinite(f[epvKey]));
    const last=samples.filter(f=>Number.isFinite(f[epvKey])).at(-1);
    const endSample=last && Math.min(t.end,time)-last.frame<=10 ? last : null;
    const pass=ended ? (passes || []).find(p=>p.possession===play.id && p.passer===t.player && Math.abs(p.start-t.end)<=2) : null;
    const shot=ended ? (play.events || []).find(e=>e.type==='shot' && e.player===t.player && Math.abs(e.frame-t.end)<=2 && e.frame<=time) : null;
    const prior=pass ? play.frames.filter(f=>f.frame<pass.start && pass.start-f.frame<=10 && !f.reason && f.geometry?.handler===t.player).at(-1) : null;
    const option=prior?.passOptions?.find(p=>p.player===pass.receiver);
    const risks=samples.map(f=>f.turnover2).filter(Number.isFinite);
    const catchEpv=first?.[epvKey] ?? null, endEpv=endSample?.[epvKey] ?? null;
    const actionValue=pass?option?.value:shot?shotPps(shot):null;
    const preActionEpv=pass?prior?.[epvKey]:endEpv;
    return {...t,ended,seconds:Math.max(0,Math.min(t.end,time)-t.start)/25,
      catchEpv,endEpv,change:Number.isFinite(catchEpv)&&Number.isFinite(endEpv)?endEpv-catchEpv:null,
      decisionChange:Number.isFinite(actionValue)&&Number.isFinite(preActionEpv)?actionValue-preActionEpv:null,
      risk:ended ? risks.at(-1)??null : endSample?.turnover2??null,peakRisk:risks.length?Math.max(...risks):null,
      action:pass?'PASS':shot?'SHOT':ended?'RELEASED':'HOLDING',receiver:pass?.receiver,
      passEpv:option?.value??null,passRisk:option?.turnoverProbability??null,
      projectedCatch:option?.completedEpv??null,pps:shot?shotPps(shot):null};
  });
}
