import fs from 'node:fs';
import { movementIdea } from '../viewer/movement-ideas.js';
const manifest=JSON.parse(fs.readFileSync('viewer/data/manifest.json'));
const grids=JSON.parse(fs.readFileSync('viewer/data/space-value.json'));
fs.mkdirSync('artifacts/movement-candidates',{recursive:true});
// Hole candidates: empty valuable regions from epv.space_field (control x open-shot
// value above 0.5 pts, no attacker within 5 ft). Each off-ball player within reach
// of a hole centroid gets a candidate at 10 ft/s, alongside the grid-search idea.
const HOLE={minDistance:3,maxDistance:20,minMass:6,speed:10,perPlayer:2};
const dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
function holeCandidates(play,index,holes){
  const frame=play.frames[index],list=holes?.[play.id]?.[String(frame.frame)];
  if(!list||frame.reason||!frame.geometry?.handler||(frame.shotClock??0)<3)return [];
  const holder=frame.offense.find(p=>p[0]===frame.geometry.handler);
  if(!holder)return [];
  const out=[];
  for(const player of frame.offense){
    if(player[0]===holder[0]||!player[3]||player[4]>3)continue;
    const start=[player[1],player[2]];
    const options=list.filter(h=>h[2]>=HOLE.minMass).map(h=>({to:[h[0],h[1]],d:dist(start,h),mass:h[2],cells:h[3]}))
      .filter(h=>h.d>=HOLE.minDistance&&h.d<=HOLE.maxDistance&&dist(h.to,[holder[1],holder[2]])>=5)
      .sort((a,b)=>b.mass/b.d-a.mass/a.d).slice(0,HOLE.perPlayer);
    for(const h of options){
      const seconds=h.d/HOLE.speed;
      if(seconds+dist([holder[1],holder[2]],h.to)/40+.62>frame.shotClock)continue;
      out.push({playId:play.id,index,player:player[0],to:h.to.map(v=>Math.round(v*10)/10),seconds:Math.round(seconds*100)/100,source:'hole',mass:h.mass,cells:h.cells});
    }
  }
  return out;
}
for (const game of manifest.games) {
  const candidates=[];
  const holePath=`viewer/data/holes/${game.match.id}.json`;
  const holes=fs.existsSync(holePath)?JSON.parse(fs.readFileSync(holePath)).plays:null;
  let fromHoles=0;
  for (const entry of game.plays) {
    const play=JSON.parse(fs.readFileSync(`viewer/data/plays/${entry.id}.json`));
    for(let i=0;i<play.frames.length;i++) {
      const frame=play.frames[i];
      // 2.5 Hz simulation; the viewer may hold an estimate for at most 0.2s.
      if(frame.frame%10!==0 || frame.reason || !frame.geometry)continue;
      const seen=new Set();
      for(const player of frame.offense) {
        if(player[0]===frame.geometry.handler)continue;
        const idea=movementIdea(frame,play.frames[i-1],grids[String(play.gameId)],id=>game.players[String(id)]||{},player[0]);
        if(idea){candidates.push({playId:play.id,index:i,player:idea.player,to:idea.to,seconds:idea.seconds,source:'grid'});seen.add(`${idea.player}:${idea.to.map(v=>Math.round(v)).join(',')}`);}
      }
      for(const c of holeCandidates(play,i,holes)){
        const key=`${c.player}:${c.to.map(v=>Math.round(v)).join(',')}`;
        if(seen.has(key))continue;
        seen.add(key);candidates.push(c);fromHoles++;
      }
    }
  }
  fs.writeFileSync(`artifacts/movement-candidates/${game.match.id}.json`,JSON.stringify(candidates));
  console.log(game.match.id,candidates.length,'screened movement candidates,',fromHoles,'from holes');
}
