import fs from "node:fs";
import { auditShot } from "../viewer/decision-audit.js";
const path = new URL("../viewer/data/manifest.json", import.meta.url);
const m = JSON.parse(fs.readFileSync(path));
let total = 0,
  flagged = 0;
for (const game of m.games) {
  game.shotAudits = [];
  for (const entry of game.plays) {
    const play = JSON.parse(
      fs.readFileSync(
        new URL(`../viewer/data/plays/${entry.id}.json`, import.meta.url),
      ),
    );
    for (const e of play.events.filter((e) => e.type === "shot")) {
      const audit = auditShot(play, e);
      total++;
      if (["missed-pass", "low-shot"].includes(audit.kind)) {
        flagged++;
        game.shotAudits.push({
          ...audit,
          playId: play.id,
          offTeamId: play.offTeamId,
          period: play.period,
          gameClock: e.gameClock,
        });
      }
    }
  }
}
fs.writeFileSync(path, JSON.stringify(m));
console.log({
  shots: total,
  candidates: flagged,
  missedPasses: m.games
    .flatMap((g) => g.shotAudits)
    .filter((a) => a.kind === "missed-pass").length,
});
