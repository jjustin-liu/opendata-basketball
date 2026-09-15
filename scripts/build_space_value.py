import json, math
from pathlib import Path
shots=[]
for path in Path('viewer/data/plays').glob('*.json'):
 p=json.loads(path.read_text())
 for e in p['events']:
  if e['type']!='shot' or e.get('fouled'):continue
  q=e.get('shotForecast',{}).get('quality',{})
  if q.get('source')!='skillcorner':continue
  f=min(p['frames'],key=lambda f:abs(f['frame']-e['frame']))
  if abs(f['frame']-e['frame'])>5:continue
  player=next((a for a in f['offense'] if a[0]==e['player']),None)
  if player:shots.append([p['gameId'],player[1],player[2],q['fieldGoalValue'],q['pointsIfMade']])
result={}
for game in sorted(set(s[0] for s in shots)):
 cells=[]
 for x in range(-46,0):
  for y in range(-24,24):
   cx,cy=x+.5,y+.5
   three=abs(cy)>21.6535 or math.hypot(cx+40.75,cy)>22.146
   near=[]
   for g,sx,sy,value,points in shots:
    if g==game or (points==3)!=three:continue
    ds=(cx-sx)**2+(cy-sy)**2
    if ds<64:near.append((math.exp(-ds/18),value))
   mass=sum(w for w,v in near)
   if mass>=3:cells.append([x,y,round(sum(w*v for w,v in near)/mass,3)])
 result[str(game)]={'cells':cells,'trainingShots':sum(s[0]!=game for s in shots)}
Path('viewer/data/space-value.json').write_text(json.dumps(result,separators=(',',':')))
print(len(shots),'shots; grids',[(g,len(v['cells'])) for g,v in result.items()])
