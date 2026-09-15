// Conservative geometry screen, not a learned policy or causal EPV forecast.
const dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
const point=p=>[p[1],p[2]];
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
function segmentDistance(p,a,b){const dx=b[0]-a[0],dy=b[1]-a[1],t=clamp(((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy||1),0,1);return {distance:dist(p,[a[0]+dx*t,a[1]+dy*t]),fraction:t};}
function toward(a,b,length){const d=dist(a,b);return d?[a[0]+(b[0]-a[0])*Math.min(1,length/d),a[1]+(b[1]-a[1])*Math.min(1,length/d)]:a;}
const grids=new WeakMap();
function lookup(grid,q){if(!grids.has(grid))grids.set(grid,new Map(grid.cells.map(([x,y,v])=>[`${x},${y}`,v])));return grids.get(grid).get(`${Math.floor(q[0])},${Math.floor(q[1])}`);}
function three(q){return Math.abs(q[1])>21.6535||dist(q,[-40.75,0])>22.146;}
export function movementIdea(frame,previous,grid,profile=()=>({}), selectedPlayer=null){
  if(!grid||frame.reason||frame.offense.length!==5||frame.defense.length!==5||frame.shotClock<3)return null;
  const holder=frame.offense.find(p=>p[0]===frame.geometry?.handler);
  if(!holder||!holder[3])return null;
  const origin=point(holder),dt=(frame.frame-(previous?.frame??frame.frame))/25;
  const defenders=frame.defense.map(p=>{
    const old=previous?.defense.find(q=>q[0]===p[0]);
    const velocity=old&&dt>0&&dt<=.4?[(p[1]-old[1])/dt,(p[2]-old[2])/dt]:[0,0];
    const speed=Math.hypot(...velocity);return {p:point(p),v:velocity.map(v=>v*Math.min(1,12/(speed||1))),error:clamp((p[4]||0)/2.146,0,2)};
  });
  let best=null;
  for(const player of frame.offense){
    if(selectedPlayer!=null && player[0]!==selectedPlayer)continue;
    if(player[0]===holder[0]||!player[3]||player[4]>3)continue;
    const start=point(player),baseValue=lookup(grid,start);if(!Number.isFinite(baseValue))continue;
    const nearest=defenders.reduce((a,d,i)=>dist(d.p,start)<dist(defenders[a].p,start)?i:a,0);
    for(const length of [4,6,8])for(let angle=0;angle<16;angle++){
      const a=angle*Math.PI/8,q=[start[0]+Math.cos(a)*length,start[1]+Math.sin(a)*length];
      if(q[0]<-44||q[0]>-3||Math.abs(q[1])>23||dist(q,origin)<5)continue;
      // Do not recommend an unsupported three to a sparse-volume shooter.
      if(three(q)&&(profile(player[0]).sampleThreePa??profile(player[0]).three??0)<20)continue;
      const value=lookup(grid,q);if(!Number.isFinite(value))continue;
      if(frame.offense.some(p=>p[0]!==player[0]&&(dist(point(p),q)<5||segmentDistance(point(p),start,q).distance<2)))continue;
      if(defenders.some(d=>segmentDistance(d.p,start,q).distance<2+d.error*.3))continue;
      const moveTime=length/10,passTime=dist(origin,q)/40+.12;
      if(moveTime+passTime+.5>frame.shotClock)continue;
      let gain=Infinity,clearGain=Infinity,margin=Infinity;
      const outcomes=[];
      for(const response of ['hold','momentum','close']){
        const positions=defenders.map((d,i)=>response==='hold'?d.p:response==='close'&&i===nearest?toward(d.p,q,12*Math.max(0,moveTime-.2)):[d.p[0]+d.v[0]*moveTime,d.p[1]+d.v[1]*moveTime]);
        const evalSpot=spot=>{
          const separation=Math.min(...positions.map((p,i)=>dist(p,spot)-defenders[i].error*.3));
          const route=Math.min(...positions.map((p,i)=>{const r=segmentDistance(p,origin,spot);return r.distance-2-defenders[i].error*.3-12*Math.max(0,dist(origin,spot)/40*r.fraction-.2);}));
          const quality=lookup(grid,spot);
          return {separation,route,score:quality*clamp((separation-2)/6,0,1)*clamp((route+1)/4,0,1)};
        };
        const teammates=frame.offense.filter(p=>p[0]!==player[0]);
        const teamScore=()=>teammates.map(p=> {
          const spot=point(p),v=lookup(grid,spot);
          if(!Number.isFinite(v))return 0;
          const clearance=Math.min(...positions.map(d=>dist(d,spot)));
          return v*clamp((clearance-2)/6,0,1);
        }).sort((a,b)=>b-a).slice(0,2).reduce((a,b)=>a+b,0)/2;
        const after=evalSpot(q),teamAfter=teamScore();
        // Staying gets its own closeout response toward the original spot.
        if(response==='close')positions[nearest]=toward(defenders[nearest].p,start,12*Math.max(0,moveTime-.2));
        const stay=evalSpot(start),teamGain=teamAfter-teamScore();
        outcomes.push({response,own:after.score-stay.score,team:teamGain,total:after.score-stay.score+.6*teamGain,route:after.route});
        gain=Math.min(gain,after.score-stay.score);clearGain=Math.min(clearGain,after.separation-stay.separation);margin=Math.min(margin,after.route);

      }
      const average=outcomes.reduce((a,b)=>a+b.total,0)/outcomes.length;
      const worst=Math.min(...outcomes.map(o=>o.total));
      const teamGain=outcomes.reduce((a,b)=>a+b.team,0)/outcomes.length;
      const positive=outcomes.filter(o=>o.total>.02).length;
      // Exploration accepts response-dependent benefits, but never invents a win.
      if(average<=.015||positive===0)continue;
      const clear=gain>=.12&&clearGain>=1.5&&margin>=.3&&worst>.05;
      const rank=average+.25*Math.min(0,worst);
      if(!best||rank>best.rank)best={player:player[0],from:start,to:q,gain,clearGain,margin,seconds:moveTime,rank,average,worst,teamGain,outcomes,
        confidence:clear?'Clear improvement':'Worth exploring',
        tradeoff:worst<-.02?'A defensive response can erase the benefit':margin<.3?'Passing access remains contested in some responses':'Benefit depends on how the defense responds',
        reason:teamGain>.035?'May create space for teammates if the defender follows':dist(q,[-40.75,0])<dist(start,[-40.75,0])-3?'Explore a cut toward the rim':'Explore a clearer receiving spot'};
    }
  }
  return best;
}
export function drawMovementIdea(ctx,idea,project,unit){
  if(!idea)return;
  const a=project(idea.from),b=project(idea.to);if(!a||!b)return;
  const dx=b[0]-a[0],dy=b[1]-a[1],d=Math.hypot(dx,dy);if(d<unit*2)return;
  const ux=dx/d,uy=dy/d,start=[a[0]+ux*unit*1.7,a[1]+uy*unit*1.7];
  ctx.save();ctx.strokeStyle=idea.confidence==='Clear improvement'?'#248ba9':'#99713c';ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=unit*.12;ctx.setLineDash([unit*.35,unit*.25]);
  ctx.beginPath();ctx.moveTo(...start);ctx.lineTo(...b);ctx.stroke();ctx.setLineDash([]);
  ctx.beginPath();ctx.arc(...b,unit*.52,0,Math.PI*2);ctx.stroke();
  ctx.beginPath();ctx.moveTo(...b);ctx.lineTo(b[0]-ux*unit*.65+uy*unit*.3,b[1]-uy*unit*.65-ux*unit*.3);ctx.lineTo(b[0]-ux*unit*.65-uy*unit*.3,b[1]-uy*unit*.65+ux*unit*.3);ctx.closePath();ctx.fill();ctx.restore();
}
