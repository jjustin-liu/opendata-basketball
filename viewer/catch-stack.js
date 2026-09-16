// Flight easing is visual, not a conditional-risk model. C&S assumes a catch.
export function displayedCatchEpv(option, frame) {
  const discounted = Number.isFinite(option.value) ? option.value : option.epv;
  if (!Number.isFinite(discounted)) return null;
  if (!Number.isFinite(frame) || !Number.isFinite(option.start) ||
      !Number.isFinite(option.end) || option.end <= option.start ||
      !Number.isFinite(option.completedEpv)) return discounted;
  const t = Math.max(0, Math.min(1, (frame-option.start)/(option.end-option.start)));
  return discounted + (option.completedEpv-discounted)*t*t*(3-2*t);
}

// `scale` enlarges the readout text without moving the stack off the chip.
export function drawCatchStack(ctx, x, y, r, flight, frame, scale = 1) {
  ctx.save();
  ctx.textAlign='center'; ctx.textBaseline='middle';
  for (const [value, label, direction] of [[displayedCatchEpv(flight,frame),'EPV',-1],[flight.catchShot?.pps,'C&S',1]]) {
    const cy=y+direction*r;
    ctx.font=`700 ${r*.56*scale}px monospace`;
    const text=Number.isFinite(value)?value.toFixed(2):'—';
    const w=Math.max(ctx.measureText(text).width,r*1.4)+r*.22;
    const h=r*.72*scale;
    ctx.fillStyle='rgba(12,18,22,.82)';ctx.beginPath();
    ctx.roundRect(x-w/2,cy-h/2,w,h,r*.12);ctx.fill();
    ctx.fillStyle='#d9f5df';ctx.fillText(text,x,cy);
    ctx.font=`700 ${r*.34*scale}px monospace`;ctx.fillStyle='#253d35';
    ctx.fillText(label,x,cy+direction*(h/2+r*.26*scale));
  }
  if (Number.isFinite(flight.turnoverProbability)) {
    const sideX=x+r*1.6;
    ctx.fillStyle='#263238';
    ctx.font=`700 ${r*.45*scale}px monospace`;
    ctx.fillText(`${(flight.turnoverProbability*100).toFixed(1)}%`,sideX,y-r*.18);
    ctx.font=`600 ${r*.28*scale}px monospace`;
    ctx.fillStyle='#465259';
    ctx.fillText('TOV',sideX,y+r*.24);
  }
  ctx.restore();
}
