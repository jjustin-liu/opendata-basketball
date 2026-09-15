// Project a court-plane tangent perpendicular to the player's rim bearing.
export function rimWingAngle(project, x, y) {
  const dx = -40.75 - x, dy = -y;
  const distance = Math.hypot(dx, dy);
  const tx = distance > .001 ? -dy / distance : 0;
  const ty = distance > .001 ? dx / distance : 1;
  const a = project(x - tx, y - ty, 0);
  const b = project(x + tx, y + ty, 0);
  return Math.atan2(b[1] - a[1], b[0] - a[0]);
}

export function defenderForecast(frame, kind, receiver = null) {
  if (frame?.actionDefense) {
    if (kind === 'block') return frame.actionDefense.shot?.enabled ? frame.actionDefense.shot : null;
    const passes = frame.actionDefense.passes || [];
    const selected = passes.find(p => p.receiver === receiver);
    if (selected) return selected;
    const best = (frame.passOptions || []).filter(o => passes.some(p => p.receiver === o.player))
      .reduce((a,b) => !a || b.value > a.value ? b : a, null);
    return passes.find(p => p.receiver === best?.player) || null;
  }
  const forecast = frame?.[kind + 'Forecast'];
  return forecast?.enabled ? forecast : null;
}

export function defenderProbability(frame, kind, player, receiver = null) {
  return defenderForecast(frame, kind, receiver)?.defenders.find(d => d.player === player)?.probability ?? null;
}

const referenceCache = new WeakMap();
// Freeze the reference at the first supported state, never at each animation frame.
export function defenderThreatReference(frames) {
  if (referenceCache.has(frames)) return referenceCache.get(frames);
  const reference = {};
  for (const kind of ['steal', 'block']) {
    const initial = frames.find(f => defenderForecast(f, kind));
    const values = defenderForecast(initial, kind)?.defenders.map(d => d.probability) || [];
    reference[kind] = values.length ? values.reduce((a,b) => a+b, 0) / values.length : 0;
  }
  referenceCache.set(frames, reference);
  return reference;
}

export function defenderThreatStrength(probability, reference, kind) {
  if (!Number.isFinite(probability) || probability <= 0) return 0;
  const floor = kind === 'block' ? .0005 : .001;
  const baseline = Math.max(reference || 0, floor);
  // Relative prominence with an absolute floor: five negligible risks stay subdued.
  return Math.min(1, probability / (2 * baseline));
}

// Typography follows the outside rim; only the position stays inside.
export function drawDefenderLabel(ctx, x, y, radius, profile, frame, player, position, lightCourt = false, threat = {}) {
  const surname = (profile.name || 'Defender').trim().split(/\s+/).slice(-1)[0].toUpperCase();
  ctx.save();
  ctx.translate(x, y);
  const steal = defenderProbability(frame, 'steal', player, threat.receiver);
  const block = defenderProbability(frame, 'block', player);
  const wingStrength = defenderThreatStrength(steal, threat.reference?.steal, 'steal');
  const tail = defenderThreatStrength(block, threat.reference?.block, 'block');
  const unit = threat.unit ?? radius; // Camera scale only, before position sizing.
  // Probability glyphs, not physical reach: drawn behind the identity chip.
  if (threat.enabled !== false && wingStrength > 0) {
    ctx.save();
    ctx.rotate(threat.wingAngle || 0);
    ctx.globalAlpha = .3 + .7 * wingStrength;
    ctx.strokeStyle = lightCourt ? '#087a69' : '#20ae98';
    ctx.lineWidth = unit * (.1 + .16 * wingStrength);
    ctx.lineCap = 'round';
    const span = unit * (1.25 + 2.7 * wingStrength);
    for (const side of [-1, 1]) {
      ctx.beginPath(); ctx.moveTo(side * unit * .82, 0);
      ctx.lineTo(side * span, 0); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(side * span, -unit * .22);
      ctx.lineTo(side * span, unit * .22); ctx.stroke();
    }
    ctx.restore();
  }
  if (threat.enabled !== false && tail > 0) {
    ctx.save();
    const rise = unit * (1.1 + 2.4 * tail);
    const reach = unit * (1.25 + .65 * tail);
    ctx.globalAlpha = .3 + .7 * tail;
    ctx.strokeStyle = lightCourt ? '#a96009' : '#ffc25b';
    ctx.fillStyle = ctx.strokeStyle;
    ctx.lineWidth = unit * (.07 + .13 * tail);
    ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(unit*.7,-unit*.6);
    ctx.bezierCurveTo(reach*1.35, -unit*.5, reach*1.3, -rise*1.2, reach*.5, -rise);
    ctx.stroke();
    ctx.beginPath(); ctx.moveTo(reach*.5-unit*.22,-rise+unit*.25);
    ctx.lineTo(reach*.5-unit*.12,-rise-unit*.12); ctx.lineTo(reach*.5+unit*.22,-rise+unit*.03); ctx.closePath(); ctx.fill();
    ctx.restore();
  }
  ctx.beginPath();
  ctx.arc(0, 0, radius * .94, 0, Math.PI * 2);
  ctx.fillStyle = '#ffffff';
  ctx.fill();
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.font = `700 ${radius * 1.25}px "DM Sans", sans-serif`;
  ctx.fillStyle = '#718092';
  ctx.fillText(position, 0, 0);

  function rimText(text, orbit, fontSize, bottom, color) {
    ctx.font = `600 ${fontSize}px "IBM Plex Mono", monospace`;
    const chars = [...text];
    const widths = chars.map(c => ctx.measureText(c).width + fontSize * .04);
    const total = widths.reduce((a,b) => a+b, 0);
    const spacing = Math.min(1, orbit * Math.PI * .93 / total);
    let cursor = -total * spacing / 2;
    for (let i = 0; i < chars.length; i++) {
      const advance = widths[i] * spacing;
      const offset = (cursor + advance / 2) / orbit;
      const angle = bottom ? Math.PI / 2 - offset : -Math.PI / 2 + offset;
      ctx.save();
      ctx.translate(Math.cos(angle) * orbit, Math.sin(angle) * orbit);
      ctx.rotate(bottom ? angle - Math.PI / 2 : angle + Math.PI / 2);
      ctx.fillStyle = color;
      ctx.fillText(chars[i], 0, 0);
      ctx.restore();
      cursor += advance;
    }
  }
  rimText(surname, radius * 1.34, radius * .4, false, lightCourt ? '#243a50' : '#e0e9f3');
  // Exact action probabilities are available in the player hover tooltip.
  ctx.restore();
}
