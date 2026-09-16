// Short replay-derived trail: seeking cannot leave stale screen-space history.
export function ballTrail(frames, current, time) {
  const samples = frames.filter(f => f.period === current.period && f.frame < time && time-f.frame <= 10 && f.ball?.slice(0,3).every(Number.isFinite));
  const points=[];let next=time;
  for(let i=samples.length-1;i>=0;i--){
    const f=samples[i];if(next-f.frame>6)break;
    points.unshift({ball:f.ball,alpha:Math.max(0,1-(time-f.frame)/11)});next=f.frame;
  }
  points.push({ball:current.ball,alpha:1});return points;
}
export function drawBallTrail(ctx, samples, project, width, passing=false) {
  ctx.save();ctx.lineCap='round';
  for(let i=1;i<samples.length;i++){
    const a=project(samples[i-1].ball),b=project(samples[i].ball);
    if(!a||!b)continue;
    ctx.strokeStyle=`rgba(242,180,64,${samples[i-1].alpha*(passing?.85:.42)})`;
    ctx.lineWidth=width*(passing?1.7:1)*(.35+.65*samples[i].alpha);
    ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();
  }
  ctx.restore();
}
