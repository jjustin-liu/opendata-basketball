// A volume badge, not an estimate of three-point accuracy or gravity.
export function highVolumeThree(profile) {
  return profile.possessions >= 100 && Number.isFinite(profile.threePer100) && profile.threePer100 >= 6;
}

export function frequentDriver(profile) {
  return profile.drivePossessions >= 500 && Number.isFinite(profile.drivesPer100) && profile.drivesPer100 >= 20;
}

export function tendencyLabels(profile) {
  return [highVolumeThree(profile) ? '3P' : '', frequentDriver(profile) ? 'DRIVER' : ''].filter(Boolean).join(' · ');
}

function drawTendencies(ctx,x,y,radius,profile) {
  const label=tendencyLabels(profile);
  if (!label) return;
  ctx.font='700 .57px monospace';
  ctx.fillStyle='#235b4c';
  const orbit=radius+.35;
  const widths=[...label].map(c=>ctx.measureText(c).width+.035);
  let cursor=-widths.reduce((a,b)=>a+b,0)/2;
  [...label].forEach((char,i)=>{
    const angle=(cursor+widths[i]/2)/orbit;
    ctx.save();ctx.translate(x,y);ctx.rotate(angle);ctx.translate(0,-orbit);
    ctx.fillText(char,0,0);ctx.restore();cursor+=widths[i];
  });
}

export function compactPlayer(ctx,x,y,radius,{position,profile,text,color,risk}) {
  ctx.save();
  ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.font='600 1.05px monospace';ctx.fillStyle=color;
  ctx.fillText(text,x,y-.3,radius*1.8);
  // Position overlaps the lower inside edge, leaving the EPV prominent.
  const py=y+radius*.7;
  ctx.fillStyle='rgba(12,18,22,.78)';
  ctx.beginPath();ctx.roundRect(x-.58,py-.5,1.16,1,.22);ctx.fill();
  ctx.font='700 .94px sans-serif';ctx.fillStyle='#dce6e9';
  ctx.fillText(position,x,py);
  if (Number.isFinite(risk)) {
    ctx.fillStyle='#263238';ctx.font='700 .78px monospace';
    ctx.fillText(`${(risk*100).toFixed(1)}%`,x+radius+1.2,y-.32);
    ctx.font='600 .48px monospace';ctx.fillText('TOV',x+radius+1.2,y+.4);
  }
  drawTendencies(ctx,x,y,radius,profile);
  ctx.restore();
}
