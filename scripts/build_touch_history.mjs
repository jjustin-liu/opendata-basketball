import fs from 'node:fs';
const aliases = new Map(fs.readFileSync('data/player_id_aliases.csv','utf8').trim().split('\n').slice(1).map(line=>{const p=line.split(',');return [+p[0],+p[2]];}));
const history = {};
for (const game of fs.readdirSync('data/matches')) {
  const path = `data/matches/${game}/${game}_dynamic_events.json`;
  if (!fs.existsSync(path)) continue;
  const events = JSON.parse(fs.readFileSync(path,'utf8'));
  for (const t of events.touches || []) {
    if (t.playerId == null || !Number.isFinite(t.startFrame) || !Number.isFinite(t.endFrame)) continue;
    (history[t.possessionId] ||= []).push({id:t.id,player:aliases.get(t.playerId) || t.playerId,
      start:t.startFrame,end:t.endFrame,shotClock:t.shotClock});
  }
}
for (const touches of Object.values(history)) touches.sort((a,b)=>a.start-b.start);
fs.writeFileSync('viewer/data/touch-history.json', JSON.stringify(history));
