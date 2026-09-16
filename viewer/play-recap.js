import { shotPps } from './action-display.js?v=foul-4';
import { cumulativeRisk } from './possession-scoreboard.js?v=aligned-2';
export function playRecap(play, time, passes=[]) {
  const first = (play.events || []).filter(e=>e.type==='shot' && e.frame<=time).sort((a,b)=>a.frame-b.frame)[0];
  const cutoff = first ? Math.min(time,first.frame) : time;
  const {risk,covered,elapsed}=cumulativeRisk(play,cutoff,passes);
  const survival=Number.isFinite(risk)?1-risk:null;
  const forecast=first?.shotForecast;
  const total=shotPps(first);
  return { risk, coverage:elapsed ? covered/elapsed : 0,
    total, playValue:Number.isFinite(survival) && Number.isFinite(total)?total*survival:null,
    foulProbability:forecast?.foulProbability ?? null,
    fouledPps:forecast?.fouledPps ?? null, notFouledPps:forecast?.notFouledPps ?? null,
    ftSecond:forecast?.ftSecondChanceIfFouled ?? null,
    ftOrb:forecast?.ftOffensiveReboundProbability ?? null,
    freeThrows:first?.shotForecast?.freeThrowValue ?? null,
    first:first?.shotForecast?.quality?.fieldGoalValue ?? null,
    orb:first?.shotForecast?.offensiveReboundProbability ?? null,
    second:first?.shotForecast?.secondChancePerShot ?? null };
}

export function playOutcome(play) {
  if (play.turnover) return 'TURNOVER';
  const shots=(play.events || []).filter(e=>e.type==='shot');
  const last=shots.at(-1);
  if (last?.label?.startsWith('Made')) return last.label.toUpperCase();
  if (last) return `MISSED SHOT · ${play.points} POINT${play.points===1?'':'S'}`;
  return `PLAY COMPLETE · ${play.points} POINT${play.points===1?'':'S'}`;
}

export function recapMarkup(recap) {
  const number=v=>Number.isFinite(v)?v.toFixed(2):'—';
  const percent=v=>Number.isFinite(v)?`${(100*v).toFixed(1)}%`:'—';
  const survival=Number.isFinite(recap.risk)?1-recap.risk:null;
  const clean=Number.isFinite(recap.foulProbability)?1-recap.foulProbability:null;
  return `<h3>Before the first shot <small>· modeled possibilities, not the result</small></h3>
    <div class="recap-headline"><strong>${number(recap.playValue)} <small>EPV</small></strong><span>=</span><span><b>${number(recap.total)}</b> PPA</span><span>×</span><span><b>${percent(survival)}</b><small>expected survival</small></span></div>
    <div class="recap-branches">
      <div><span>No foul <small title="Offensive rebound probability conditional on a live field-goal miss">ORB ${percent(recap.orb)} on a miss</small></span><strong>${percent(clean)} × ${number(recap.notFouledPps)} <small>PPS</small></strong></div>
      <div><span>Foul <small title="Offensive rebound probability conditional on a missed final free throw">And-1s + FTs · FT ORB ${percent(recap.ftOrb)}</small></span><strong>${percent(recap.foulProbability)} × ${number(recap.fouledPps)} <small>PPS</small></strong></div>
    </div>
    <div class="recap-footnote">Expected play value · both branches include second chances</div>
    <div class="recap-footnote">${percent(recap.risk)} TOV before first attempt · ${Math.round(recap.coverage*100)}% risk coverage</div>
    <details><summary>What’s included</summary><p>Combined scoring value = P(fouled) × points if fouled + P(not fouled) × points if not fouled. Fouled includes made baskets on and-ones, player-specific free throws and ${number(recap.ftSecond)} expected FT-rebound points per foul trip. Not fouled includes SQ and field-goal second chances. FT rebound rate uses a small other-game sample; continuation value is borrowed from field-goal rebounds.</p><p>The no-turnover factor accumulates supported risk only, stopping at the first shot to avoid discounting continuation twice. This replay-based estimate is not calibrated whole-play EPV. Missing intervals are excluded, so incomplete coverage can understate risk. Plays without a supported scoring attempt have no combined estimate.</p></details>`;
}
