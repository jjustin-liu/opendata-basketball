export function simulatedMovement(data,playId,frame,selected=null) {
  if (!data || frame.reason) return null;
  const source=Math.floor(frame.frame/10)*10;
  if (frame.frame-source>=10) return null;
  const candidates=(data.plays?.[playId]?.[String(source)] || [])
    .filter(c=>(selected==null || c.player===selected) && c.low>=.01
      && c.player!==frame.geometry?.handler && frame.offense.some(p=>p[0]===c.player));
  const best=candidates.reduce((a,b)=>!a || b.low>a.low?b:a,null);
  if (!best) return null;
  const p=frame.offense.find(p=>p[0]===best.player);
  return {...best,from:[p[1],p[2]],confidence:'Clear improvement',estimated:true};
}

export function defensiveMovement(data,playId,frame) {
  if (!data || data.version!==2 || frame.reason) return null;
  // Coordinates are normalized toward the left basket. Avoid transition and
  // trailing defenders: this positional sensitivity is only for a set defense.
  const holder=frame.offense?.find(p=>p[0]===frame.geometry?.handler);
  if(!holder || holder[1]>-10 || frame.offense.length!==5 || frame.defense.length!==5
    || frame.offense.some(p=>p[1]>=-1) || frame.defense.some(p=>p[1]>=-1)) return null;
  const source=Math.floor(frame.frame/25)*25;
  if(frame.frame-source>10)return null;
  const candidates=data.plays?.[playId]?.[String(source)] || [];
  const best=candidates.filter(c=>c.responseChecked && c.gain>=.01 && c.to[0]<=holder[1]+2
    && frame.defense.some(p=>p[0]===c.player && p[1]<=holder[1]+2 && (!c.origin || Math.hypot(p[1]-c.origin[0],p[2]-c.origin[1])<=1.5))
    && (!c.ball || Math.hypot(frame.ball[0]-c.ball[0],frame.ball[1]-c.ball[1])<=3))
    .reduce((a,b)=>!a || b.gain>a.gain?b:a,null);
  if(!best)return null;
  const p=frame.defense.find(p=>p[0]===best.player);
  return {...best,side:'defense',from:[p[1],p[2]],confidence:'Defensive shift',estimated:true};
}
