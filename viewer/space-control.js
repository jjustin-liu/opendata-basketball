// Exploratory arrival-time surface; not a calibrated control or scoring model.
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
function arrival(p,old,dt,x,y){
  const dx=x-p[1],dy=y-p[2],distance=Math.hypot(dx,dy);
  const vx=old&&dt>0&&dt<=.4?clamp((p[1]-old[1])/dt,-14,14):0;
  const vy=old&&dt>0&&dt<=.4?clamp((p[2]-old[2])/dt,-14,14):0;
  const speed=distance?clamp((vx*dx+vy*dy)/distance,-14,14):0;
  const acceleration=10,maxSpeed=14, tCap=(maxSpeed-speed)/acceleration;
  const dCap=speed*tCap+.5*acceleration*tCap*tCap;
  const t=distance<=dCap?(-speed+Math.sqrt(speed*speed+2*acceleration*distance))/acceleration:tCap+(distance-dCap)/maxSpeed;
  // predError is a 90% radial distance bound; isotropic Gaussian approximation.
  return {t,sigma:Math.max(.06,(Number.isFinite(p[4])?p[4]:4)/2.146/Math.max(4,speed+acceleration*t))};
}
export function spaceControl(frame,previous,grid){
  if(frame.reason||frame.offense.length!==5||frame.defense.length!==5||!grid)return {cells:[],area:0};
  const dt=(frame.frame-(previous?.frame??frame.frame))/25;
  let area=0;const cells=[];
  for(const [x,y,value] of grid.cells){
    const fastest=side=>frame[side].map(p=>arrival(p,previous?.[side]?.find(q=>q[0]===p[0]),dt,x+.5,y+.5)).reduce((a,b)=>a.t<b.t?a:b);
    const off=fastest('offense'),def=fastest('defense');
    if(off.t>Math.min(2,frame.shotClock??2))continue;
    const sigma=Math.hypot(off.sigma,def.sigma,.12);
    const control=1/(1+Math.exp(-1.702*(def.t-off.t)/sigma));
    const score=control*value;
    if(score<.5)continue;
    area+=1;
    cells.push({corners:[[x,y],[x+1,y],[x+1,y+1],[x,y+1]],alpha:.12+.32*clamp((score-.5)/.9,0,1),score});
  }
  return {cells,area};
}
