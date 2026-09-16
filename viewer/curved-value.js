// A straight EPV cap straddles the top edge of a position chip.
export function capOffset(radius, width, height, ball) {
  if (!ball) return -radius;
  const dx = Math.max(Math.abs(ball.x) - width / 2, 0);
  const dy = Math.max(Math.abs(ball.y + radius) - height / 2, 0);
  return Math.hypot(dx, dy) <= ball.radius + .2 ? radius : -radius;
}

export function curvedValue(ctx, x, y, radius, text, color, secondary = '', ball = null) {
  ctx.save();
  ctx.translate(x, y);
  ctx.font = '700 1.18px "IBM Plex Mono", monospace';
  const width = Math.max(ctx.measureText(text).width, ctx.measureText('0.00').width) + .62;
  const height = 1.46;
  const capY = capOffset(radius, width, height, ball && { x: ball.x - x, y: ball.y - y, radius: ball.radius });
  ctx.beginPath();
  ctx.roundRect(-width / 2, capY - height / 2, width, height, .27);
  ctx.fillStyle = 'rgba(12,18,22,.78)';
  ctx.fill();
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = color;
  ctx.fillText(text, 0, capY);
  if (secondary) {
    const percentage = secondary.match(/^[\d.]+%/)?.[0];
    const sideX = radius + 1.3;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = '#263238';
    ctx.font = '700 .96px "IBM Plex Mono", monospace';
    ctx.fillText(percentage || secondary, sideX, percentage ? -.38 : 0);
    if (percentage) {
      ctx.font = '600 .6px "IBM Plex Mono", monospace';
      ctx.fillStyle = '#465259';
      ctx.fillText('TOV', sideX, .48);
    }
  }
  ctx.restore();
}
