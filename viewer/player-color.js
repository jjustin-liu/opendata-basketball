// Presentation memory only: never supplies an EPV number or model input.
const NEUTRAL = [112,119,117];
const mix = (a,b,t) => a.map((v,i)=>v+(b[i]-v)*t);
const rgb = color => color.startsWith('#')
  ? [1,3,5].map(i=>parseInt(color.slice(i,i+2),16))
  : color.match(/[\d.]+/g).slice(0,3).map(Number);
export function playerColor(previous, color, time, key) {
  if (!previous || previous.key!==key || time<previous.time || time-previous.time>12.5) previous=null;
  const valid=typeof color==='string';
  const last=valid?rgb(color):previous?.last??NEUTRAL;
  const lastTime=valid?time:previous?.lastTime??time-25;
  const age=(time-lastTime)/25;
  const target=valid?last:mix(last,NEUTRAL,.18+.82*Math.max(0,Math.min(1,(age-.6)/.4)));
  const shown=previous?mix(previous.shown,target,1-Math.exp(-(time-previous.time)/3)):target;
  return {key,time,last,lastTime,shown,fill:`rgb(${shown.map(Math.round).join(',')})`};
}
