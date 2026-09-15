import { movementIdea, drawMovementIdea } from "./movement-ideas.js?v=2";
const movementCache = new WeakMap();
import { ballTrail, drawBallTrail } from "./ball-trail.js";
import { spaceControl } from "./space-control.js?v=1";
let spaceGrids = {};
const spaceCache = new WeakMap();
import { drawRealistic } from "./realistic.js?v=realistic-2";
import { drawDefenderLabel, defenderProbability, defenderForecast, defenderThreatReference, rimWingAngle } from "./defender-label.js?v=names-toggle-2";
import { drawThreatOverlay } from "./threat-overlay.js?v=1";
import { auditShot } from "./decision-audit.js?v=foul-4";
import { shotReview } from "./shot-review.js";
import { followPass } from "./follow-pass.js";
import { activePass, flightLabel, passWithRisk } from "./pass-flight.js?v=flight-risk-1";
import { playerProfile, profileTab, defenderNumbers, defenderChipScale } from "./player-profile.js?v=position-size-1";
import { bestPass, shotPps, actionCard } from "./action-display.js";
import { driveSpace } from "./drive-space.js";
import { ballRiskColor } from "./ball-risk-color.js";
import { curvedValue } from "./curved-value.js?v=avoid-ball-5";
import { closestDefender, drawDefenderDistance } from "./defender-distance.js?v=distance-2";
import { drawCourt3D } from "./court3d.js?v=closer-card-4";
import { interpolateFrame } from "./playback.js";
let surrogateReport = null;
let tacticalView = false;
let realisticView = false;
let positionView = false;
let threatView = false;
let hoverPlayer = null;
const courtZoom = { flat: 1, wide: 1, follow: 1, tactical: 1 };
function resetZoom(mode) { courtZoom[mode] = 1; zoomOffsets[mode] = [0, 0]; }
const zoomOffsets = { flat: [0, 0], wide: [0, 0], follow: [0, 0], tactical: [0, 0] };
const zoomMode = () => !$("view3d").checked ? "flat" : tacticalView ? "tactical" : cameraPlayer === null ? "wide" : "follow";
let lookYaw = 0, lookPitch = 0, lookDrag = null, suppressCourtClick = false;
const $ = (id) => document.getElementById(id);
const colors = {
  off: "#151719",
  def: "#4169a1",
  ball: "#f2b440",
  teal: "#5ed5be",
  coral: "#f18b78",
};
let auditFocus = null;
let manifest,
  game,
  play,
  index = 0,
  playing = false,
  lastTime = 0,
  requestId = 0,
  visiblePlays = [],
  courtTransform,
  courtHits = [],
  driveCacheFrame = null,
  driveCache = [],
  cameraFollow = null,
  cameraPlayer = null,
  animationPhase = 0,
  selectedPass = null;
// Fixed point scale so a color means the same value across frames and players.
function epvColor(value) {
  if (!Number.isFinite(value)) return "#a8afb5";
  const low = [255, 112, 112],
    mid = [239, 237, 215],
    high = [80, 222, 132];
  const t = Math.max(0, Math.min(1, (value - 0.7) / 0.8));
  const a = t < 0.5 ? low : mid,
    b = t < 0.5 ? mid : high;
  const mix = t < 0.5 ? t * 2 : (t - 0.5) * 2;
  return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * mix)).join(",")})`;
}
// Solid chip palette on the same fixed EPV scale as the numeric legend.
function passFill(value) {
  const t = Math.max(0, Math.min(1, (value - .7) / .8));
  const low = [181, 65, 59], mid = [91, 108, 107], high = [26, 135, 85];
  const a = t < .5 ? low : mid, b = t < .5 ? mid : high;
  const u = t < .5 ? t * 2 : (t - .5) * 2;
  return `rgb(${a.map((v,i) => Math.round(v + (b[i]-v)*u)).join(',')})`;
}
const pct = (x) => (Number.isFinite(x) ? (100 * x).toFixed(1) : "—");
const clock = (x) =>
  `${Math.floor(Math.max(0, x) / 60)}:${String(Math.floor(Math.max(0, x) % 60)).padStart(2, "0")}`;
const name = (id) => game?.players[String(id)]?.name || "Unknown player";
const shortName = (id) => name(id).split(" ").slice(-1)[0];
const teamName = (id) =>
  game.match.home_team.id === id
    ? game.match.home_team.name
    : game.match.away_team.name;
const escape = (s) =>
  String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
async function getJSON(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw Error(`${path}: HTTP ${r.status}`);
  return r.json();
}
function setPlaying(value) {
  playing = value;
  $("playPause").textContent = value ? "Ⅱ Pause" : "▶ Play";
  $("playPause").setAttribute(
    "aria-label",
    value ? "Pause possession" : "Play possession",
  );
  lastTime = 0;
  animationPhase = 0;
}
function selectGame(gid) {
  setPlaying(false);
  requestId++;
  game = manifest.games.find((g) => String(g.match.id) === String(gid));
  $("gameScore").textContent =
    `${game.match.home_score} — ${game.match.away_score} · ${game.match.date_time.slice(0, 10)}`;
  renderList();
  const hash = new URLSearchParams(location.hash.slice(1));
  const preferred = game.plays.find((p) => p.id === hash.get("play"));
  loadPlay(preferred?.id || visiblePlays[0]?.id);
}
function renderList() {
  if (!game) return;
  const filter = $("filter").value,
    query = $("search").value.toLowerCase();
  $("listMetric").textContent = filter === "audit" ? "" : "PTS / PEAK RISK¹";
  if (filter === "audit") {
    const candidates = (game.shotAudits || [])
      .filter((a) =>
        `${teamName(a.offTeamId)} ${name(a.shooter)} q${a.period}`
          .toLowerCase()
          .includes(query),
      )
      .sort((a, b) => b.priority - a.priority);
    visiblePlays = game.plays.filter((p) =>
      candidates.some((a) => a.playId === p.id),
    );
    $("playCount").textContent = `${candidates.length} review candidates`;
    $("playList").innerHTML =
      candidates
        .map(
          (a) =>
            `<button class="play-item audit-item ${play?.id === a.playId && auditFocus === a.shotFrame ? "active" : ""}" data-play="${a.playId}" data-shot="${a.shotFrame}" title="${escape(name(a.shooter))} · ${a.window ? "Estimated pass advantage over actual release PPS" : "Low release PPS; no passing window met all filters"}"><span class="audit-name">${escape(shortName(a.shooter))}</span><span class="audit-clock">Q${a.period} ${a.gameClock == null ? "—" : clock(a.gameClock)}</span><span class="audit-row-detail">${a.window ? "Pass advantage" : "Low shot quality"}</span><span class="audit-row-value">${a.window ? "+" + (Number(a.window.pass.toFixed(2)) - Number(a.total.toFixed(2))).toFixed(2) + " pts" : a.total.toFixed(2) + " PPS"}</span></button>`,
        )
        .join("") || '<p class="microcopy">No candidates meet this screen.</p>';
    $("playList")
      .querySelectorAll("button")
      .forEach(
        (b) => (b.onclick = () => loadPlay(b.dataset.play, +b.dataset.shot)),
      );
    return;
  }
  visiblePlays = game.plays.filter(
    (p) =>
      (filter !== "turnovers" || p.turnover) &&
      (filter !== "scored" || p.points > 0) &&
      `${teamName(p.offTeamId)} q${p.period}`.toLowerCase().includes(query),
  );
  if (filter === "risk") visiblePlays.sort((a, b) => b.peakRisk - a.peakRisk);
  $("playCount").textContent = `${visiblePlays.length} possessions`;
  $("playList").innerHTML =
    visiblePlays
      .map(
        (p) =>
          `<button class="play-item ${play?.id === p.id ? "active" : ""}" data-play="${p.id}"><div><span>${escape(teamName(p.offTeamId))}</span><small>Q${p.period} · ${clock(p.startClock)}${p.turnover ? " · TURNOVER" : ""}</small></div><div class="play-numbers">${p.points}<small>${pct(p.peakRisk)}%</small></div></button>`,
      )
      .join("") || '<p class="microcopy">No matching possessions.</p>';
  $("playList")
    .querySelectorAll("button")
    .forEach((b) => (b.onclick = () => loadPlay(b.dataset.play)));
}
async function loadPlay(pid, reviewFrame = null) {
  auditFocus = reviewFrame;
  cameraPlayer = null;
  cameraFollow = null;
  if (!pid) return;
  setPlaying(false);
  const ticket = ++requestId;
  try {
    const next = await getJSON(`data/plays/${pid}.json`);
    if (ticket !== requestId) return;
    play = next;
    index = Math.max(
      0,
      play.frames.findIndex((f) => f.epv != null && f.offense.some(p => p[0] === f.geometry?.handler && p[1] <= 0)),
    );
    history.replaceState(null, "", `#game=${game.match.id}&play=${pid}`);
    $("scrubber").max = play.frames.length - 1;
    $("playKicker").textContent =
      `QUARTER ${play.period} / ${clock(play.startClock)} / ${play.frames.length} FRAMES`;
    $("playTitle").textContent = teamName(play.offTeamId);
    $("playSubtitle").textContent =
      `vs. ${teamName(play.offTeamId === game.match.home_team.id ? game.match.away_team.id : game.match.home_team.id)} · Outcome: ${play.points} points${play.turnover ? " / turnover" : ""}`;
    $("offenseLabel").textContent = "Offense";
    renderList();
    $("eventStrip").innerHTML =
      play.events
        .filter((e) => e.type !== "pass")
        .map(
          (e) =>
            `<button class="${e.type}" data-frame="${e.frame}">${escape(e.label)}${e.player ? " · " + escape(shortName(e.player)) : ""}</button>`,
        )
        .join("") ||
      '<span class="microcopy">No terminal event in this interval.</span>';
    $("eventStrip")
      .querySelectorAll("button")
      .forEach((b) => (b.onclick = () => seekFrame(+b.dataset.frame)));
    $("coverage").textContent =
      `${play.frames.filter((f) => f.epv != null).length} of ${play.frames.length} replay frames have supported estimates. Playback skips missing/dead-ball tracking; free throws remain in the points target.`;
    $("loading").hidden = true;
    $("content").hidden = false;
    render();
    if (reviewFrame != null) {
      const event = play.events.find(e => e.type === "shot" && e.frame === reviewFrame);
      const window = event ? auditShot(play, event).window : null;
      seekFrame(window?.frame ?? reviewFrame);
      selectedPass = window?.player ?? null;
      render();
    }
  } catch (e) {
    $("loading").hidden = false;
    $("loading").textContent = `Could not load play: ${e.message}`;
  }
}
function seekFrame(frame) {
  if (!play) return;
  let best = 0;
  for (let i = 1; i < play.frames.length; i++)
    if (
      Math.abs(play.frames[i].frame - frame) <
      Math.abs(play.frames[best].frame - frame)
    )
      best = i;
  index = best;
  setPlaying(false);
  render();
}
function canvasSetup(id) {
  const c = $(id),
    rect = c.getBoundingClientRect(),
    dpr = window.devicePixelRatio || 1;
  if (
    c.width !== Math.round(rect.width * dpr) ||
    c.height !== Math.round(rect.height * dpr)
  ) {
    c.width = Math.round(rect.width * dpr);
    c.height = Math.round(rect.height * dpr);
  }
  const ctx = c.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);
  return [ctx, rect.width, rect.height];
}
function recentShot(f) {
  return play?.events
    .filter(
      (e) => e.type === "shot" && e.frame <= f.frame && f.frame - e.frame <= 50,
    )
    .at(-1);
}
function drawCourt(blend = 0) {
  if (!play) return;
  $("defenseContext").hidden = !$("defenseDetail").checked;
  const f = interpolateFrame(play.frames[index], play.frames[index + 1], blend),
    [ctx, w, h] = canvasSetup("court"),
    scale = Math.min(w / 98, h / 56) * courtZoom.flat,
    cx = w * (0.5 + zoomOffsets.flat[0]),
    cy = h * (0.5 + zoomOffsets.flat[1]);
  const sourceFrame = play.frames[index];
  const nextFrame = play.frames[index + 1];
  const visualFrame =
    nextFrame &&
    nextFrame.period === f.period &&
    nextFrame.frame - f.frame <= 10
      ? f.frame + (nextFrame.frame - f.frame) * blend
      : f.frame;
  const flight = passWithRisk(activePass(game.recordedPasses, play.id, visualFrame), play.frames);
  if (driveCacheFrame !== sourceFrame) {
    driveCacheFrame = sourceFrame;
    driveCache = driveSpace(sourceFrame);
  }
  let space = {cells:[],area:0};
  if ($("spaceControl").checked && !realisticView) {
    if (!spaceCache.has(sourceFrame)) spaceCache.set(sourceFrame, spaceControl(sourceFrame, play.frames[index-1], spaceGrids[String(play.gameId)]));
    space = spaceCache.get(sourceFrame);
  }
  $("spaceArea").hidden = !$("spaceControl").checked;
  $("spaceArea").textContent = realisticView ? 'Space overlay: views 1–4 / 6' : space.cells.length ? `${space.area} ft² · value-weighted space` : 'No supported space above threshold';
  const driveCells = [
    ...space.cells.map(c=>({...c,space:true})),
    ...($("driveSpace").checked && !recentShot(f) ? driveCache : []),
  ];
  let movement = null;
  if ($("movementIdeas").checked && !realisticView && !flight && !recentShot(f)) {
    const evaluate = i => {
      const frame = play.frames[i];
      if (!frame) return null;
      if (!movementCache.has(frame)) movementCache.set(frame,new Map());
      const cache=movementCache.get(frame),key=selectedPass??'auto';
      if(!cache.has(key))cache.set(key,movementIdea(frame,play.frames[i-1],spaceGrids[String(play.gameId)],id=>playerProfile(game,id),selectedPass));
      return cache.get(key);
    };
    const candidate=evaluate(index);
    if(candidate){
      const player=f.offense.find(p=>p[0]===candidate.player);
      movement={...candidate,from:[player[1],player[2]]};
    }
  }
  $("movementContext").hidden=!$("movementIdeas").checked;
  $("movementContext").textContent=realisticView?'Movement ideas: views 1–4 / 6':movement?`${shortName(movement.player)} · ${movement.confidence} · ${movement.reason}`:selectedPass?`${shortName(selectedPass)} · no supported improvement; try another teammate`:'Click a teammate to explore movement';
  $("movementContext").title=movement?`${name(movement.player)}: ${Math.hypot(movement.to[0]-movement.from[0],movement.to[1]-movement.from[1]).toFixed(1)} ft, about ${movement.seconds.toFixed(1)}s. ${movement.reason}. ${movement.tradeoff}. Compares staying with moving, including space for teammates under hold, momentum and closeout responses. Experimental heuristic, not validated EPV gain.`:'Select an off-ball teammate. No arrow means no supported positive alternative under this limited search, not that staying is optimal.';

  const guard = closestDefender(f);
  $("guardAngle").textContent =
    guard?.signedAngle != null
      ? `Guard ∠ ${Math.round((Math.abs(guard.signedAngle) * 180) / Math.PI)}°`
      : "Guard ∠ —";
  $("guardAngle").title =
    guard?.signedAngle != null
      ? `Rim–ballhandler–defender angle: 0° toward rim, 90° beside, 180° behind. ${guard.lateral.toFixed(1)} ft lateral offset; ${guard.along.toFixed(1)} ft along the rim direction. Geometry only, not a contest or advantage probability.`
      : "Angle unavailable";
  courtTransform = { scale, cx, cy };
  $("realisticCanvas").hidden = !realisticView;
  if (realisticView) {
    $("overhead").hidden = true;
    document.querySelector(".attack-label").textContent = "5 · REALISTIC · TRACKED PATHS / INFERRED POSES";
    courtHits = [];
    try {
      drawRealistic($("realisticCanvas"), f, {visualFrame, frames:play.frames, events:play.events,
        previous:play.frames[Math.max(0,index-1)], zoom:courtZoom.wide,
        pressure:$("defenseDetail").checked, selectedPass,
        profile:id=>playerProfile(game,id)});
    } catch (error) {
      console.error(error);
      realisticView=false; $("realisticCanvas").hidden=true;
      $("realisticView").setAttribute("aria-pressed","false");
      document.querySelector(".attack-label").textContent="Realistic view requires WebGL graphics support";
    }
    return;
  }
  if ($("view3d").checked) {
    cameraFollow = followPass(cameraFollow, cameraPlayer, flight, visualFrame);
    cameraPlayer = cameraFollow.player;
    $("overhead").hidden = cameraPlayer === null;
    document.querySelector(".attack-label").textContent =
      cameraPlayer === null
        ? tacticalView ? "4 · TACTICAL BOARD · STEAL WINGS / BLOCK TAIL" : "3D · CLICK A PLAYER TO FOLLOW"
        : cameraFollow.ball
          ? "FOLLOWING THE PASS · BALL CAMERA"
          : `${name(cameraPlayer)} · DRAG TO LOOK · DOUBLE-CLICK TO CENTER`;
    courtHits = drawCourt3D(ctx, w, h, f, {
      cameraPlayer, tactical: tacticalView,
      lookYaw, lookPitch, zoom: courtZoom[zoomMode()], zoomOffset: zoomOffsets[zoomMode()],
      motionEvents: play.events,
      replayFrames: play.frames,
      visualFrame,
      followBall: cameraFollow.ball,
      cameraKey: play.id,
      flight,
      profile: (id) => playerProfile(game, id, f.frame),
      driveCells, movement,
      epvKey: epvKey(),
      epvColor, passFill,
      shotEvent: flight ? null : recentShot(f),
      lanes: $("lanes").checked || cameraPlayer !== null,
      pressure: $("pressure").checked,
      defenseDetail: $("defenseDetail").checked,
      defenderNames: $("defenderNames").checked,
      ballRisk: flight ? flight.turnoverProbability : recentShot(f) || f.reason ? null : f.turnover2,
      ballColor: ballRiskColor(flight ? flight.turnoverProbability : recentShot(f) || f.reason ? null : f.turnover2),
      selectedPass,
    });
    return;
  }
  courtHits = [];
  $("overhead").hidden = true;
  if (threatView) document.querySelector(".attack-label").textContent = "7 · THREAT · STL TICK ON THE PASS / BLK ARC ON THE SHOOTER";
  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(scale, scale);
  ctx.fillStyle = "#d9d4c4";
  ctx.fillRect(-49, -28, 98, 56);
  for (let x = -46; x < 46; x += 3) {
    ctx.fillStyle = Math.round((x + 46) / 3) % 2 ? "#d7d2c3" : "#dad6c8";
    ctx.fillRect(x, -24.606, 3, 49.212);
  }
  ctx.strokeStyle = "#979e91";
  ctx.lineWidth = 0.14;
  ctx.strokeRect(-45.932, -24.606, 91.864, 49.212);
  ctx.beginPath();
  ctx.moveTo(0, -24.606);
  ctx.lineTo(0, 24.606);
  ctx.stroke();
  circle(0, 0, 5.905, "#9ca394");
  function circle(x, y, r, stroke) {
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.strokeStyle = stroke;
    ctx.stroke();
  }
  for (const sign of [-1, 1]) {
    ctx.save();
    ctx.scale(sign, 1);
    ctx.fillStyle = "#c6cabc66";
    ctx.fillRect(26.903, -8.038, 19.029, 16.076);
    ctx.strokeStyle = "#939c8d";
    ctx.strokeRect(26.903, -8.038, 19.029, 16.076);
    circle(26.903, 0, 5.905, "#939c8d");
    ctx.beginPath();
    ctx.moveTo(45.932, -21.6535433);
    const cornerX = 40.75 - Math.sqrt(22.146 ** 2 - 21.6535433 ** 2),
      theta = Math.acos((cornerX - 40.75) / 22.146);
    ctx.lineTo(cornerX, -21.6535433);
    ctx.arc(40.75, 0, 22.146, -theta, theta, true);
    ctx.lineTo(45.932, 21.6535433);
    ctx.stroke();
    ctx.lineWidth = 0.24;
    ctx.beginPath();
    ctx.moveTo(42.0, -3);
    ctx.lineTo(42.0, 3);
    ctx.stroke();
    circle(40.75, 0, 0.75, "#b38251");
    ctx.lineWidth = 0.14;
    ctx.restore();
  }
  // Player trails use earlier frames only and break across gaps.
  if (index > 0) {
    for (const p of f.offense) {
      ctx.beginPath();
      let active = false;
      for (let j = Math.max(0, index - 8); j <= index; j++) {
        const old = play.frames[j],
          point = old.offense.find((q) => q[0] === p[0]);
        if (!point) continue;
        if (!active || (j > 0 && old.frame - play.frames[j - 1].frame > 10)) {
          ctx.moveTo(point[1], -point[2]);
          active = true;
        } else ctx.lineTo(point[1], -point[2]);
      }
      ctx.strokeStyle = "#187d6a33";
      ctx.lineWidth = 0.35;
      ctx.stroke();
    }
  }
  for (const cell of driveCells) {
    ctx.beginPath();
    cell.corners.forEach(([x, y], i) => {
      if (i) ctx.lineTo(x, -y);
      else ctx.moveTo(x, -y);
    });
    ctx.closePath();
    ctx.fillStyle = cell.space ? `rgba(65,145,210,${cell.alpha})` : `rgba(255,139,36,${cell.alpha})`;
    ctx.fill();
  }
  drawMovementIdea(ctx, movement, p=>[p[0],-p[1]], 1);
  const shotEvent = flight ? null : recentShot(f);
  const holder = f.offense.find((p) => p[0] === f.geometry?.handler);
  const matchup = closestDefender(f);
  if (matchup) {
    const { holder: a, defender: b, distance } = matchup;
    ctx.save();
    ctx.strokeStyle = "#b6c5c088";
    ctx.lineWidth = 0.1;
    ctx.setLineDash([0.45, 0.3]);
    ctx.beginPath();
    ctx.moveTo(a[1], -a[2]);
    ctx.lineTo(b[1], -b[2]);
    ctx.stroke();
    ctx.setLineDash([]);
    if (matchup.signedAngle != null) {
      const start = matchup.rimBearing,
        delta = matchup.signedAngle;
      ctx.strokeStyle = "#7fa99a66";
      ctx.lineWidth = 0.1;
      ctx.beginPath();
      ctx.moveTo(a[1], -a[2]);
      ctx.lineTo(a[1] + 5 * Math.cos(start), -a[2] - 5 * Math.sin(start));
      ctx.stroke();
      ctx.beginPath();
      for (let i = 0; i <= 24; i++) {
        const t = start + (delta * i) / 24,
          x = a[1] + 2.5 * Math.cos(t),
          y = -a[2] - 2.5 * Math.sin(t);
        if (i) ctx.lineTo(x, y);
        else ctx.moveTo(x, y);
      }
      ctx.stroke();
    }
    const norm = distance || 1;
    const x = (a[1] + b[1]) / 2 + ((b[2] - a[2]) / norm) * 2.5;
    const y = -(a[2] + b[2]) / 2 + ((b[1] - a[1]) / norm) * 2.5;
    const label = distance.toFixed(1) + " ft";
    ctx.font = "400 .7px monospace";
    const width = ctx.measureText(label).width + 0.65;
    ctx.fillStyle = "#11171c66";
    ctx.fillRect(x - width / 2, y - 0.65, width, 1.3);
    ctx.fillStyle = "#aebbb7";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, x, y);
    ctx.restore();
  }

  if (holder && $("lanes").checked) {
    for (const lane of f.geometry.lanes) {
      const target = f.offense.find((p) => p[0] === lane.player);
      if (!target) continue;
      ctx.setLineDash([0.6, 0.6]);
      ctx.lineWidth = 0.18;
      ctx.strokeStyle = lane.clearance < 3 ? "#b74d40aa" : "#187d6a88";
      ctx.beginPath();
      ctx.moveTo(holder[1], -holder[2]);
      ctx.lineTo(target[1], -target[2]);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }
  if (holder && $("pressure").checked) {
    ctx.fillStyle = "#b74d4010";
    ctx.beginPath();
    ctx.arc(holder[1], -holder[2], 6, 0, Math.PI * 2);
    ctx.fill();
    const d = f.defense.find((p) => p[0] === f.geometry.nearestDefender);
    if (d) {
      ctx.strokeStyle = "#b74d4088";
      ctx.lineWidth = 0.22;
      ctx.beginPath();
      ctx.moveTo(holder[1], -holder[2]);
      ctx.lineTo(d[1], -d[2]);
      ctx.stroke();
    }
  }
  const scenario = f.passOptions?.find((o) => o.player === selectedPass);
  if (scenario) {
    ctx.setLineDash([0.35, 0.25]);
    ctx.strokeStyle = "#bc8721";
    ctx.lineWidth = 0.18;
    for (const side of ["offense", "defense"]) {
      for (const p of scenario[side]) {
        const current = f[side].find((q) => q[0] === p[0]);
        if (!current) continue;
        ctx.beginPath();
        ctx.moveTo(current[1], -current[2]);
        ctx.lineTo(p[1], -p[2]);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(p[1], -p[2], 1.8, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
    const destination = scenario.offense.find((p) => p[0] === selectedPass);
    if (holder && destination) {
      ctx.lineWidth = 0.35;
      ctx.beginPath();
      ctx.moveTo(holder[1], -holder[2]);
      ctx.lineTo(destination[1], -destination[2]);
      ctx.stroke();
    }
    ctx.setLineDash([]);
  }
  const bestRoute = !flight && !shotEvent && bestPass(f);
  const bestReceiver =
    bestRoute && f.offense.find((p) => p[0] === bestRoute.player);
  if (holder && bestReceiver) {
    ctx.save();
    ctx.setLineDash([]);
    ctx.strokeStyle = "#36c879";
    ctx.lineWidth = 0.19;
    ctx.beginPath();
    ctx.moveTo(holder[1], -holder[2]);
    ctx.lineTo(bestReceiver[1], -bestReceiver[2]);
    ctx.stroke();
    ctx.restore();
  }
  const defenderLabels = defenderNumbers(f.defense, id => playerProfile(game, id));
  const offenseLabels = defenderNumbers(f.offense, id => playerProfile(game, id));
  const threatOpts = threatView && holder && !flight && !shotEvent ? {
    holder, selectedPass,
    receiver: f.offense.find((p) => p[0] === (defenderForecast(f, "steal", selectedPass)?.receiver)),
    chipRadius: 1.95 * defenderChipScale(offenseLabels.get(holder[0])),
    radiusOf: (id) => 1.95 * defenderChipScale(defenderLabels.get(id)),
    expanded: $("defenseDetail").checked, hover: hoverPlayer,
  } : null;
  if (threatOpts) drawThreatOverlay(ctx, f, { ...threatOpts, layer: "under" });
  for (const [players, color] of [
    [f.defense, colors.def],
    [f.offense, colors.off],
  ])
    for (const p of players) {
      ctx.beginPath();
      const offensive = players === f.offense;
      const chipScale = defenderChipScale((offensive ? offenseLabels : defenderLabels).get(p[0])) * (positionView ? .88 : 1);
      const option = offensive && f.passOptions?.find((o) => o.player === p[0]);
      const passTint = offensive && p[0] !== holder?.[0] && !flight && p[0] !== shotEvent?.player && Number.isFinite(option?.value);
      if (!offensive && !$("defenseDetail").checked && !threatView) {
        // Illustrative arms/hands, not a calibrated interception radius.
        ctx.save();
        ctx.lineCap = "round";
        ctx.strokeStyle = color;
        ctx.lineWidth = 0.38 * chipScale;
        ctx.beginPath();
        ctx.moveTo(p[1] - 2.8 * chipScale, -p[2]);
        ctx.lineTo(p[1] + 2.8 * chipScale, -p[2]);
        ctx.stroke();
        ctx.fillStyle = "#b99779";
        for (const side of [-1, 1]) {
          ctx.beginPath();
          ctx.arc(p[1] + side * 2.85 * chipScale, -p[2], 0.28 * chipScale, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();
      }
      ctx.beginPath();
      ctx.arc(p[1], -p[2], (passTint ? 1.95 : 1.75) * chipScale, 0, Math.PI * 2);
      ctx.fillStyle = passTint ? passFill(option.value) : positionView && offensive ? colors.off :
        offensive && (flight?.receiver === p[0] || p[0] === shotEvent?.player)
          ? "#16834b"
          : color;
      ctx.fill();
      const higherOpenPass =
        option &&
        Number.isFinite(f[epvKey()]) &&
        option.value > f[epvKey()] &&
        option.route?.reachableDefenders === 0;
      const isShooter = offensive && p[0] === shotEvent?.player;
      ctx.strokeStyle =
        offensive && flight?.receiver === p[0]
          ? "#36db7a"
          : isShooter
            ? "#36db7a"
            : p[0] === holder?.[0]
              ? "#fff6dc"
              : higherOpenPass
                ? "#36db7a"
                : option?.route?.immediateReach
                  ? "#e6ac39"
                  : color;
      ctx.lineWidth =
        p[0] === holder?.[0] || higherOpenPass || option?.route?.immediateReach
          ? 0.33
          : 0.13;
      ctx.setLineDash(p[3] ? [] : [0.3, 0.25]);
      ctx.beginPath();
      ctx.arc(p[1], -p[2], 1.95 * chipScale, 0, Math.PI * 2);
      if (!passTint) ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#fff";
      ctx.font = "500 1.2px monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      if (offensive && flight?.receiver === p[0]) {
        ctx.fillStyle = '#f7faf8';
        ctx.font = '700 1.05px "IBM Plex Mono", monospace';
        ctx.fillText(Number.isFinite(flight.turnoverProbability) ? pct(flight.turnoverProbability) + '%' : '', p[1], -p[2]-.35);
        ctx.font = '500 .65px "IBM Plex Mono", monospace';
        ctx.fillText(Number.isFinite(flight.turnoverProbability) ? 'TOV' : '', p[1], -p[2]+.65);
      } else if (offensive && positionView) {
        ctx.fillStyle = passTint ? '#f7faf8' : '#e2e6e8';
        ctx.font = `600 ${2.05 * chipScale}px "DM Sans", sans-serif`;
        ctx.fillText(offenseLabels.get(p[0]), p[1], -p[2]);
        const isHolder = p[0] === holder?.[0];
        const value = isShooter ? shotPps(shotEvent) : isHolder ? f[epvKey()] : option?.value;
        const text = Number.isFinite(value) ? value.toFixed(2) : '';
        const turnover = isShooter || flight ? null : isHolder ? f.turnover2 : option?.turnoverProbability;
        const turnoverText = isShooter ? 'SHOT' : Number.isFinite(turnover) ? `${pct(turnover)}% TOV${isHolder ? ' · 2s' : ''}` : '';
        curvedValue(ctx, p[1], -p[2], 1.95 * chipScale, text,
          Number.isFinite(value) ? epvColor(value) : '#c4cbcf', turnoverText,
          { x: f.ball[0], y: -f.ball[1], radius: 1.0 });
      } else if (offensive && flight) {
        const text = flightLabel(flight, p[0]);
        ctx.font = "600 1.05px monospace";
        ctx.fillStyle = "#c1ecee";
        ctx.fillText(text, p[1], -p[2]);
      } else if (isShooter) {
        ctx.fillStyle = "#effff3";
        ctx.font = "600 1.05px monospace";
        const pps = shotPps(shotEvent);
        ctx.fillText(
          f.frame - shotEvent.frame < 15
            ? "SHOT"
            : pps != null
              ? pps.toFixed(2)
              : "—",
          p[1],
          -p[2] - 0.35,
        );
        ctx.font = "500 0.75px monospace";
        ctx.fillText(
          f.frame - shotEvent.frame < 15 ? "" : "PPS",
          p[1],
          -p[2] + 0.65,
        );
      } else if (offensive) {
        const isHolder = p[0] === holder?.[0];
        ctx.fillStyle = passTint ? "#f7faf8" : epvColor(isHolder ? f[epvKey()] : option?.value);
        ctx.font = "600 1.05px monospace";
        ctx.fillText(
          isHolder
            ? Number.isFinite(f[epvKey()])
              ? f[epvKey()].toFixed(2)
              : "—"
            : option
              ? option.value.toFixed(2)
              : "—",
          p[1],
          -p[2] - (option || isHolder ? 0.45 : 0),
        );
        if (option || isHolder) {
          ctx.fillStyle = passTint ? "#e1e9e5" : "#d3d8dc";
          ctx.font = "500 0.8px monospace";
          ctx.fillText(
            isHolder ? "EPV" : `${pct(option.turnoverProbability)}%`,
            p[1],
            -p[2] + 0.65,
          );
        }
      }
      if (!offensive) {
        drawDefenderLabel(ctx, p[1], -p[2], 1.95 * chipScale, playerProfile(game, p[0]), f, p[0], defenderLabels.get(p[0]), true, { showNames: $("defenderNames").checked, enabled: $("defenseDetail").checked && !threatView, receiver: selectedPass, unit: 1.95, reference: defenderThreatReference(play.frames), wingAngle: rimWingAngle((x, y) => [x, -y], p[1], p[2]) });
        if (!threatView) drawDefenderDistance(ctx, p[1], -p[2] + 1.95 * chipScale + .65, 1.2, p, f);
      }
      if (offensive && !positionView) profileTab(
        ctx,
        p[1],
        -p[2] - 1.95 * chipScale - .4,
        1,
        playerProfile(game, p[0], f.frame),
        offensive,
      );
    }
  if (threatOpts) drawThreatOverlay(ctx, f, { ...threatOpts, layer: "over" });
  if (holder && !flight && !shotEvent && !f.reason) {
    const best = bestPass(f);
    const x = Math.max(-44, Math.min(44, holder[1]));
    const y = -holder[2] + (holder[2] > 19 ? 3.5 : positionView ? -4.3 : -4.5);
    ctx.strokeStyle = "#83948c66";
    ctx.lineWidth = 0.09;
    ctx.beginPath();
    ctx.moveTo(holder[1], -holder[2]);
    ctx.lineTo(x, y);
    ctx.stroke();
    actionCard(
      ctx,
      x,
      y,
      1,
      f.shot?.shotPlusSecondChance,
      best?.value,
      epvColor, passFill,
    );
  }
  drawBallTrail(ctx, ballTrail(play.frames, f, visualFrame), b=>[b[0],-b[1]], 1.0);
  ctx.fillStyle = "#9d753733";
  ctx.beginPath();
  ctx.ellipse(f.ball[0] + 0.3, -f.ball[1] + 0.4, 1.0, 0.5, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = ballRiskColor(flight ? flight.turnoverProbability : shotEvent || f.reason ? null : f.turnover2);
  ctx.strokeStyle = "#704915";
  ctx.lineWidth = 0.12;
  ctx.beginPath();
  ctx.arc(f.ball[0], -f.ball[1], 1.0, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  const ballRisk = flight ? flight.turnoverProbability : shotEvent || f.reason ? null : f.turnover2;
  if (Number.isFinite(ballRisk)) {
    ctx.fillStyle = '#191919';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = '700 .72px "IBM Plex Mono", monospace';
    ctx.fillText(`${Math.round(ballRisk * 100)}%`, f.ball[0], -f.ball[1], 1.8);
  }
  ctx.restore();
}
function chart(id, key, color, max) {
  const [ctx, w, h] = canvasSetup(id),
    frames = play.frames,
    first = frames[0].frame,
    last = frames.at(-1).frame;
  const x = (v) => 8 + ((w - 45) * (v - first)) / Math.max(1, last - first),
    y = (v) => h - 15 - ((h - 27) * v) / max;
  ctx.font = "9px monospace";
  ctx.textAlign = "right";
  for (const v of [0, max / 2, max]) {
    ctx.strokeStyle = "#2b373e";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(8, y(v));
    ctx.lineTo(w - 35, y(v));
    ctx.stroke();
    ctx.fillStyle = "#8fa0aa";
    ctx.fillText(
      key.startsWith("epv") ? v.toFixed(1) : Math.round(v * 100) + "%",
      w - 1,
      y(v) + 3,
    );
  }
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.7;
  ctx.beginPath();
  let active = false;
  frames.forEach((f, i) => {
    if (f[key] == null) {
      active = false;
      return;
    }
    if (!active || (i > 0 && f.frame - frames[i - 1].frame > 10)) {
      ctx.moveTo(x(f.frame), y(f[key]));
      active = true;
    } else ctx.lineTo(x(f.frame), y(f[key]));
  });
  ctx.stroke();
  for (const e of play.events.filter((e) =>
    ["shot", "turnover"].includes(e.type),
  )) {
    ctx.fillStyle = e.type === "shot" ? "#5ed5be66" : "#f18b7866";
    ctx.fillRect(x(e.frame) - 1, h - 10, 2, 5);
  }
  const actual = frames[index],
    next = frames[index + 1],
    f = {
      ...actual,
      frame:
        actual.frame +
        (next && next.frame - actual.frame <= 10
          ? (next.frame - actual.frame) * animationPhase
          : 0),
    };
  ctx.strokeStyle = "#edf2f377";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x(f.frame), 4);
  ctx.lineTo(x(f.frame), h - 11);
  ctx.stroke();
  if (f[key] != null) {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x(f.frame), y(f[key]), 3, 0, Math.PI * 2);
    ctx.fill();
  }
}
function epvKey() {
  return $("epvMode").value;
}
function drawEpvChart() {
  const key = epvKey();
  chart(
    "epvChart",
    key,
    colors.teal,
    Math.max(2, Math.ceil(Math.max(...play.frames.map((f) => f[key] || 0)))),
  );
}
function renderShot(f) {
  const review = shotReview(play, auditFocus ?? f.frame);
  const panel = $("shotReview");
  panel.hidden = !review;
  document.querySelector(".shot-panel").hidden = !!review;
  document.querySelector(".second-chance-panel").hidden = !!review;
  const reviewKey = review ? `${play.id}:${review.event.frame}:${auditFocus}` : "";
  if (!review) panel.dataset.reviewKey = "";
  if (review && panel.dataset.reviewKey !== reviewKey) {
    panel.dataset.reviewKey = reviewKey;
    const points = (v) => (Number.isFinite(v) ? v.toFixed(2) : "—");
    const audit = auditShot(play, review.event),
      w = audit.window;
    const headline = w
      ? `Potential missed pass → ${escape(shortName(w.player))}`
      : audit.kind === "foul" ? "Shooting foul · ungraded"
      : audit.kind === "low-shot"
        ? "Low-value shot · review"
        : audit.kind === "unavailable"
          ? "Insufficient shot evidence"
          : "No clear pass advantage flagged";
    panel.innerHTML = `<div class="audit-eyebrow">DECISION REVIEW · CANDIDATE</div>
      <h3 class="audit-headline ${w || audit.kind === "low-shot" ? "flagged" : ""}">${headline}</h3>
      <div class="audit-meta">${escape(name(review.event.player))} · ${review.clock == null ? "—" : review.clock.toFixed(1) + "s"} on clock · Q${play.period} ${review.event.gameClock == null ? "" : clock(review.event.gameClock)}</div>
      <div class="audit-release"><small>ACTUAL SHOT · AT RELEASE</small><div>${review.event.shotForecast?.quality?.source === "skillcorner" ? "SkillCorner SQ · score ÷ 100 used as P(make)" : "Pooled model · SkillCorner score unavailable"}</div><b>${points(review.total)} <span>${review.event.fouled ? "FT VALUE PENDING" : "PPS"}</span></b><div>${review.event.fouled ? "Fouled attempt · " + points(review.first) + " expected field-goal points only" : `${points(review.first)} first chance + ${points(review.second)} second chance${Number.isFinite(review.total) && Number.isFinite(review.first) && Number.isFinite(review.second) && Math.abs(Number(review.first.toFixed(2)) + Number(review.second.toFixed(2)) - Number(review.total.toFixed(2))) > 0.005 ? " ≈ " : " = "}${points(review.total)}<br>${pct(review.orb)}% expected ORB on a live miss`}</div></div>
      ${w ? `<div class="audit-window-label">EARLIER OPTION · ${((review.event.frame - w.frame) / 25).toFixed(2)}s BEFORE RELEASE</div><div class="audit-compare"><div><small>ACTUAL RELEASE PPS</small><b>${points(review.total)}</b></div><div><small>PASS AT WINDOW</small><b>${points(w.pass)}</b></div></div><p class="audit-evidence"><strong>+${(Number(w.pass.toFixed(2)) - Number(review.total.toFixed(2))).toFixed(2)} pass edge over actual shot</strong> · ${((w.end - w.start) / 25).toFixed(2)}s sustained window<br>≤${pct(w.maxTo)}% pass TO · route clear under model timing.<br>Earlier shoot-now estimate: ${points(w.shot)} PPS (context only).</p><button id="reviewWindow" class="primary">↶ Inspect this moment</button>` : `<p class="audit-evidence">${audit.kind === "foul" ? "Free-throw value is not modeled. A fouled miss is not a normal live rebound; this shot is excluded from decision flags." : audit.kind === "low-shot" ? "Below 0.95 PPS with more than 5s left. No passing window met all edge filters (value, duration, turnover risk and route clearance)." : "No sustained open pass exceeded the actual release PPS by 0.15. This does not certify the decision."}</p>`}
      <div class="audit-actions"><button id="reviewRelease">Show release</button>${auditFocus != null ? '<button id="reviewLive">Return to live</button>' : ""}</div>
      <details class="audit-details"><summary>Shot breakdown & pass evidence</summary>
        <div class="review-row"><span>First chance</span><strong>${points(review.first)}</strong></div>
        <div class="review-row"><span>Second chance / shot</span><strong>+${points(review.second)}</strong><small>${pct(review.orb)}% expected ORB · ${points(review.perMiss)} pts/live miss</small></div>
        <div class="review-row"><span>Total release PPS</span><strong>${points(review.total)}</strong></div>
        <div class="review-row"><span>Pass just before release</span><strong>${review.pass ? escape(shortName(review.pass.player)) + " · " + points(review.pass.value) : "—"}</strong><small>${review.pass ? pct(review.pass.turnoverProbability) + "% TO · " + review.passAge.toFixed(2) + "s before shot" + (review.pass.route?.reachableDefenders ? " · route within reach" : "") : "No supported estimate within 0.4s"}</small></div>
      </details>
      <details class="audit-details"><summary>Screening rules & limits</summary><p>Pass edge ≥0.15 points for ≥0.4s to the same receiver, ending ≥0.3s before release, within the preceding 2s. Compare the earlier pass estimate against the PPS of the shot actually created at release. This is a retrospective review, not a live recommendation. Pass TO ≤12%, no defender marked able to reach the route. Low-shot screen: &lt;0.95 PPS and &gt;5s left. These are review thresholds, not validated coaching grades. The 0.3s buffer is not measured shooting commitment. Release PPS uses SkillCorner SQ / 100 as make probability, with pooled fallback. Earlier pass values still use our model. Free throws excluded; make/miss results do not affect flags.</p></details>`;
    const showRelease = () => {
      auditFocus = review.event.frame;
      seekFrame(review.event.frame);
    };
    $("reviewRelease").onclick = showRelease;
    if ($("reviewLive"))
      $("reviewLive").onclick = () => {
        auditFocus = null;
        render();
      };
    if (w)
      $("reviewWindow").onclick = () => {
        auditFocus = review.event.frame;
        seekFrame(w.frame);
        selectedPass = w.player;
        render();
      };
  }
  const event = recentShot(f),
    forecast = event
      ? event.shotForecast
      : f.shot?.secondChancePerMiss != null
        ? f.shot
        : null;
  const shot = event
    ? forecast?.quality
      ? { ...forecast.quality, shooter: event.player }
      : null
    : f.shot;
  $("shotHeading").textContent = event
    ? "SHOT QUALITY · AT RELEASE"
    : "CURRENT SHOOTING SCENARIO";
  $("secondChance").textContent = forecast
    ? forecast.secondChancePerMiss.toFixed(2) + " pts / live miss"
    : "—";
  $("reboundProbability").textContent = forecast
    ? pct(forecast.offensiveReboundProbability) + "% offensive rebound"
    : "No supported rebound estimate";
  $("secondChanceShot").textContent =
    forecast?.secondChancePerShot != null
      ? forecast.secondChancePerShot.toFixed(2) + " pts / shot"
      : "—";
  $("shotPlayer").textContent = shot
    ? name(shot.shooter)
    : f.unsupportedShot ? name(f.unsupportedShot.shooter) : "No supported estimate";
  $("shotProbability").textContent = shot
    ? pct(shot.makeProbability) + "%"
    : "—";
  $("shotValue").textContent = shot
    ? shot.fieldGoalValue.toFixed(2) + " pts"
    : "—";
  $("shotEvidence").textContent =
    shot?.trainingAttempts != null ? shot.trainingAttempts + " shots" : "—";
  $("shotGeneric").textContent = shot
    ? event
      ? shot.source === "skillcorner" ? "SkillCorner SQ / 100" : "Pooled model fallback"
      : shot.source === "skillcorner-surrogate" ? "Estimated SkillCorner SQ" : "Pooled estimate: " + pct(shot.pooledProbability) + "%"
    : "Pooled estimate: —";
  $("shotContext").textContent = event
    ? `Observed shot · estimate fixed at release${shot?.vendorQuality != null ? " · SkillCorner SQ " + shot.vendorQuality.toFixed(1) + "/100 (score)" : ""}`
    : shot
      ? `${shot.pointsIfMade}PT scenario${shot.nearLine ? " · near the 3PT line" : ""} · current spacing · no release projection${shot.source === "skillcorner-surrogate" && shot.pointsIfMade === 3 ? " · openness capped at 9 ft" : ""}`
      : f.shotUnavailableReason || f.reason || "Outside the 32 ft model range";
  if (shot?.source === "skillcorner-surrogate") {
    $("shotEvidence").textContent = surrogateReport ? (surrogateReport.summary.mae*100).toFixed(1) + " pp MAE" : "—";
  }
  $("shotEvidenceNote").textContent = shot?.source === "skillcorner-surrogate"
    ? `Held-out release error; live uncertainty may be larger${shot.extrapolated ? " · outside training range" : ""}`
    :
    shot?.trainingAttempts === 0
      ? "No player attempts; quality remains pooled"
      : "Player count for context only; quality is pooled";
}
function renderSearch(f) {
  const forecast = recentShot(f) ? null : f.search;
  const box = $("searchForecast");
  if (!forecast || f.reason) {
    box.textContent =
      "No supported dribble-start forecast here (requires controlled possession, within 32 ft, and at least 2.2 seconds on the shot clock).";
    return;
  }
  const labels = {
    pullup: "Pull-up / stepback family",
    rim: "Rim / floater / hook",
    other_shot: "Other shot",
    pass: "Pass attempted",
    turnover: "Turnover before pass/shot",
    foul: "Foul before pass/shot",
    retain: "Still on same touch",
    other: "Other touch ending",
  };
  const release = forecast.release;
  box.innerHTML = `<p class="pass-note"><b>${escape(name(f.geometry.handler))}</b> · ${forecast.playerWeight > 0 ? `Player adjustment: ${forecast.playerTouches} touches across ${forecast.playerGames} other games; ${Math.round(forecast.playerWeight * 100)}% residual weight.` : `Pooled · ${forecast.playerTouches} touches / ${forecast.playerGames} other games (needs 20 / 2).`}</p>
    <div class="search-branches">${Object.entries(labels)
      .map(
        ([key, label]) =>
          `<div><span>${label}</span><b>${pct(forecast.events[key])}%</b><progress max="1" value="${forecast.events[key]}" aria-label="${label}"></progress></div>`,
      )
      .join("")}</div>
    <p class="pass-note">If shot ≤2s: <b>${release.distance.toFixed(1)} ft</b> rim · <b>${release.separation.toFixed(1)} ft</b> defender · <b>${release.seconds.toFixed(2)}s</b>. Conditional means.</p>
    <details><summary>Experimental possession-points reference</summary><p class="pass-note">${forecast.points.toFixed(2)} remaining points following observed dribble starts. Pooled reference ${forecast.pooledPoints.toFixed(2)}; pooled 80% empirical outcome-error range ${forecast.pooledOutcomeRange.join("–")} points. This is not a confidence interval for the mean or a causal SEARCH action value. It has not beaten the constant baseline and is not used to rank SHOT or PASS.</p></details>`;
  const validation = manifest.metrics.search;
  if (validation) {
    const m = validation.summary;
    $("searchValidation").textContent =
      `Held-out games · ${validation.audit.exclusions.accepted} touch anchors. Next-event log loss ${m.context.logLoss.toFixed(3)} vs ${m.constant.logLoss.toFixed(3)} constant (lower is better). Release-distance error ${m.release.releaseDistanceMae.toFixed(1)} ft vs ${m.release.releaseDistanceBaselineMae.toFixed(1)} ft. Points RMSE ${m.context.pointsRmse.toFixed(3)} vs ${m.constant.pointsRmse.toFixed(3)}. No held-out touch qualified for a player adjustment.`;
  }
}
function renderSteals(f) {
  const forecast = defenderForecast(f, 'steal', selectedPass);
  const block = defenderForecast(f, 'block');
  $("defenseContext").textContent = `STL: pass ${forecast?.receiver ? '→ ' + name(forecast.receiver) : 'unavailable'} · BLK: shoot now · experimental`;
  $("stealTotal").textContent = `${forecast ? pct(forecast.anyEventProbability) + '% pass STL' : '— STL'} · ${block ? pct(block.anyEventProbability) + '% shot BLK' : '— BLK'}`;
  $("stealNone").textContent = forecast ? `${pct(forecast.noEventProbability)}% no credited interception on this pass` : '';
  $("stealPlayers").innerHTML = f.defense.map(d => {
    const steal = defenderProbability(f, 'steal', d[0], selectedPass), block = defenderProbability(f, 'block', d[0]);
    return `<div class="steal-player"><span>${escape(name(d[0]))}</span><span>STL ${steal == null ? '—' : pct(steal)+'%'} · BLK ${block == null ? '—' : pct(block)+'%'}</span></div>`;
  }).join('');
}
function renderPassOptions(f) {
  const holder = f.geometry?.handler;
  const options = f.passOptions || [];
  $("passOptions").innerHTML = f.offense
    .filter((p) => p[0] !== holder)
    .map((p) => {
      const o = options.find((o) => o.player === p[0]);
      return `<button class="pass-option ${selectedPass === p[0] ? "selected" : ""}" data-player="${p[0]}" aria-pressed="${selectedPass === p[0]}" ${o ? "" : "disabled"}><span>${escape(shortName(p[0]))}</span><b style="color:${epvColor(o?.value)}">${o ? o.value.toFixed(2) : "—"} <small>EPV</small></b><span>${o ? pct(o.turnoverProbability) + "% pass TO" : "Unavailable"}</span>${o?.route?.reachableDefenders ? `<span class="route-warning">${o.route.immediateReach ? "Direct route within reach" : "Defender can reach route"}</span>` : ""}</button>`;
    })
    .join("");
  const selected = options.find((o) => o.player === selectedPass);
  $("passDetail").textContent = selected
    ? `${name(selected.player)} · catch in ${selected.arrivalSeconds.toFixed(2)}s${selected.timingModel === "learned" ? ` (${selected.flightSeconds.toFixed(2)}s learned flight + 0.12s release)` : ""} · ${selected.completedEpv.toFixed(2)} EPV if completed × ${(1 - selected.turnoverProbability).toFixed(3)} survival = ${selected.value.toFixed(2)} expected points. Catch positions use constant velocity. ${selected.route?.reachableDefenders ? `${selected.route.reachableDefenders} defender(s) can reach the direct route under the timing assumptions; maximum time advantage ${selected.route.advantageSeconds.toFixed(2)}s. The fitted TO% is not a calibrated probability for forcing that straight pass.` : "No direct-route reach flagged under the timing assumptions; this does not guarantee a safe pass."}`
    : "Select a pass to inspect its projected catch. Turnovers contribute zero remaining offensive points.";
}
$("passOptions").onclick = (e) => {
  const b = e.target.closest("button[data-player]");
  if (!b || b.disabled) return;
  selectedPass = +b.dataset.player;
  playing = false;
  $("playPause").textContent = "▶ Play";
  render();
};
$("clearPass").onclick = () => {
  selectedPass = null;
  render();
};

function render() {
  if (!play || $("content").hidden) return;
  const f = play.frames[index];
  $("epvValue").textContent =
    f[epvKey()] == null ? "—" : f[epvKey()].toFixed(2);
  renderShot(f);
  renderSearch(f);
  renderPassOptions(f);
  renderSteals(f);
  $("riskValue").textContent = pct(f.turnover2);
  $("restValue").textContent = pct(f.turnoverRest);
  $("gameClock").textContent = clock(f.gameClock);
  $("shotClock").textContent =
    f.shotClock == null ? "—" : f.shotClock.toFixed(1);
  $("scrubber").value = index;
  $("elapsed").textContent =
    Math.max(0, play.frames[0].gameClock - f.gameClock).toFixed(1) + "s";
  $("frameStatus").textContent = f.reason || "PREDICTED FROM PRIOR STATE";
  drawCourt();
  drawEpvChart();
  chart(
    "riskChart",
    "turnover2",
    colors.coral,
    Math.max(
      0.1,
      Math.ceil(Math.max(...play.frames.map((f) => f.turnover2 || 0)) * 10) /
        10,
    ),
  );
  const holder = f.offense.find((p) => p[0] === f.geometry?.handler),
    def = f.defense.find((p) => p[0] === f.geometry?.nearestDefender);
  const dist =
    holder && def ? Math.hypot(holder[1] - def[1], holder[2] - def[2]) : null;
  const detected = f.offense.concat(f.defense).filter((p) => p[3]).length;
  const rows = [
    ["Ballhandler", holder ? name(holder[0]) : "Uncertain / in flight"],
    [
      "Nearest defender",
      dist == null ? "—" : `${dist.toFixed(1)} ft · ${shortName(def[0])}`,
    ],
    [
      "Crowded passing lanes",
      f.geometry
        ? `${f.geometry.lanes.filter((l) => l.clearance < 3).length} of 4 within 3 ft`
        : "—",
    ],
    ["Directly detected players", `${detected} / 10`],
  ];
  $("geometry").innerHTML = rows
    .map(
      ([a, b]) =>
        `<div class="geometry-row"><span>${escape(a)}</span><b>${escape(b)}</b></div>`,
    )
    .join("");
  $("lineup").innerHTML = f.offense
    .map((p, i) => [p, f.defense[i]])
    .flat()
    .map(
      (p, i) =>
        `<div class="player-name ${i % 2 ? "def" : ""}"><span class="jersey" style="${p[3] ? "" : "border-style:dashed"}">${escape(p[5])}</span>${escape(name(p[0]))}</div>`,
    )
    .join("");
  $("eventStrip")
    .querySelectorAll("button")
    .forEach((b) =>
      b.classList.toggle("current", Math.abs(+b.dataset.frame - f.frame) < 15),
    );
}
function showModel() {
  const m = manifest.metrics;
  let html = `<p>${m.games} games · ${m.possessions.toLocaleString()} possessions with supported states · ${m.trainingStates.toLocaleString()} sampled training states.</p><p>Every replay uses a model trained on the other nine games. The final all-game model is saved separately. These are expected outcomes under observed play, not estimates of the best possible action.</p><h3>Does player geometry improve prediction?</h3><p>Lower error is better. Same fixed model settings, compared with a constant and a clock / ball-location baseline. Games contribute equally; possessions have equal weight within each game.</p><div class="table-wrap"><table><thead><tr><th>Target / error</th><th>Constant</th><th>Clock + location</th><th>+ Player geometry</th><th>+ Pooled shot quality</th></tr></thead><tbody>`;
  for (const target of ["points", "turnover2", "turnover_rest"]) {
    const metric = target === "points" ? "rmse" : "brier";
    html += `<tr><td>${target === "points" ? "EPV · RMSE" : target === "turnover2" ? "TO next 2 sec · Brier" : "TO remaining · Brier"}</td>${["constant", "clock_location", "geometry", "shooting"].map((k) => `<td>${m.summary[target][k]?.[metric]?.toFixed(4) ?? "—"}</td>`).join("")}</tr>`;
  }
  html += "</tbody></table></div>";
  html += `<p><strong>Current result:</strong> geometry modestly improves short-term turnover prediction. ${m.summary.points.shooting.rmse < m.summary.points.constant.rmse ? "EPV with shooting inputs has lower held-out RMSE than the constant baseline." : "EPV with shooting inputs does not beat the constant baseline overall."} These ten games do not establish statistical significance; remaining-possession turnover risk is also experimental.</p><h3>What the numbers mean</h3><ul><li>EPV includes the offense’s remaining made field goals and free throws, including continuation after an offensive rebound.</li><li>Turnover risk includes recorded turnovers and offensive fouls. “Next 2 seconds” uses the running game clock and stops at the possession boundary.</li><li>Estimates appear only in supported, controlled-ball states. The chart leaves gaps during shots, passes, uncertain control, or low-quality chances.</li><li>Player positions, trailing movement, defender proximity, spacing, and passing-lane clearance feed the geometry model. These are associations, not causal explanations or calibrated probabilities for individual passing lanes.</li><li>Ten games limit certainty. Shot quality is pooled across players; shooter identity does not adjust make probability. No season aggregates, future outcomes from the evaluated game, or vendor shot-quality scores are inputs.</li></ul><h3>Turnover calibration · next 2 seconds</h3><div class="table-wrap"><table><tr><th>Prediction band</th><th>Mean prediction</th><th>Observed frequency</th><th>States</th></tr>${m.calibration.turnover2.map((b) => `<tr><td>${Math.round(b.lo * 100)}–${Math.round(b.hi * 100)}%</td><td>${pct(b.predicted)}%</td><td>${pct(b.observed)}%</td><td>${b.n}</td></tr>`).join("")}</table></div><p>The frequency comparison uses held-out predictions. Sparse bands can be unstable. The two turnover horizons are fitted separately, then projected so short-term risk cannot exceed remaining-possession risk. The reported errors include this correction.</p><h3>Tracking quality</h3><p>Dashed rings mark extrapolated players. Pressure circles show a 6 ft neighborhood; dashed potential passes show geometric clearance only. Coordinates are rotated toward the offensive basket. Raw tracking is 25 Hz; replay is 5 Hz and training is 2.5 Hz. Video footage is not included in this release.</p>`;
  if (m.shooting) {
    html += `<h3>Shooting model · ${m.shooting.attempts} observed attempts</h3><p>The pooled make model uses shot distance, defender distance, lateral location, and clock. No player adjustments are applied. The scenario applies release-context predictions to the current holder; it does not model gather time, body pose, or whether the shot is actually executable.</p><div class="table-wrap"><table><tr><th>Held-out shot model</th><th>Brier</th><th>Log loss</th></tr>${Object.entries(
      m.shooting.summary,
    )
      .map(
        ([name, v]) =>
          `<tr><td>${name}</td><td>${v.brier.toFixed(4)}</td><td>${v.logLoss.toFixed(4)}</td></tr>`,
      )
      .join(
        "",
      )}</table></div><p>All recorded shot events are eligible, including fouled misses. Expected field-goal points exclude free throws and offensive rebounds, so subtracting them from full EPV is not a shoot-versus-continue decision margin.</p><p>Nested game exclusions keep EPV training rows from seeing their own shooting outcomes through the skill estimates. Shot accuracy is evaluated on actual attempts; declined shots remain counterfactual. Teammate skill and individual defender ability are not modeled yet.</p>`;
  }
  if (m.passing) {
    const p = m.passing;
    if (p.flightTiming) {
      const t = p.flightTiming;
      html += `<h3>Learned pass flight time</h3><p>${t.passes} completed passes; each replay excludes its entire game. Mean held-out absolute timing error: ${t.summary.fixed40.mae.toFixed(3)}s with fixed speed → ${t.summary.learned.mae.toFixed(3)}s learned. RMSE: ${t.summary.fixed40.rmse.toFixed(3)}s → ${t.summary.learned.rmse.toFixed(3)}s.</p><p>${escape(t.target)} ${escape(t.limitations)} The interception-route diagnostic still uses its separate fixed-speed assumptions.</p>`;
    }
    if (p.perGame.every((r) => r.geometryBrier != null)) {
      const mean = (key) =>
        (
          p.perGame.reduce((sum, r) => sum + r[key], 0) / p.perGame.length
        ).toFixed(4);
      html += `<h3>Timing feature comparison</h3><p>Compared with the previous geometry model, mean held-out log loss changes from ${mean("geometryLogLoss")} to ${mean("logLoss")} (better); Brier changes from ${mean("geometryBrier")} to ${mean("brier")} (slightly worse). This is mixed exploratory evidence, not established calibration improvement.</p>`;
    }
    html += `<h3>Experimental pass scenarios</h3><p>${p.trainingPasses} selected passes, including ${p.trainingTurnovers} inferred turnovers. Early-flight reconstruction matches ${(p.reconstructionAccuracy * 100).toFixed(1)}% of accepted completed-pass receivers. All prediction inputs precede release; each replay excludes its game from pass, shot, and EPV fitting.</p><p>${escape(p.limitations)}</p><p>${escape(p.timing || "")}</p><table><tr><th>Held-out game</th><th>Pass Brier</th><th>Constant Brier</th></tr>${p.perGame.map((r) => `<tr><td>${r.gameId}</td><td>${r.brier.toFixed(4)}</td><td>${r.baselineBrier.toFixed(4)}</td></tr>`).join("")}</table>`;
  }
  if (m.catchValidation) {
    const c = m.catchValidation;
    html += `<h3>Catch forecast consistency</h3><p>${c.passes} completed passes. Mean absolute gap between pre-pass conditional catch EPV and observed post-catch EPV: ${c.mae.toFixed(3)} points; bias ${c.bias.toFixed(3)}. Mean receiver position error ${c.receiverErrorFt.toFixed(2)} ft. ${escape(c.meaning)}</p><p>Observed and projected EPV share holder-centered features. Ball flight speed, ball height, control offset and tracking-quality measurements are excluded from EPV; these remain available to turnover models. Projected defender closing speed uses the same short-history calculation as observed states.</p>`;
  }
  if (m.secondChance) {
    const r = m.secondChance;
    html += `<h3>Second-chance value</h3><p>${r.misses} resolved live misses, including ${r.offensiveRebounds} offensive rebounds. ${escape(r.definition)}</p><p>Held-out rebound Brier: ${r.summary.brier.toFixed(4)} versus ${r.summary.baselineBrier.toFixed(4)} constant. Second-chance point RMSE: ${r.summary.pointsRmse.toFixed(3)} versus ${r.summary.baselinePointsRmse.toFixed(3)} constant. These are experimental estimates.</p>`;
  }
  $("modelDetails").innerHTML = html;
  $("methodDialog").showModal();
}
$("gameSelect").onchange = (e) => selectGame(e.target.value);
$("filter").onchange = renderList;
$("search").oninput = renderList;
$("playPause").onclick = () => {
  if (index === play.frames.length - 1) index = 0;
  setPlaying(!playing);
  render();
};
$("scrubber").oninput = (e) => {
  index = +e.target.value;
  setPlaying(false);
  render();
};
for (const id of ["lanes", "pressure", "driveSpace", "defenseDetail", "defenderNames", "spaceControl", "movementIdeas"])
  $(id).onchange = () => drawCourt(animationPhase);
$("overhead").onclick = () => {
  resetZoom("wide");
  cameraPlayer = null;
  cameraFollow = null;
  lookYaw = lookPitch = 0;
  drawCourt(animationPhase);
};
$("view3d").onchange = (event) => {
  if (event) { positionView = false; threatView = false; }
  $("positionView").setAttribute("aria-pressed", String(positionView));
  $("threatView").setAttribute("aria-pressed", String(threatView));
  if (event || !$("view3d").checked) { tacticalView = false; realisticView = false; }
  $("realisticView").setAttribute("aria-pressed", String(realisticView));
  $("tacticalView").setAttribute("aria-pressed", String(tacticalView));
  localStorage.setItem("epvView3d", $("view3d").checked ? "1" : "0");
  document.querySelector(".attack-label").textContent = $("view3d").checked
    ? "3D · FACING THE ATTACKING BASKET"
    : "← OFFENSE ATTACKS";
  $("tooltip").hidden = true;
  drawCourt(animationPhase);
};
$("view3d").checked = localStorage.getItem("epvView3d") !== "0";
document.querySelector(".attack-label").textContent = $("view3d").checked
  ? "3D · FACING THE ATTACKING BASKET"
  : "← OFFENSE ATTACKS";
$("threatView").onclick = () => {
  threatView=true; positionView=false; tacticalView=false; realisticView=false; cameraPlayer=null; cameraFollow=null;
  resetZoom("flat"); $("view3d").checked=false; $("view3d").onchange();
};
$("positionView").onclick = () => {
  threatView=false; positionView=true; tacticalView=false; realisticView=false; cameraPlayer=null; cameraFollow=null;
  resetZoom("flat"); $("view3d").checked=false; $("view3d").onchange();
};
$("realisticView").onclick = () => {
  positionView=false; threatView=false;
  realisticView=true; tacticalView=false; cameraPlayer=null; cameraFollow=null;
  resetZoom("wide"); $("view3d").checked=true; $("view3d").onchange();
};
$("tacticalView").onclick = () => {
  positionView=false; threatView=false;
  realisticView=false;
  tacticalView = true;
  cameraPlayer = null; cameraFollow = null;
  resetZoom("tactical");
  $("view3d").checked = true;
  $("view3d").onchange();
};
$("epvMode").onchange = render;
for (const [id, dir] of [
  ["prevPlay", -1],
  ["nextPlay", 1],
])
  $(id).onclick = () => {
    const n = visiblePlays.findIndex((p) => p.id === play?.id);
    if (visiblePlays.length)
      loadPlay(
        visiblePlays[(n + dir + visiblePlays.length) % visiblePlays.length].id,
      );
  };
for (const id of ["epvChart", "riskChart"])
  $(id).onclick = (e) => {
    const rect = $(id).getBoundingClientRect(),
      ratio = Math.max(
        0,
        Math.min(1, (e.clientX - rect.left - 8) / (rect.width - 45)),
      );
    seekFrame(
      play.frames[0].frame +
        ratio * (play.frames.at(-1).frame - play.frames[0].frame),
    );
  };
$("methodButton").onclick = () => manifest && showModel();
$("closeMethod").onclick = () => $("methodDialog").close();
$("methodDialog").onclick = (e) => {
  if (e.target === $("methodDialog")) {
    const r = e.target.getBoundingClientRect();
    if (
      e.clientX < r.left ||
      e.clientX > r.right ||
      e.clientY < r.top ||
      e.clientY > r.bottom
    )
      e.target.close();
  }
};
$("court").addEventListener("wheel", (e) => {
  if (!play) return;
  e.preventDefault();
  const delta = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 300 : 1);
  const mode = zoomMode(), offset = zoomOffsets[mode];
  const previousZoom = courtZoom[mode];
  courtZoom[mode] = Math.max(0.6, Math.min(3, courtZoom[mode] * Math.exp(-Math.max(-200, Math.min(200, delta)) * 0.002)));
  const ratio = courtZoom[mode] / previousZoom;
  const rect = $("court").getBoundingClientRect();
  const centerY = mode === "flat" ? 0.5 : mode === "follow" ? 0.48 : 0.48;
  const mx = (e.clientX - rect.left) / rect.width;
  const my = (e.clientY - rect.top) / rect.height;
  offset[0] = mx - 0.5 - ratio * (mx - 0.5 - offset[0]);
  offset[1] = my - centerY - ratio * (my - centerY - offset[1]);
  $("tooltip").hidden = true;
  drawCourt(animationPhase);
}, { passive: false });
$("court").onpointerdown = (e) => {
  if (!$("view3d").checked || cameraPlayer === null || e.button !== 0) return;
  lookDrag = {x:e.clientX, y:e.clientY, yaw:lookYaw, pitch:lookPitch};
  suppressCourtClick = false;
  $("court").setPointerCapture(e.pointerId);
};
$("court").onpointermove = (e) => {
  if (!lookDrag) return;
  const dx = e.clientX-lookDrag.x, dy = e.clientY-lookDrag.y;
  if (Math.hypot(dx,dy) < 4 && !suppressCourtClick) return;
  suppressCourtClick = true;
  lookYaw = lookDrag.yaw - dx*.006;
  lookPitch = Math.max(-.65,Math.min(.55,lookDrag.pitch + dy*.004));
  $("tooltip").hidden = true;
  drawCourt(animationPhase);
};
$("court").onpointerup = $("court").onpointercancel = () => { lookDrag = null; };
$("court").ondblclick = () => { lookYaw = lookPitch = 0; drawCourt(animationPhase); };
$("court").onclick = (e) => {
  if (suppressCourtClick) { suppressCourtClick = false; return; }
  if (!play || !courtTransform) return;
  const r = $("court").getBoundingClientRect(),
    { scale, cx, cy } = courtTransform;
  const x = (e.clientX - r.left - cx) / scale,
    y = -(e.clientY - r.top - cy) / scale;
  const f = interpolateFrame(
    play.frames[index],
    play.frames[index + 1],
    animationPhase,
  );
  const p = $("view3d").checked
    ? courtHits
        .slice()
        .reverse()
        .find(
          (hit) =>
            Math.hypot(
              hit.x - (e.clientX - r.left),
              hit.y - (e.clientY - r.top),
            ) < hit.r,
        )?.player
    : f.offense.find((p) => Math.hypot(p[1] - x, p[2] - y) < 2);
  if (p && $("movementIdeas").checked && f.offense.some(a=>a[0]===p[0]) && p[0]!==f.geometry?.handler) {
    selectedPass=p[0];setPlaying(false);render();return;
  }
  if (p && $("view3d").checked && !tacticalView) {
    lookYaw = lookPitch = 0;
    cameraPlayer = p[0];
    cameraFollow = null;
    $("tooltip").hidden = true;
    setPlaying(false);
    render();
    return;
  }
  if (!p || !f.passOptions?.some((o) => o.player === p[0])) return;
  selectedPass = p[0];
  playing = false;
  $("playPause").textContent = "▶ Play";
  render();
};
$("court").onmousemove = (e) => {
  if (lookDrag) return;
  if (!play || !courtTransform) return;
  const r = $("court").getBoundingClientRect(),
    { scale, cx, cy } = courtTransform,
    animationPhase = 0;
  const x = (e.clientX - r.left - cx) / scale,
    y = -(e.clientY - r.top - cy) / scale;
  const p = $("view3d").checked
    ? courtHits
        .slice()
        .reverse()
        .find(
          (hit) =>
            Math.hypot(
              hit.x - (e.clientX - r.left),
              hit.y - (e.clientY - r.top),
            ) < hit.r,
        )?.player
    : play.frames[index].offense
        .concat(play.frames[index].defense)
        .find((p) => Math.hypot(p[1] - x, p[2] - y) < 2);
  $("tooltip").hidden = !p;
  const nextHover = p ? p[0] : null;
  if (threatView && nextHover !== hoverPlayer) { hoverPlayer = nextHover; if (!playing) drawCourt(); }
  else hoverPlayer = nextHover;
  if (p) {
    $("tooltip").textContent = (() => {
      const profile = playerProfile(game, p[0], play.frames[index].frame);
      if (play.frames[index].defense.some(d => d[0] === p[0])) {
        const prior = profile.stealPrior;
        const block = defenderProbability(play.frames[index], "block", p[0]);
        const forecast = defenderForecast(play.frames[index], 'steal', selectedPass);
        const probability = defenderProbability(play.frames[index], 'steal', p[0], selectedPass);
        return `${name(p[0])} · ${profile.position}${block != null ? ` · ${pct(block)}% block if holder shoots` : ""}${probability != null ? ` · ${pct(probability)}% interception on pass to ${name(forecast.receiver)}` : ""}${prior ? ` · ${prior.priorPer100.toFixed(2)} steals/100 defensive possessions (shrunk prior) · ${prior.steals} credited steals / ${prior.defensivePossessions} possessions in other games${prior.defensivePossessions ? "" : "; pooled fallback"}` : ""}`;
      }
      return `#${p[5]} ${name(p[0])} · ${profile.position} · ${profile.heightCm ? profile.heightCm + " cm (ACB listed)" : "height unavailable; generic model"} · 3PA/100: ${profile.threePer100 == null ? "—" : profile.threePer100.toFixed(1)} · ${profile.three} threes / ${profile.possessions} on-court offensive possessions; ${profile.shootingSample || "full available sample"} · 3P: ${profile.made}/${profile.three}${profile.three ? " (" + ((100 * profile.made) / profile.three).toFixed(1) + "%)" : " (no attempts)"} · ${profile.possessions < 100 ? "Sparse sample; faded cue. " : ""}Tab color/bar = observed 3P tendency, not measured gravity${p[3] ? "" : " · extrapolated"}`;
    })();
    $("tooltip").style.left =
      Math.min(e.clientX - r.left + 10, r.width - 170) + "px";
    $("tooltip").style.top = Math.max(0, e.clientY - r.top - 30) + "px";
  }
};
$("court").onmouseleave = () => { $("tooltip").hidden = true; if (hoverPlayer != null) { hoverPlayer = null; if (threatView && !playing) drawCourt(); } };
window.addEventListener("resize", render);
document.addEventListener("keydown", (e) => {
  const editing = e.target.isContentEditable ||
    e.target.closest?.("textarea, select, input:not([type=range]):not([type=checkbox]):not([type=radio])");
  if (e.key.toLowerCase() === "v" && !editing && !e.metaKey && !e.ctrlKey && !e.altKey && !e.repeat && !$("methodDialog").open && play) {
    e.preventDefault();
    $("playPause").click();
    return;
  }
  if (["1", "2", "3", "4", "5", "6", "7"].includes(e.key) && !editing && !e.metaKey && !e.ctrlKey && !e.altKey && !$("methodDialog").open && play) {
    e.preventDefault();
    const f = play.frames[index];
    const flight = activePass(game.recordedPasses, play.id, f.frame);
    const holder = f.geometry?.handler ?? flight?.passer ?? recentShot(f)?.player;
    if (e.key === "3" && !holder) return;
    positionView = e.key === "6";
    threatView = e.key === "7";
    realisticView = e.key === "5";
    tacticalView = e.key === "4";
    resetZoom(tacticalView ? "tactical" : ["1", "6", "7"].includes(e.key) ? "flat" : ["2", "5"].includes(e.key) ? "wide" : "follow");
    cameraPlayer = e.key === "3" ? holder : null;
    cameraFollow = null;
    lookYaw = lookPitch = 0;
    $("view3d").checked = !["1", "6", "7"].includes(e.key);
    $("view3d").onchange();
    return;
  }
  if (e.key === "Escape" && !$("methodDialog").open) {
    e.preventDefault();
    if (cameraPlayer !== null) $("overhead").click();
    else if ($("view3d").checked) {
      $("view3d").checked = false;
      $("view3d").onchange();
    }
    $("tooltip").hidden = true;
    return;
  }
  if (
    ["INPUT", "SELECT", "BUTTON"].includes(e.target.tagName) ||
    $("methodDialog").open ||
    !play
  )
    return;
  if (e.code === "Space") {
    e.preventDefault();
    $("playPause").click();
  }
  if (["ArrowRight", "ArrowLeft"].includes(e.code)) {
    e.preventDefault();
    index = Math.max(
      0,
      Math.min(
        play.frames.length - 1,
        index + (e.code === "ArrowRight" ? 1 : -1),
      ),
    );
    setPlaying(false);
    render();
  }
});
function tick(time) {
  if (playing && play) {
    if (!lastTime) lastTime = time;
    animationPhase +=
      (Math.min(time - lastTime, 100) / 200) * Number($("speed").value);
    lastTime = time;
    let changed = false;
    while (animationPhase >= 1 && index < play.frames.length - 1) {
      index++;
      animationPhase -= 1;
      changed = true;
    }
    if (index >= play.frames.length - 1) {
      index = play.frames.length - 1;
      setPlaying(false);
      changed = true;
    }
    if (changed) render();
    if (playing) {
      drawCourt(animationPhase);
      drawEpvChart();
      chart(
        "riskChart",
        "turnover2",
        colors.coral,
        Math.max(
          0.1,
          Math.ceil(
            Math.max(...play.frames.map((f) => f.turnover2 || 0)) * 10,
          ) / 10,
        ),
      );
      const f = interpolateFrame(
        play.frames[index],
        play.frames[index + 1],
        animationPhase,
      );
      $("gameClock").textContent = clock(f.gameClock);
      $("shotClock").textContent =
        f.shotClock == null ? "—" : f.shotClock.toFixed(1);
    }
  }
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);
try {
  spaceGrids = await getJSON("data/space-value.json");
  manifest = await getJSON("data/manifest.json");
  surrogateReport = await getJSON("data/vendor-surrogate.json").catch(() => null);
  if (manifest.metrics.summary.points.shooting) {
    $("modelStatus").textContent =
      manifest.metrics.summary.points.shooting.rmse <
      manifest.metrics.summary.points.constant.rmse
        ? "Shooting inputs improve EPV over the constant benchmark in this sample; validation is limited to ten games."
        : "Shooting inputs are now included. EPV has not beaten the constant benchmark in these ten games.";
  }
  $("gameSelect").innerHTML = manifest.games
    .map(
      (g) =>
        `<option value="${g.match.id}">${escape(g.match.home_team.name)} / ${escape(g.match.away_team.name)}</option>`,
    )
    .join("");
  const hash = new URLSearchParams(location.hash.slice(1));
  const initial =
    manifest.games.find((g) => String(g.match.id) === hash.get("game")) ||
    manifest.games[0];
  $("gameSelect").value = initial.match.id;
  selectGame(initial.match.id);
} catch (e) {
  $("loading").textContent =
    `Could not load model data. Run the training pipeline first. ${e.message}`;
}
