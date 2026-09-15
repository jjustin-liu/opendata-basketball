import { drawMovementIdea } from "./movement-ideas.js?v=2";
import { ballTrail, drawBallTrail } from "./ball-trail.js";
import { drawDefenderLabel, defenderThreatReference, rimWingAngle } from "./defender-label.js?v=flight-risk-1";
import { displayBall } from "./ball-display.js";
import { shootingMotion } from "./shooting-motion.js";
import { flightLabel } from "./pass-flight.js?v=flight-risk-1";
import { heightFeet, profileTab, defenderNumbers, defenderChipScale } from "./player-profile.js?v=position-size-1";
import { bestPass, shotPps, actionCard } from "./action-display.js";
import { closestDefender, drawDefenderDistance } from "./defender-distance.js?v=distance-2";
let followPose = null;
let lastCameraTime = 0;
// Perspective camera above the backcourt, looking toward the attacking basket.
export function drawCourt3D(ctx, w, h, f, opts) {
  const hits = [];
  const playerEye = [...f.offense, ...f.defense].find(
    (p) => p[0] === opts.cameraPlayer,
  );
  const eye =
    opts.followBall && playerEye
      ? [playerEye[0], f.ball[0], f.ball[1]]
      : playerEye;
  const eyeHeight = opts.followBall
    ? 15
    : eye
      ? heightFeet(opts.profile(eye[0])) + 3
      : 5.8;
  let focal = (eye ? Math.min(w * 0.65, h * 1.05) : Math.min(w * 0.95, h * 1.15));
  const dx = eye ? -40.75 - eye[1] : -1,
    dy = eye ? -eye[2] : 0;
  const length = Math.hypot(dx, dy) || 1,
    fx = dx / length,
    fy = dy / length;
  // Follow from ten feet behind and slightly over the shoulder.
  const back = opts.followBall ? 22 : 10;
  const followX = eye ? eye[1] - fx * back + fy * 2 : 0;
  const followY = eye ? eye[2] - fy * back - fx * 2 : 0;
  const now = performance.now();
  if (eye) {
    const desired = [
      followX,
      followY,
      eyeHeight,
      fx,
      fy,
      Math.atan2(10 - eyeHeight, length + back),
      focal,
    ];
    if (!followPose || followPose.key !== opts.cameraKey)
      followPose = { key: opts.cameraKey, values: desired };
    else {
      const alpha =
        1 -
        Math.exp(
          -Math.min(0.1, Math.max(0, (now - lastCameraTime) / 1000)) * 10,
        );
      followPose.values = desired.map(
        (v, i) => followPose.values[i] + (v - followPose.values[i]) * alpha,
      );
    }
    focal = followPose.values[6];
  } else followPose = null;
  if (opts.tactical) focal = Math.min(w / 112, h / 52) * 115;
  focal *= opts.zoom ?? 1;
  lastCameraTime = now;
  const camera = (x, y, z = 0) => {
    // A centered tilted camera, rather than shearing the court sideways.
    if (opts.tactical) return [x, -y * .72 - z * .694, 115 + y * .694 - z * .72];
    if (eye) {
      const [px, py, pz, ux, uy, basePitch] = followPose.values;
      const yaw = opts.lookYaw || 0, pitch = basePitch + (opts.lookPitch || 0);
      const rx = ux*Math.cos(yaw)-uy*Math.sin(yaw), ry = ux*Math.sin(yaw)+uy*Math.cos(yaw);
      const norm = Math.hypot(ux, uy) || 1,
        vx = rx / norm,
        vy = ry / norm;
      const forward = (x - px) * vx + (y - py) * vy,
        up = z - pz;
      return [
        (x - px) * vy - (y - py) * vx,
        forward * Math.sin(pitch) - up * Math.cos(pitch),
        forward * Math.cos(pitch) + up * Math.sin(pitch),
      ];
    }
    const forward = 20 - x,
      down = 38 - z;
    return [y, down * 0.757 - forward * 0.653, forward * 0.757 + down * 0.653];
  };
  const screen = ([x, y, d]) => [
    w * (0.5 + (opts.zoomOffset?.[0] || 0)) + (x * focal) / d,
    h * ((eye ? 0.48 : 0.48) + (opts.zoomOffset?.[1] || 0)) + (y * focal) / d,
    focal / d,
    d,
  ];
  const project = (x, y, z = 0) => screen(camera(x, y, z));
  function path(points, color, width = 1.5, fill = null, close = false) {
    const ps = points.map((p) => camera(...p)),
      near = 0.8;
    const intersection = (a, b) => {
      const t = (near - a[2]) / (b[2] - a[2]);
      return a.map((v, i) => v + (b[i] - v) * t);
    };
    ctx.beginPath();
    if (fill || close) {
      const clipped = [];
      for (let i = 0; i < ps.length; i++) {
        const a = ps[(i + ps.length - 1) % ps.length],
          b = ps[i];
        if (a[2] >= near !== b[2] >= near) clipped.push(intersection(a, b));
        if (b[2] >= near) clipped.push(b);
      }
      if (clipped.length < 3) return;
      clipped.forEach((p, i) => {
        const q = screen(p);
        if (i) ctx.lineTo(q[0], q[1]);
        else ctx.moveTo(q[0], q[1]);
      });
      ctx.closePath();
    } else {
      for (let i = 1; i < ps.length; i++) {
        let a = ps[i - 1],
          b = ps[i];
        if (a[2] < near && b[2] < near) continue;
        if (a[2] < near) a = intersection(a, b);
        else if (b[2] < near) b = intersection(a, b);
        const u = screen(a),
          v = screen(b);
        ctx.moveTo(u[0], u[1]);
        ctx.lineTo(v[0], v[1]);
      }
    }
    if (fill) {
      ctx.fillStyle = fill;
      ctx.fill();
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.stroke();
  }
  // Stylized, generic human meshes: jersey, shorts, limbs, shoes and head.
  function human(p, off) {
    const size = heightFeet(opts.profile(p[0])) / 6.23;
    const pose = off
      ? shootingMotion(opts.motionEvents, p[0], opts.visualFrame ?? f.frame)
      : null;
    const lift = pose ? pose.jump - pose.crouch : 0;
    const dirX = -40.75 - p[1],
      dirY = -p[2],
      distance = Math.hypot(dirX, dirY) || 1;
    const ux = pose ? dirX / distance : -1,
      uy = pose ? dirY / distance : 0;
    const world = (a, b, z) => [
      p[1] + (-ux * a + uy * b) * size,
      p[2] + (-uy * a - ux * b) * size,
      (z + lift) * size,
    ];
    const x = p[1],
      y = p[2],
      kit = off ? "#202830" : "#4169a1",
      skin = "#b99779";
    function limb(points, width, color) {
      const joints = points.map(q => world(...q));
      const scale = project(...joints[0])[2];
      ctx.save(); ctx.lineCap = "round"; ctx.lineJoin = "round";
      path(joints, color, Math.max(1, scale * size * width));
      ctx.restore();
    }
    // Rounded articulated limbs and a tapered jersey, in true court-height units.
    const bend = pose?.crouch || 0;
    for (const side of [-1, 1]) {
      limb([[0,side*.42,2.9],[-.12-bend,side*.48,1.5],[0,side*.53,.3+bend]], .36, skin);
      limb([[.12,side*.53,.15+bend],[-.43,side*.53,.15+bend]], .33, "#d4dce0");
      limb([[0,side*.42,3.05],[0,side*.45,2.35]], .59, kit);
    }
    path([[0,-.68,3.15],[0,.68,3.15],[0,.91,4.8],[0,.57,5.04],[0,-.57,5.04],[0,-.91,4.8]].map(q=>world(...q)), "#ffffff18", .6, kit, true);
    limb([[0,0,5.0],[0,0,5.35]], .34, skin);
    for (const side of [-1, 1]) {
      const r = pose?.raise || 0;
      if (off) {
        limb([[0,side*.85,4.78],[-.25-.25*r,side*(.96-.32*r),3.8+2*r],[-.4-.25*r,side*(.97-.75*r),3.15+4*r]], .3, skin);
      } else {
        limb([[0,side*.85,4.78],[0,side*1.75,4.78],[0,side*2.65,4.78]], .3, skin);
        limb([[0,side*2.65,4.78],[0,side*2.9,4.78]], .4, skin);
      }
      limb([[0,side*.76,4.77],[0,side*.72,4.3]], .08, off ? "#70838d" : "#a2bdd4");
    }
    const [hx, hy, scale, depth] = project(...world(0, 0, 5.7));
    if (depth > 0.8) {
      ctx.beginPath();
      ctx.ellipse(
        hx,
        hy,
        scale * size * 0.42,
        scale * size * 0.53,
        0,
        0,
        Math.PI * 2,
      );
      ctx.fillStyle = skin;
      ctx.fill();
    }
  }
  const arc = (x, y, radius, z = 0, start = 0, end = 2 * Math.PI) =>
    Array.from({ length: 81 }, (_, i) => {
      const a = start + ((end - start) * i) / 80;
      return [x + Math.cos(a) * radius, y + Math.sin(a) * radius, z];
    });
  const bg = ctx.createLinearGradient(0, 0, 0, h);
  bg.addColorStop(0, "#0b141e");
  bg.addColorStop(1, "#27313b");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, w, h);
  path(
    [
      [-49, -28],
      [-49, 28],
      [49, 28],
      [49, -28],
    ],
    "#7c6c53",
    1,
    "#bfa77e",
    true,
  );
  for (let x = -46; x < 46; x += 3) {
    path(
      [
        [x, -24.606],
        [x, 24.606],
        [Math.min(46, x + 3), 24.606],
        [Math.min(46, x + 3), -24.606],
      ],
      "#cbbb9d",
      0.3,
      Math.round((x + 46) / 3) % 2 ? "#d7c5a3" : "#dfcfb1",
      true,
    );
  }
  const line = "#f6f1e2";
  path(
    [
      [-45.932, -24.606],
      [-45.932, 24.606],
      [45.932, 24.606],
      [45.932, -24.606],
    ],
    line,
    2,
    null,
    true,
  );
  path(
    [
      [0, -24.606],
      [0, 24.606],
    ],
    line,
  );
  path(arc(0, 0, 5.905), line);
  for (const sign of [-1, 1]) {
    path(
      [
        [sign * 45.932, -8.038],
        [sign * 26.903, -8.038],
        [sign * 26.903, 8.038],
        [sign * 45.932, 8.038],
      ],
      line,
      1.5,
      "#526c7c55",
    );
    path(arc(sign * 26.903, 0, 5.905), line);
    const hoop = sign * 40.75;
    const corner = 40.75 - Math.sqrt(22.146 ** 2 - 21.6535 ** 2);
    const theta = Math.acos((40.75 - corner) / 22.146);
    const three = Array.from({ length: 81 }, (_, i) => {
      const a = -theta + (2 * theta * i) / 80;
      return [sign * (40.75 - 22.146 * Math.cos(a)), 22.146 * Math.sin(a)];
    });
    path(
      [[sign * 45.932, -21.6535], ...three, [sign * 45.932, 21.6535]],
      line,
      2,
    );
    path(
      [
        [sign * 44, 0, 0],
        [sign * 44, 0, 12],
        [sign * 42, 0, 12],
      ],
      "#8b99a3",
      4,
    );
    path(
      [
        [sign * 42, -3, 9],
        [sign * 42, 3, 9],
        [sign * 42, 3, 13],
        [sign * 42, -3, 13],
      ],
      "#c4e8f1",
      2,
      "#b9e4ed44",
      true,
    );
    path(arc(hoop, 0, 0.75, 10), "#f08c3e", 3);
    path(arc(hoop, 0, 0.5, 8.5), "#ffffff88", 1);
    for (let i = 0; i < 8; i++) {
      const a = (i * Math.PI) / 4;
      path(
        [
          [hoop + 0.75 * Math.cos(a), 0.75 * Math.sin(a), 10],
          [hoop + 0.5 * Math.cos(a), 0.5 * Math.sin(a), 8.5],
        ],
        "#ffffff88",
        1,
      );
    }
  }
  for (const cell of opts.driveCells || []) {
    path(
      cell.corners.map(([x, y]) => [x, y, 0.02]),
      "transparent",
      0,
      cell.space ? `rgba(65,145,210,${cell.alpha})` : `rgba(255,139,36,${cell.alpha})`,
      true,
    );
  }
  drawMovementIdea(ctx, opts.movement, p=>camera(p[0],p[1],.03)[2]>.8?project(p[0],p[1],.03):null, opts.movement?project(...opts.movement.to)[2]:1);
  const holder = f.offense.find((p) => p[0] === f.geometry?.handler);
  const matchup = closestDefender(f);
  let distanceLabel = null;
  if (matchup) {
    const { holder: a, defender: b, distance } = matchup;
    ctx.setLineDash([7, 5]);
    path(
      [
        [a[1], a[2], 0.04],
        [b[1], b[2], 0.04],
      ],
      "#b6c5c088",
      1,
    );
    ctx.setLineDash([]);
    if (matchup.signedAngle != null) {
      const start = matchup.rimBearing;
      path(
        [
          [a[1], a[2], 0.04],
          [a[1] + 5 * Math.cos(start), a[2] + 5 * Math.sin(start), 0.04],
        ],
        "#7fa99a66",
        1,
      );
      path(
        arc(a[1], a[2], 2.5, 0.04, start, start + matchup.signedAngle),
        "#7fa99a88",
        1,
      );
    }
    const mid = [(a[1] + b[1]) / 2, (a[2] + b[2]) / 2, 0.04];
    if (camera(...mid)[2] > 0.8)
      distanceLabel = {
        point: project(...mid),
        text: distance.toFixed(1) + " ft",
      };
  }

  if (holder && opts.pressure)
    path(arc(holder[1], holder[2], 5), "#d4955222", 1, "#b06b3522");
  if (holder && opts.lanes)
    for (const lane of f.geometry?.lanes || []) {
      const receiver = f.offense.find((p) => p[0] === lane.player);
      if (receiver) {
        ctx.setLineDash([6, 5]);
        path(
          [
            [holder[1], holder[2], 0.1],
            [receiver[1], receiver[2], 0.1],
          ],
          lane.clearance < 3 ? "#b96355" : "#268d76",
          2,
        );
        ctx.setLineDash([]);
      }
    }
  const scenario = f.passOptions?.find((o) => o.player === opts.selectedPass);
  if (scenario)
    for (const side of ["offense", "defense"])
      for (const p of scenario[side]) {
        ctx.setLineDash([4, 3]);
        path(arc(p[1], p[2], 1.7, 0.1), "#e7af47", 2);
        ctx.setLineDash([]);
      }
  function badge(x, y, r, value, label, color, ring = "#9aa9af", darkText = false) {
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = ring;
    ctx.lineWidth = 2;
    if (!darkText) ctx.stroke();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = darkText ? "#f7faf8" : typeof value === "number" ? opts.epvColor(value) : "#fff";
    ctx.font = `${label || typeof value === "number" ? 600 : 700} ${r * (typeof value === "string" && /^[1-5]$/.test(value) ? 1.25 : 0.66)}px monospace`;
    ctx.fillText(
      typeof value === "number" ? value.toFixed(2) : (value ?? ""),
      x,
      y - (label ? r * 0.24 : 0),
    );
    if (label) {
      ctx.fillStyle = darkText ? "#e1e9e5" : "#d7dfe4";
      ctx.font = `500 ${r * 0.4}px monospace`;
      ctx.fillText(label, x, y + r * 0.48);
    }
  }
  const bestRoute = !opts.flight && !opts.shotEvent && bestPass(f);
  const bestReceiver =
    bestRoute && f.offense.find((p) => p[0] === bestRoute.player);
  if (holder && bestReceiver) {
    ctx.setLineDash([]);
    path(
      [
        [holder[1], holder[2], 0.06],
        [bestReceiver[1], bestReceiver[2], 0.06],
      ],
      "#36c879",
      2.2,
    );
  }
  const defenderLabels = defenderNumbers(f.defense, opts.profile);
  const players = [
    ...f.defense.map((p) => ({ p, off: false })),
    ...f.offense.map((p) => ({ p, off: true })),
  ].sort(
    (a, b) => camera(...b.p.slice(1, 3))[2] - camera(...a.p.slice(1, 3))[2],
  );
  for (const { p, off } of players) {
    if (camera(p[1], p[2])[2] < 1) continue;
    if (!opts.tactical) human(p, off);
    const [groundX, ground, s] = project(p[1], p[2]);
    const [x, y] = project(p[1], p[2], opts.tactical ? .35 : heightFeet(opts.profile(p[0])) + (off ? 1.8 : 1.0));
    const r = Math.max(13, Math.min(27, s * 1.5)) * (off ? 1 : defenderChipScale(defenderLabels.get(p[0])));
    ctx.fillStyle = "#00000033";
    ctx.beginPath();
    ctx.ellipse(groundX, ground, r * 0.9, r * 0.3, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#c0c9cb22";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(groundX, ground);
    ctx.lineTo(x, y);
    ctx.stroke();
    const option = f.passOptions?.find((o) => o.player === p[0]);
    const isHolder = p[0] === holder?.[0],
      isShooter = off && p[0] === opts.shotEvent?.player;
    const good =
      option?.value > f[opts.epvKey] && option.route?.reachableDefenders === 0;
    let value = off ? (isHolder ? f[opts.epvKey] : option?.value) : defenderLabels.get(p[0]);
    let label = off
      ? isHolder
        ? "EPV"
        : option
          ? `${(option.turnoverProbability * 100).toFixed(1)}%`
          : ""
      : "";
    if (off && opts.flight) {
      value = flightLabel(opts.flight, p[0]);
      label = "";
      if (opts.flight.receiver === p[0]) {
        value = Number.isFinite(opts.flight.turnoverProbability) ? (opts.flight.turnoverProbability * 100).toFixed(1) + '%' : '';
        label = Number.isFinite(opts.flight.turnoverProbability) ? 'TOV' : '';
      }
    } else if (isShooter) {
      value =
        f.frame - opts.shotEvent.frame < 15
          ? "SHOT"
          : (shotPps(opts.shotEvent) ?? "—");
      label = value === "SHOT" ? "" : "PPS";
    }
    const passTint = off && !isHolder && !opts.flight && !isShooter && Number.isFinite(option?.value);
    ctx.setLineDash(p[3] ? [] : [4, 3]);
    badge(
      x,
      y,
      r,
      value,
      label,
      passTint ? opts.passFill(option.value) : off && (opts.flight?.receiver === p[0] || isShooter)
        ? "#16834b"
        : off
          ? "#151719"
          : "#4169a1",
      off && opts.flight?.receiver === p[0]
        ? "#36db7a"
        : isShooter
          ? "#36db7a"
          : isHolder
            ? "#fff6dc"
            : good
              ? "#36db7a"
              : option?.route?.immediateReach
                ? "#e6ac39"
                : "#99abb6",
      passTint,
    );
    ctx.setLineDash([]);
    if (off) {
      profileTab(ctx, x, y - r * 1.23, r / 1.75, opts.profile(p[0]), true);
    }
    else {
      const ballScreen = project(f.ball[0], f.ball[1]);
      drawDefenderLabel(ctx, x, y, r, opts.profile(p[0]), f, p[0], defenderLabels.get(p[0]), !!opts.tactical, {
        enabled: opts.defenseDetail,
        showNames: opts.defenderNames,
        receiver: opts.selectedPass,
        unit: Math.max(13, Math.min(27, s * 1.5)),
        wingAngle: rimWingAngle(project, p[1], p[2]),
        reference: defenderThreatReference(opts.replayFrames),
        angle: Math.atan2(ballScreen[1] - ground, ballScreen[0] - x),
      });
    }
    if (!off) drawDefenderDistance(ctx, x, y + r * 1.4, r / 1.5, p, f);
    hits.push({ player: p, x, y, r });
    hits.push({
      player: p,
      x,
      y: (ground + y) / 2,
      r: Math.max(r, Math.abs(ground - y) / 2),
    });
    if (isHolder && !opts.flight && !opts.shotEvent && !f.reason) {
      const best = bestPass(f);
      const ax = Math.max(r * 2.8, Math.min(w - r * 2.8, x)),
        ay = Math.max(r * 1.1, y - r * 2.9);
      ctx.strokeStyle = "#83948c66";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, y - r);
      ctx.lineTo(ax, ay);
      ctx.stroke();
      actionCard(
        ctx,
        ax,
        ay,
        r * 0.8,
        f.shot?.shotPlusSecondChance,
        best?.value,
        opts.epvColor,
      );
    }
  }
  const ball = displayBall(
    f,
    opts.replayFrames || [],
    opts.motionEvents || [],
    opts.visualFrame ?? f.frame,
    opts.profile,
  );
  drawBallTrail(ctx, ballTrail(opts.replayFrames || [], {...f,ball}, opts.visualFrame ?? f.frame), b=>camera(...b.slice(0,3))[2]>.8?project(b[0],b[1],Math.max(.39,b[2]||0)):null, Math.max(3,project(...ball)[2]*.7));
  const [bx, by, bs] = project(ball[0], ball[1], Math.max(0.39, ball[2] || 0));
  if (camera(ball[0], ball[1], ball[2] || 0)[2] > 0.8) {
    ctx.beginPath();
    ctx.arc(bx, by, Math.max(4.5, bs * 0.53), 0, Math.PI * 2);
    ctx.fillStyle = opts.ballColor || "#f2b440";
    ctx.fill();
    ctx.strokeStyle = "#805219";
    ctx.stroke();
  }
  if (distanceLabel) {
    const { point, text } = distanceLabel;
    const x = Math.max(32, Math.min(w - 32, point[0]));
    const y = Math.max(15, Math.min(h - 30, point[1] + 14));
    ctx.font = "400 10px monospace";
    const width = ctx.measureText(text).width + 12;
    ctx.fillStyle = "#11171c66";
    ctx.fillRect(x - width / 2, y - 7, width, 14);
    ctx.fillStyle = "#aebbb7";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, x, y);
  }
  return hits;
}
