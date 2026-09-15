import fs from 'node:fs';
const annotations = {};
const aliases = new Map(fs.readFileSync('data/player_id_aliases.csv','utf8').trim().split('\n').slice(1).map(line=>{const p=line.split(',');return [+p[0],+p[2]];}));
for (const game of fs.readdirSync('data/matches')) {
  const path=`data/matches/${game}/${game}_dynamic_events.json`;
  if (!fs.existsSync(path)) continue;
  const events=JSON.parse(fs.readFileSync(path,'utf8'));
  for (const r of events.rebounds || []) {
    if (!r.rebounded || r.defensive || r.rebounderId == null) continue;
    (annotations[r.possessionId] ||= []).push({frame:r.frame,player:aliases.get(r.rebounderId) || r.rebounderId});
  }
}
fs.writeFileSync('viewer/data/rebound-annotations.json',JSON.stringify(annotations));
