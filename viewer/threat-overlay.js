// View 7: action threat drawn on the action it threatens, not on every defender.
// STL rides the chosen pass line as one tick; BLK rides the holder as one arc.
// Alpha uses fixed anchors from the credited-event any-event probability, so a
// contested action looks different from a routine one across possessions.
import { defenderForecast } from "./defender-label.js?v=flight-risk-1";

// Floor: nothing drawn below. Full: maximum alpha at or above.
// Pass any-interception spans roughly 1.0%–2.2% (p5–p99); shot any-block 0.4%–8% (p5–p99).
export const STEAL_ANCHORS = { floor: 0.010, full: 0.022 };
export const BLOCK_ANCHORS = { floor: 0.010, full: 0.080 };
const TEAL = "#087a69", AMBER = "#a96009";

export function threatStrength(probability, anchors) {
  if (!Number.isFinite(probability) || probability < anchors.floor) return 0;
  return Math.min(1, (probability - anchors.floor) / (anchors.full - anchors.floor));
}

// Leading defender and how clearly they lead the field (top / second).
function leader(forecast) {
  const sorted = (forecast?.defenders || []).slice().sort((a, b) => b.probability - a.probability);
  if (!sorted.length) return null;
  const second = sorted[1]?.probability ?? 0;
  const margin = second > 0 ? sorted[0].probability / second : 4;
  return { player: sorted[0].player, probability: sorted[0].probability,
    // Identification confidence: 1.0x (a coin flip) → 0, 1.35x → 1.
    clarity: Math.max(0, Math.min(1, (margin - 1) / 0.35)) };
}

export function threatScenarios(frame, receiver = null) {
  const pass = defenderForecast(frame, "steal", receiver);
  const shot = defenderForecast(frame, "block");
  return {
    pass: pass ? { forecast: pass, receiver: pass.receiver, any: pass.anyEventProbability,
      strength: threatStrength(pass.anyEventProbability, STEAL_ANCHORS), lead: leader(pass) } : null,
    shot: shot ? { forecast: shot, any: shot.anyEventProbability,
      strength: threatStrength(shot.anyEventProbability, BLOCK_ANCHORS), lead: leader(shot) } : null,
  };
}

// Court-plane drawing in the 2D canvas convention (x, -y). `layer` is "under"
// (hairlines beneath the chips) or "over" (tick, arc, hover rings above them).
export function drawThreatOverlay(ctx, frame, opts) {
  const { holder, receiver, layer, chipRadius, radiusOf, expanded, hover } = opts;
  if (!holder) return;
  const { pass, shot } = threatScenarios(frame, opts.selectedPass);
  const at = (id) => frame.defense.find((p) => p[0] === id);
  const H = [holder[1], -holder[2]];
  ctx.save();
  ctx.lineCap = "round";

  // STL: one tick on the pass line at the leading interceptor's projection point.
  if (pass && receiver && pass.strength > 0) {
    const R = [receiver[1], -receiver[2]];
    const D = at(pass.lead?.player);
    const dx = R[0] - H[0], dy = R[1] - H[1], len2 = dx * dx + dy * dy || 1;
    // Keep the tick on the visible part of the line, clear of both chips.
    const len = Math.sqrt(len2), margin = Math.min(0.45, (chipRadius + 0.7) / len);
    let t = 0.5;
    if (D) t = Math.max(margin, Math.min(1 - margin, ((D[1] - H[0]) * dx + (-D[2] - H[1]) * dy) / len2));
    const T = [H[0] + t * dx, H[1] + t * dy];
    const alpha = 0.25 + 0.75 * pass.strength;
    const nx = -dy / Math.sqrt(len2), ny = dx / Math.sqrt(len2);
    if (layer === "under" && D && pass.lead.clarity > 0) {
      ctx.globalAlpha = alpha * pass.lead.clarity * 0.9;
      ctx.strokeStyle = TEAL; ctx.lineWidth = 0.09; ctx.setLineDash([0.45, 0.4]);
      ctx.beginPath(); ctx.moveTo(D[1], -D[2]); ctx.lineTo(T[0], T[1]); ctx.stroke();
      ctx.setLineDash([]);
    }
    if (layer === "over") {
      const half = 0.55 + 0.45 * pass.strength;
      ctx.globalAlpha = alpha; ctx.strokeStyle = TEAL; ctx.lineWidth = 0.22 + 0.16 * pass.strength;
      ctx.beginPath(); ctx.moveTo(T[0] - nx * half, T[1] - ny * half); ctx.lineTo(T[0] + nx * half, T[1] + ny * half); ctx.stroke();
    }
  }

  // BLK: one arc on the holder chip facing the leading blocker.
  if (shot && shot.strength > 0) {
    const D = at(shot.lead?.player);
    const bearing = D ? Math.atan2(-D[2] - H[1], D[1] - H[0]) : Math.atan2(0 - H[1], -40.75 - H[0]);
    const r = chipRadius + 0.55;
    const alpha = 0.25 + 0.75 * shot.strength;
    const span = (Math.PI / 180) * (50 + 30 * shot.strength);
    if (layer === "under" && D && shot.lead.clarity > 0) {
      ctx.globalAlpha = alpha * shot.lead.clarity * 0.9;
      ctx.strokeStyle = AMBER; ctx.lineWidth = 0.09; ctx.setLineDash([0.45, 0.4]);
      ctx.beginPath(); ctx.moveTo(D[1], -D[2]); ctx.lineTo(H[0] + Math.cos(bearing) * (r + 0.2), H[1] + Math.sin(bearing) * (r + 0.2)); ctx.stroke();
      ctx.setLineDash([]);
    }
    if (layer === "over") {
      ctx.globalAlpha = alpha; ctx.strokeStyle = AMBER; ctx.lineWidth = 0.26 + 0.2 * shot.strength;
      ctx.beginPath(); ctx.arc(H[0], H[1], r, bearing - span / 2, bearing + span / 2); ctx.stroke();
    }
  }

  // Progressive disclosure: hovering the holder or any defender (or the detail
  // toggle) expands to all five defenders as thin rings, arc length = share of
  // that scenario's defender mass. Steal ring inside, block ring outside.
  const showAll = layer === "over" && (expanded || (hover != null && (hover === holder[0] || frame.defense.some((d) => d[0] === hover))));
  if (showAll) {
    for (const [scenario, color, offset] of [[pass, TEAL, 0.45], [shot, AMBER, 0.85]]) {
      if (!scenario) continue;
      const mass = scenario.forecast.defenders.reduce((a, d) => a + d.probability, 0) || 1;
      for (const d of scenario.forecast.defenders) {
        const P = at(d.player); if (!P) continue;
        const share = d.probability / mass;
        ctx.globalAlpha = 0.85; ctx.strokeStyle = color; ctx.lineWidth = 0.16;
        ctx.beginPath(); ctx.arc(P[1], -P[2], radiusOf(d.player) + offset, -Math.PI / 2, -Math.PI / 2 + share * Math.PI * 2); ctx.stroke();
      }
    }
  }
  ctx.restore();
}
