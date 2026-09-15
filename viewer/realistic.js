import * as T from './vendor/three.module.js';
import { heightFeet } from './player-profile.js';
import { shootingMotion } from './shooting-motion.js';
import { defenderProbability, defenderThreatStrength, defenderThreatReference } from './defender-label.js';
import { displayBall } from './ball-display.js';
// Generic articulated figures. Joint motion is illustrative, not measured pose.
let view;
const V = (x,y,z) => new T.Vector3(x,y,z);
const mat = (color, roughness=.75) => new T.MeshStandardMaterial({color,roughness});
function mesh(geometry, material, parent, position=[0,0,0]) {
  const m = new T.Mesh(geometry,material); m.position.set(...position);
  m.castShadow=true; m.receiveShadow=true; parent.add(m); return m;
}
function build(canvas) {
  const renderer = new T.WebGLRenderer({canvas,antialias:true,alpha:false});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  renderer.shadowMap.enabled=true; renderer.shadowMap.type=T.PCFSoftShadowMap;
  renderer.toneMapping=T.ACESFilmicToneMapping; renderer.toneMappingExposure=1.15;
  const scene=new T.Scene(); scene.background=new T.Color('#101b25');
  scene.fog=new T.Fog('#101b25',105,210);
  scene.add(new T.HemisphereLight('#e7f1ff','#665342',2.3));
  const light=new T.DirectionalLight('#fff3df',3.2);light.position.set(-15,45,-10);
  light.castShadow=true;light.shadow.mapSize.set(2048,2048);
  Object.assign(light.shadow.camera,{left:-60,right:60,top:60,bottom:-60,near:1,far:130});
  light.shadow.bias=-.0005;light.shadow.normalBias=.03;scene.add(light);
  const camera=new T.PerspectiveCamera(43,1,.1,250);
  const wood=document.createElement('canvas');wood.width=1024;wood.height=512;
  const c=wood.getContext('2d');
  // Deterministic maple floor texture, with staggered plank seams.
  for(let x=0;x<1024;x+=64) for(let y=-64;y<512;y+=128){
    const yy=y+(x/64%2)*64; c.fillStyle=['#bd9866','#c7a475','#d0ae80','#c5a171'][(x/64+y/128+8|0)%4];c.fillRect(x,yy,64,128);
    c.strokeStyle='#9c794c55';c.strokeRect(x,yy,64,128);
    for(let j=4;j<64;j+=7){c.strokeStyle='#eee0b61a';c.beginPath();c.moveTo(x+j,yy);c.lineTo(x+j+2,yy+128);c.stroke();}
  }
  const texture=new T.CanvasTexture(wood);texture.colorSpace=T.SRGBColorSpace;texture.anisotropy=8;
  const floor=mesh(new T.PlaneGeometry(58,104),new T.MeshStandardMaterial({map:texture,roughness:.36}),scene);
  floor.rotation.x=-Math.PI/2;floor.receiveShadow=true;floor.castShadow=false;
  const lineMat=new T.LineBasicMaterial({color:'#fff7e3'});
  function line(points){const g=new T.BufferGeometry().setFromPoints(points.map(([x,z])=>V(x,.025,z)));scene.add(new T.Line(g,lineMat));}
  function arc(x,z,r,a=0,b=Math.PI*2){line(Array.from({length:97},(_,i)=>[x+r*Math.cos(a+(b-a)*i/96),z+r*Math.sin(a+(b-a)*i/96)]));}
  line([[-24.6,-45.93],[24.6,-45.93],[24.6,45.93],[-24.6,45.93],[-24.6,-45.93]]);
  line([[-24.6,0],[24.6,0]]);arc(0,0,5.9);
  for(const sign of [-1,1]){
    line([[-8.04,45.93*sign],[-8.04,26.9*sign],[8.04,26.9*sign],[8.04,45.93*sign]]);arc(0,26.9*sign,5.9);
    // Arc at 6.75 metres plus straight corner sections.
    const a=Math.acos(21.98/22.145);
    const points=Array.from({length:97},(_,i)=>{const t=a+(Math.PI-2*a)*i/96;return [22.145*Math.cos(t),sign*(40.75-22.145*Math.sin(t))];});
    line([[-21.98,45.93*sign],...points.reverse(),[21.98,45.93*sign]]);
    mesh(new T.BoxGeometry(.45,10.5,.45),mat('#354353'),scene,[0,5.25,49*sign]);
    mesh(new T.BoxGeometry(6,3.5,.16),new T.MeshPhysicalMaterial({color:'#dbe8ec',transparent:true,opacity:.27,roughness:.12,side:T.DoubleSide}),scene,[0,11.5,43.1*sign]);
    const rim=mesh(new T.TorusGeometry(.75,.065,10,40),mat('#e36c26'),scene,[0,10,40.75*sign]);rim.rotation.x=Math.PI/2;
    const net=new T.LineBasicMaterial({color:'#f3f1e4',transparent:true,opacity:.65});
    for(let j=0;j<12;j++){const a=j*Math.PI/6;const pts=[V(Math.cos(a)*.75,10,40.75*sign+Math.sin(a)*.75),V(Math.cos(a+.2)*.48,8.65,40.75*sign+Math.sin(a+.2)*.48)];scene.add(new T.Line(new T.BufferGeometry().setFromPoints(pts),net));}
  }
  const ball=mesh(new T.SphereGeometry(.39,24,16),mat('#ca6528',.9),scene);
  for(const rot of [[0,0,0],[Math.PI/2,0,0],[0,Math.PI/2,0]]){const seam=mesh(new T.TorusGeometry(.392,.012,4,48),mat('#392820'),ball);seam.rotation.set(...rot);}
  return {renderer,scene,camera,ball,players:new Map()};
}
function figure(scene,off,number){
  const root=new T.Group();scene.add(root);
  const skin=mat('#aa8264'),kit=mat(off?'#162a3c':'#f0f2ef'),trim=mat(off?'#77d9c4':'#356eb3');
  const pieces=[];
  function ellipsoid(x,y,z,sx,sy,sz,material){const m=mesh(new T.SphereGeometry(1,20,14),material,root,[x,y,z]);m.scale.set(sx,sy,sz);return m;}
  const torso=mesh(new T.CylinderGeometry(.67,.49,1.65,20),kit,root,[0,3.98,0]);torso.scale.z=.64;
  const neck=ellipsoid(0,5.0,0,.19,.28,.19,skin);
  const head=ellipsoid(0,5.48,0,.34,.46,.35,skin);
  const hair=ellipsoid(0,5.7,-.025,.345,.27,.35,mat('#302a27'));
  const nose=ellipsoid(0,5.45,.34,.08,.105,.1,skin);
  const shorts=mesh(new T.CylinderGeometry(.52,.64,.68,16),kit,root,[0,2.9,0]);shorts.scale.z=.7;
  const waistband=mesh(new T.CylinderGeometry(.525,.525,.07,16),trim,root,[0,3.22,0]);waistband.scale.z=.7;
  // Numbers are on the jersey, not floating chips.
  const label=document.createElement('canvas');label.width=128;label.height=128;
  const c=label.getContext('2d');c.fillStyle=off?'#eaf8f3':'#356eb3';c.font='bold 88px sans-serif';c.textAlign='center';c.fillText(String(number||''),64,100);
  const tex=new T.CanvasTexture(label);tex.colorSpace=T.SRGBColorSpace;
  for(const sign of [-1,1]){const n=mesh(new T.PlaneGeometry(.7,.7),new T.MeshBasicMaterial({map:tex,transparent:true,side:T.DoubleSide}),root,[0,4,sign*.44]);n.rotation.y=sign<0?Math.PI:0;}
  for(let i=0;i<8;i++)pieces.push(mesh(new T.CylinderGeometry(i<4?.17:.125,i<4?.22:.16,1,12),skin,root));
  const hands=[-1,1].map(s=>ellipsoid(s,4,0,.13,.21,.09,skin));
  const shoes=[-1,1].map(s=>ellipsoid(s*.36,.15,.13,.22,.15,.44,mat(off?'#e9ebe7':'#234c78')));
  const danger=new T.Group();root.add(danger);
  const wingMaterial=new T.MeshStandardMaterial({color:'#39b9a6',transparent:true,opacity:.3,depthWrite:false});
  const wing=mesh(new T.CylinderGeometry(.04,.04,1,8),wingMaterial,danger,[0,3.7,0]);wing.rotation.z=Math.PI/2;wing.castShadow=false;
  const tailMaterial=new T.MeshStandardMaterial({color:'#eab054',transparent:true,opacity:.38,depthWrite:false});
  const curve=new T.CatmullRomCurve3([V(.5,0,0),V(1,.8,0),V(.8,1.6,0),V(.25,1.7,0)]);
  const tail=mesh(new T.TubeGeometry(curve,20,.035,6,false),tailMaterial,danger,[0,4.4,0]);tail.castShadow=false;
  return {root,pieces,hands,shoes,off,danger,wing,tail};
}
function segment(m,a,b){a=V(...a);b=V(...b);m.position.copy(a).add(b).multiplyScalar(.5);m.scale.y=a.distanceTo(b);m.quaternion.setFromUnitVectors(V(0,1,0),b.sub(a).normalize());}
export function drawRealistic(canvas,f,opts){
  if(!view)view=build(canvas);
  const {renderer,scene,camera,players,ball}=view;
  const w=canvas.clientWidth,h=canvas.clientHeight;
  if(canvas.width!==Math.round(w*renderer.getPixelRatio())||canvas.height!==Math.round(h*renderer.getPixelRatio()))renderer.setSize(w,h,false);
  camera.aspect=w/h;
  camera.position.set(27/(opts.zoom||1),25/(opts.zoom||1),19/(opts.zoom||1));camera.lookAt(0,2,-25);camera.updateProjectionMatrix();
  const visible=new Set();const time=opts.visualFrame/25;
  const reference=defenderThreatReference(opts.frames);
  for(const [list,off] of [[f.offense,true],[f.defense,false]])for(const p of list){
    const key=`${p[0]}-${off}`;visible.add(key);
    if(!players.has(key))players.set(key,figure(scene,off,p[5]));
    const actor=players.get(key),{root,pieces,hands,shoes}=actor;root.visible=true;
    const prior=opts.previous?.[off?'offense':'defense']?.find(q=>q[0]===p[0]);
    const dt=(f.frame-(opts.previous?.frame??f.frame))/25;
    const vx=prior&&dt>0&&dt<.5?(p[2]-prior[2])/dt:0,vz=prior&&dt>0&&dt<.5?(p[1]-prior[1])/dt:0;
    const speed=Math.min(18,Math.hypot(vx,vz));
    const pose=off?shootingMotion(opts.events,p[0],opts.visualFrame):null;
    const size=heightFeet(opts.profile(p[0]))/5.95;
    root.scale.setScalar(size);root.position.set(p[2],(pose?.jump||0)*size,p[1]);
    const face=off?V(-p[2],0,-40.75-p[1]):V(f.ball[1]-p[2],0,f.ball[0]-p[1]);
    root.rotation.y=speed>2&&!pose?Math.atan2(vx,vz):Math.atan2(face.x,face.z);
    actor.danger.visible=!off&&opts.pressure;
    if(!off){
      const steal=defenderThreatStrength(defenderProbability(f,'steal',p[0],opts.selectedPass),reference.steal,'steal');
      const block=defenderThreatStrength(defenderProbability(f,'block',p[0]),reference.block,'block');
      actor.danger.rotation.y=Math.atan2(-p[2],-40.75-p[1])-root.rotation.y;
      actor.wing.visible=steal>0;actor.wing.scale.y=3+4*steal;
      actor.tail.visible=block>0;actor.tail.scale.setScalar(.4+block);
    }
    const gait=Math.sin(time*10+p[0]%7)*Math.min(.78,speed/14),bend=pose?.crouch||(!off?.18:0);
    let i=0;
    for(const [j,s] of [-1,1].entries()){
      const swing=gait*s,hip=[s*.34,2.75,0],knee=[s*.37,1.5-bend,swing],foot=[s*.4,.25, -swing];
      segment(pieces[i++],hip,knee);segment(pieces[i++],knee,foot);shoes[j].position.set(foot[0],.15+Math.max(0,swing)*.3,foot[2]+.12);
      const r=pose?.raise||0;
      const shoulder=[s*.66,4.65,0],elbow=off?[s*(.75-.35*r),3.85+1.25*r,-swing*.6+.25]:[s*1.25,4.25,.2];
      const hand=off?[s*(.7-.48*r),3.35+3*r,.45+r*.2]:[s*1.95,4.3,.35];
      segment(pieces[i++],shoulder,elbow);segment(pieces[i++],elbow,hand);hands[j].position.set(...hand);
    }
  }
  for(const [key,actor] of players)actor.root.visible=visible.has(key);
  const b=displayBall(f,opts.frames,opts.events,opts.visualFrame,opts.profile);
  ball.visible=b.every(Number.isFinite);if(ball.visible)ball.position.set(b[1],Math.max(.39,b[2]),b[0]);
  renderer.render(scene,camera);
}
