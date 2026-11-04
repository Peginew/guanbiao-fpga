#pragma once
static const char CONSOLE_HTML[] PROGMEM = R"HTML(<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>R24 · 完整三轮上位机</title>
<style>
:root{color-scheme:dark;--bg:#09111f;--card:#111f32;--line:#314257;--ink:#eff6ff;--muted:#9bb2cb;--accent:#57d5ff;--red:#ff6e7c}
*{box-sizing:border-box}body{margin:0;font:15px system-ui,-apple-system,Segoe UI,sans-serif;background:linear-gradient(145deg,#09111f,#12283b);color:var(--ink);min-height:100vh}
main{max-width:1050px;margin:auto;padding:22px 16px 36px}header{display:flex;justify-content:space-between;align-items:center;gap:15px;margin-bottom:18px}h1{font-size:clamp(23px,4vw,32px);margin:0}h2{font-size:18px;margin:0 0 16px}small,.sub{color:var(--muted)}.pill{padding:9px 12px;border-radius:30px;background:#1a3449;color:#89e2ac;font-weight:700;white-space:nowrap}
.layout{display:grid;grid-template-columns:1.3fr 1fr;gap:16px}.card{background:var(--card);border:1px solid var(--line);border-radius:19px;padding:20px;box-shadow:0 12px 30px #0003}.wide{grid-column:1/-1}
.padArea{display:flex;gap:20px;align-items:center;flex-wrap:wrap;justify-content:space-around}.pad{position:relative;width:min(68vw,256px);height:min(68vw,256px);border-radius:50%;touch-action:none;user-select:none;border:2px solid #415d74;background:radial-gradient(circle,#253d53 0 24%,#1b2f44 26% 54%,#12263b 56%);box-shadow:inset 0 0 40px #0005;cursor:crosshair}.crossV,.crossH{position:absolute;background:#49637d;opacity:.7;pointer-events:none}.crossV{left:50%;height:94%;top:3%;width:1px}.crossH{top:50%;width:94%;left:3%;height:1px}.knob{position:absolute;width:74px;height:74px;left:50%;top:50%;transform:translate(-50%,-50%);border-radius:50%;background:linear-gradient(145deg,#85e5ff,#1989c0);box-shadow:0 5px 24px #0009;pointer-events:none}.padActive{border-color:var(--accent)}.dpad{display:grid;grid-template-columns:repeat(3,58px);grid-template-rows:repeat(3,54px);gap:7px;align-items:center}.dpad button{height:54px;touch-action:none}.up{grid-column:2;grid-row:1}.left{grid-column:1;grid-row:2}.center{grid-column:2;grid-row:2}.right{grid-column:3;grid-row:2}.down{grid-column:2;grid-row:3}
button{border:1px solid #426079;color:var(--ink);background:#234059;border-radius:11px;padding:12px 13px;font:inherit;font-weight:700;cursor:pointer;touch-action:manipulation}button:disabled{opacity:.45;cursor:default}button:active,.pressed{background:#267daa!important}button.danger{background:#8f273a;border-color:#ee6c83}.bigstop{width:100%;font-size:20px;padding:18px;margin-top:15px}.mutedbtn{background:#273747}.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.row>*{flex:1}input[type=range]{width:100%;accent-color:var(--accent)}input[type=number]{min-width:0;width:100%;background:#0a1b2c;border:1px solid #415971;color:white;border-radius:9px;padding:12px;font:inherit}.forms{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.forms section{border:1px solid #334b60;border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:10px}.forms label{font-size:13px;color:var(--muted)}.forms button{margin-top:auto}.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.stats div{background:#0b1b2a;padding:13px;border-radius:11px;min-width:0}.stats strong{display:block;font-size:21px;overflow-wrap:anywhere}.stats small{display:block;margin-bottom:6px}.tip{font-size:13px;color:var(--muted);line-height:1.7;margin:11px 0 0}.error{color:var(--red)}#note{min-height:20px;margin-top:10px;color:#8ae7c1}
@media(max-width:800px){.layout{grid-template-columns:1fr}.wide{grid-column:auto}.forms{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.padArea{gap:10px}}@media(max-width:370px){.dpad{grid-template-columns:repeat(3,45px);grid-template-rows:repeat(3,47px);gap:4px}.dpad button{height:47px;padding:5px}}
[hidden]{display:none!important}.mapTabs{display:flex;gap:8px;margin:14px 0 0}.mapTabs button{flex:1;background:#172e43;border-radius:11px 11px 0 0}.mapTabs button.active{color:#09111f;background:#7de4ff;border-color:#7de4ff}.mapPanel{border:1px solid #415971;border-radius:0 0 12px 12px;padding:15px;margin:0 0 14px}.mapPanel h2{margin-bottom:8px}.coordinateGrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.coordinateGrid label,.mapPanel .row label{font-size:13px;color:var(--muted)}.mapPanel select{display:block;width:100%;padding:11px;background:#0a1b2c;color:white;border:1px solid #415971;border-radius:9px}.modeBar{padding:9px 12px;border-left:3px solid #7de4ff;background:#172e43;border-radius:7px;margin:10px 0;font-weight:700;font-size:14px}.mapPanel .row{margin-top:10px}.mapPanel fieldset{min-width:0;border:1px solid #415971;border-radius:10px;margin:12px 0;padding:12px}.mapPanel legend{font-size:14px;color:#c9dcec;padding:0 5px}@media(max-width:560px){.coordinateGrid{grid-template-columns:repeat(2,minmax(0,1fr))}.mapPanel{padding:12px}.mapTabs button{font-size:14px;padding:11px 6px}}
@media(max-width:560px){#mapCard>.row:first-child{display:block}#mapCard>.row:first-child h2{margin-bottom:8px}.goalInputs{display:grid;grid-template-columns:1fr 1fr;align-items:end}.goalInputs>label:last-child{grid-column:1/-1}}
</style></head><body><div style="max-width:1050px;margin:12px auto;padding:12px 16px;background:#fff0f1;color:#26313a;border-left:4px solid #b8242a"><a href="/" style="color:#b8242a">返回扇区巡检与点位结果</a><p>完整上位机保留原地图、障碍编辑、路径预览、摇杆/键盘与PID参数显示。进入此模式先停车并清除旧任务；与扇区巡检互斥，不会借用巡检输出许可。</p><button id="consoleAcquire">停车后接管完整上位机</button> <button id="consoleReturn">停车并返回巡检</button><span id="consoleOwnerState">等待状态</span><p>首次请在巡检主页确认真实IMU/标定并设置原点，再接管。PID仅显示原保存参数，未新增在线写入接口。</p></div><main>
<header><div><h1>三轮机器人 <span style="color:var(--accent)">S3</span></h1><div class="sub">M1 / M2 双轮驱动＋支撑轮 · 真实IMU · R20</div></div><div class="pill" id="connected">正在连接…</div></header>
<div class="layout">
<div class="card wide" id="mapCard"><div class="row"><h2>二维坐标 · 米制导航</h2><span class="sub" id="mapSource">真实IMU航向＋FG计距 · 待标定</span></div>
<p class="tip" id="coordinateHelp">坐标单位为米：归零后X填5、Y填0可走5米。单段最长5米；坐标±10米，合计最长30米。速度上限220mm/s（0.22米/秒），默认40；转弯、纠偏和到点自动减速。</p><div id="demoBanner" style="display:none;background:#614714;padding:12px;border-radius:10px;margin-bottom:12px">离线演示：仅理想运动动画，不连接小车，不代表实车精度。此演示只支持坐标导航、停车、急停和归零。</div>
<div class="mapTabs" role="tablist" aria-label="地图设置"><button id="obstacleTab" role="tab" aria-controls="obstacleEditor" aria-selected="false">① 障碍设置</button><button id="routeTab" role="tab" aria-controls="routeEditor" aria-selected="true" class="active">② 终点与路线</button></div>
<section id="obstacleEditor" class="mapPanel" role="tabpanel" aria-labelledby="obstacleTab" hidden><h2>障碍设置</h2><p class="tip">先按当前原点设置障碍，再去“终点与路线”选择目标。可填坐标添加，也可在下方地图点两次；此页操作只修改地图。</p>
<div class="row"><label>障碍形状 / 地图绘制方式<select id="mapEditMode"><option value="target" hidden disabled>选择终点</option><option value="rect">矩形 · 两个对角</option><option value="wall">墙段 · 两个端点</option></select></label><label>墙厚 / 米<input id="wallThickness" type="number" value="0.10" min="0.02" max="2" step="0.02"></label></div>
<fieldset><legend>用坐标添加 / 修改障碍 · 单位米</legend><div class="coordinateGrid"><label>X1<input id="obstacleX1" type="number" min="-10" max="10" step="0.05" placeholder="第一个点 X"></label><label>Y1<input id="obstacleY1" type="number" min="-10" max="10" step="0.05" placeholder="第一个点 Y"></label><label>X2<input id="obstacleX2" type="number" min="-10" max="10" step="0.05" placeholder="第二个点 X"></label><label>Y2<input id="obstacleY2" type="number" min="-10" max="10" step="0.05" placeholder="第二个点 Y"></label></div><div class="row"><button id="addObstacleCoordinates">按坐标添加障碍</button><button id="updateObstacleCoordinates" class="mutedbtn">更新所选障碍</button></div><p class="tip">矩形填写任意两个对角，顺序可反；长宽均至少0.05米。墙段支持任意方向，长度至少0.05米，厚度0.02～2米。坐标可为0，范围±10米。</p></fieldset>
<p id="obstacleFormStatus" class="tip" role="status" aria-live="polite"></p><p class="tip" id="obstacleInfo"></p><div class="row"><label>已添加障碍（选择后载入坐标）<select id="obstacleList"><option value="">暂无障碍</option></select></label><button id="removeObstacle" class="mutedbtn">删除所选障碍</button></div>
<div class="row"><button id="cancelObstacle" class="mutedbtn">取消本次绘制</button><button id="clearObstacles" class="mutedbtn">清空障碍</button><button id="obstaclesDone">下一步：终点与路线</button></div>
<div class="row"><label>车体包络半径 / 米<input id="obstacleRadius" type="number" value="0.15" min="0.08" max="1" step="0.01"></label><label>额外余量 / 米<input id="obstacleMargin" type="number" value="0.15" min="0.05" max="1" step="0.01"></label></div>
<p class="tip">默认半径0.15米和余量0.15米仅为待实测值；必须测量三轮整车包络（包括前支撑轮和外突件）后填写。红色为障碍，橙色为扩张后的保护区。归零或重启会清空旧障碍，请按新原点重设。</p></section>
<section id="routeEditor" class="mapPanel" role="tabpanel" aria-labelledby="routeTab"><h2>终点与路线</h2><p class="tip">在下方共享地图单击选择终点，或输入终点坐标。黄色虚线是预览；只有点击“确认前往目标点”才执行。</p>
<div class="row goalInputs" style="margin-top:12px"><label>目标 X / 米<input id="goalX" type="number" value="5" min="-10" max="10" step="0.05"></label><label>目标 Y / 米<input id="goalY" type="number" value="0" min="-10" max="10" step="0.05"></label><label>速度上限 mm/s（35–220）<input id="goalSpeed" type="number" value="40" min="35" max="220" step="5"></label></div>
<div class="row" style="margin-top:12px"><label>到点走法<select id="pathMode" style="display:block;width:100%;padding:12px;background:#0a1b2c;color:white;border:1px solid #415971;border-radius:9px"><option value="direct">直达目标</option><option value="avoid">自动规划绕开障碍</option><option value="xy">先沿X，再沿Y</option><option value="yx">先沿Y，再沿X</option><option value="custom">自定义途经点</option></select></label></div>
<div id="waypointEditor" hidden style="margin-top:12px"><label for="waypointText">途经点（按顺序，每行 X,Y，单位米；最后自动到上方目标点）</label><textarea id="waypointText" rows="4" spellcheck="false" placeholder="例如：&#10;5,0&#10;5,5" style="display:block;width:100%;margin-top:8px;background:#0a1b2c;color:white;border:1px solid #415971;border-radius:9px;padding:12px;font:inherit"></textarea><div class="row" style="margin-top:8px"><button id="addWaypoint">把所选坐标加入途经点</button><button id="useLastWaypoint" class="mutedbtn">用列表末点作为终点</button><button id="clearWaypoints" class="mutedbtn">清空途经点</button></div><p class="tip">可以点击地图选一个拐点，再加入列表；依次添加后，最后点击或填写真正的目标点。也可以直接编辑列表；列表已经包含终点时，点击“用列表末点作为终点”，避免末尾接上旧目标。</p></div>
<p id="pathPreview" class="tip" aria-live="polite"></p>
<div class="row" style="margin-top:12px"><button id="planAvoid">预览自动绕障路线</button><button id="gotoBtn" disabled>确认前往目标点</button></div></section>
<div id="mapModeText" class="modeBar" aria-live="polite">终点与路线 · 点击地图选择终点</div><style>#mapSvg *{pointer-events:none}</style><svg id="mapSvg" viewBox="0 0 640 440" role="img" aria-label="共享地图：二维坐标、障碍、估算车位与目标点" style="display:block;width:100%;height:auto;background:#081725;border:1px solid #314d64;border-radius:12px;touch-action:manipulation;cursor:crosshair"></svg><p id="mapInputHint" class="tip" role="status" aria-live="polite"></p>
<div class="row" style="margin-top:12px"><button id="mapStop">取消导航 / 停车</button><button id="clearTrack" class="mutedbtn">清空显示轨迹</button></div>
<div class="row" style="margin-top:12px"><label>地图纵向半幅<select id="mapSpan"><option value="1000">±1 米</option><option value="2500">±2.5 米</option><option value="5000" selected>±5 米</option><option value="10000">±10 米</option></select></label><strong id="navState">等待状态</strong><span id="goalInfo" class="sub"></span></div>
<p class="tip">两页共用同一张地图，切页会取消未完成的两点绘制；已添加障碍会保留。最多12个障碍、12个路线点（含终点），每段最长5米，合计最长30米，坐标范围±10米。必须停车并显式重置原点；原点是该次归零车位，+X为当时车头、+Y为当时左侧；图上X向右、Y向上。所有路线在纠偏预算耗尽时失败并停车，不按剩余轮程冒充到点。自动绕障只按手绘地图检查整条折线，并非实时传感器避障；请先目视核对实地和路线；FG计距与IMU航向仍会因打滑产生误差，手动遥控请目视看车。</p></div>

<div class="card"><h2>实时操纵</h2><div class="padArea"><div id="pad" class="pad" role="application" aria-label="按住摇杆驾驶"><div class="crossV"></div><div class="crossH"></div><div class="knob" id="knob"></div></div>
<div><div class="dpad"><button class="up" data-control="up">▲</button><button class="left" data-control="left">◀</button><button class="center mutedbtn" id="stopSmall">■</button><button class="right" data-control="right">▶</button><button class="down" data-control="down">▼</button></div><p class="tip" style="text-align:center">W A S D / 方向键<br>松开即刹车 · 断联自动停车</p></div></div>
<div style="margin-top:20px"><div class="row"><label for="speed">速度上限</label><strong id="speedText" style="text-align:right">20%</strong></div><input id="speed" type="range" min="15" max="100" value="20"></div>
<button id="stop" class="danger bigstop">正常停车 · 不锁定</button><div class="row" style="margin-top:10px"><button id="estop" class="danger">急停锁定（需手动解除）</button><button id="clear" class="mutedbtn" hidden>检查后清除故障</button></div><p class="tip">摇杆可组合前后和转向；角速度单位°/s，底层将转向轮速限制在60mm/s内。松手、失焦或断联停车；解除急停不会续跑。</p><div id="note" role="status"></div></div>
<div class="card"><h2>实时状态</h2><p id="imuState" class="tip" role="status">IMU：等待设备；上电后请水平静置</p><div class="stats"><div><small>工作模式</small><strong id="mode">--</strong></div><div><small>故障</small><strong id="fault">--</strong></div><div><small>X / 米</small><strong id="x">--</strong></div><div><small>Y / 米</small><strong id="y">--</strong></div><div><small>航向 / °</small><strong id="yaw">--</strong></div><div><small>左轮 / mm/s</small><strong id="l">--</strong></div><div><small>右轮 / mm/s</small><strong id="r">--</strong></div><div><small>FG 累计</small><strong id="fg">--</strong></div></div><p class="tip" id="headingStatus">角度纠偏：停稳对准目标3°；偏差超过10°持续200ms才触发纠偏，回到8°内撤销触发，≥20°立即刹车。第三次纠偏成功仍可继续；预算耗尽仍未对准时失败并停车。</p><p class="tip" id="faultDetail">等待设备故障状态</p><p class="tip" id="stopSource">最近停车来源：等待状态</p><p class="tip" id="faultSource">故障来源：等待状态</p><p class="tip" id="motorStartStatus">启转首脉冲：等待状态（约50ms采样分辨率）</p><p class="tip" id="wheelPidState">两轮PID：等待设备参数</p><p class="tip" id="counts">M1 -- · M2 --</p><p class="tip">三轮底盘：左驱动M2、右驱动M1，支撑轮无驱动输出。沿用68mm轮径、180 FG及0.70距离系数，均须按新底盘实测标定；位置由FG与IMU估算，会累积打滑误差。</p><button class="mutedbtn" id="imuReconnect" disabled>静止时重试IMU查询</button><p class="tip" id="imuLinkHelp">上电后持续查询版本；恢复后需水平静置，重新确认状态。</p><button class="mutedbtn" id="zero">静止时重置坐标原点</button></div>

</div></main>
<script>
// Local files default to animation-only demo; no request reaches a vehicle.
const MAP_DEMO=typeof location!=='undefined'&&(location.protocol==='file:'||new URLSearchParams(location.search).get('demo')==='1');
if(MAP_DEMO){
 const demo={poseFrame:1,poseZeroed:false,snapshotAgeMs:0,controlMode:'three-wheel-scan-lite-v4',driveTurnUnits:'deg/s',maxTurnWheelSpeed:60,navGuarded:false,obstacles:[],navPoints:[],bootSession:'00000000000000d1',webEpoch:2,stopSource:'boot',faultSource:'none',stage:'MONITOR',armed:0,active:0,rxForward:0,ready:true,uart:false,ioFault:false,estop:false,mode:'idle',fault:'none',x:0,y:0,yaw:0,left:0,right:0,count:[0,0],wheelSpeed:[0,0],duty:[0,0],maxLinear:220,maxAngular:160,minArcRadius:141,calibrated:false,nav:'idle',navActive:false,navReason:'none',goalX:0,goalY:0,goalError:0,navPoint:0,navCount:0,finalX:0,finalY:0};
 let plan=null,lastDemoTime=Date.now(),demoPathMm=0,demoLeaseToken=null,demoLastTouch=0;
 const wrap=a=>((a+540)%360)-180;
 function demoStop(reason,source='web'){plan=null;demoLeaseToken=null;demo.mode='idle';demo.navActive=false;demo.left=demo.right=0;demo.nav=reason;demo.navReason=reason==='arrived-estimate'?'IDEAL_ANIMATION':'STOPPED';demo.stopSource=source;demo.webEpoch++}
 function demoLeg(){const p=plan.points[plan.index];demo.goalX=p.x;demo.goalY=p.y;demo.navPoint=plan.index+1;demo.nav='turning';demo.mode='goto-turn';demo.left=demo.right=0}
 function demoArrive(){
  demo.x=demo.goalX;demo.y=demo.goalY;demo.left=demo.right=0;
  if(plan.index+1<plan.points.length){plan.index++;plan.nextLeg=true;plan.settledAt=Date.now();demo.nav='settling';demo.mode='goto-settle'}
  else demoStop('arrived-estimate','completed');
 }
 setInterval(()=>{
  const now=Date.now(),dt=Math.max(0,Math.min(.1,(now-lastDemoTime)/1000));lastDemoTime=now;if(!plan)return;
  if(now-demoLastTouch>2000){demoStop('cancelled','page-lost');return;}
  const dx=demo.goalX-demo.x,dy=demo.goalY-demo.y,dist=Math.hypot(dx,dy);
  if(demo.nav==='turning'){
   const error=wrap(Math.atan2(dy,dx)*180/Math.PI-demo.yaw),step=90*dt;
   if(Math.abs(error)<=step){demo.yaw=wrap(demo.yaw+error);demo.nav='settling';plan.settledAt=now;demo.mode='goto-settle'}
   else demo.yaw=wrap(demo.yaw+Math.sign(error)*step);
  }else if(demo.nav==='settling'){
   if(now-plan.settledAt>=200){if(plan.nextLeg){plan.nextLeg=false;demoLeg()}else{demo.nav='driving';demo.mode='goto-drive'}}
  }else if(demo.nav==='driving'){
   if(dist<.01){demoArrive();return}
   const step=Math.min(dist,plan.speed*dt);demo.x+=dx/dist*step;demo.y+=dy/dist*step;demoPathMm+=step;demo.left=demo.right=plan.speed;
   if(dist<=step)demoArrive();
  }
  demo.goalError=Math.hypot(demo.goalX-demo.x,demo.goalY-demo.y);demo.count=Array(2).fill(Math.floor(demoPathMm/1.1868));demo.wheelSpeed=Array(2).fill(demo.left);
 },50);
 window.fetch=async(url,options={})=>{
  let code=200,error='';const path=String(url).split('?')[0],p=new URLSearchParams(options.body||'');
  if(path==='/api/status'){const renew=options.method==='POST'&&p.get('bootSession')===demo.bootSession&&Number(p.get('epoch'))===demo.webEpoch&&demoLeaseToken&&p.get('leaseToken')===demoLeaseToken;if(renew)demoLastTouch=Date.now();return {ok:true,status:200,json:async()=>({...JSON.parse(JSON.stringify(demo)),leaseRenewed:Boolean(renew)})};}
  if(path==='/api/stop')demoStop('cancelled');
  else if(path==='/api/estop'){demoStop('cancelled');demo.estop=true;demo.fault='e-stop';demo.faultSource='web'}
  else if(p.get('bootSession')!==demo.bootSession||Number(p.get('epoch'))!==demo.webEpoch){code=409;error='请等待状态同步'}
  else if(path==='/api/touch'){if(!demoLeaseToken||p.get('leaseToken')!==demoLeaseToken){code=409;error='页面授权已失效'}else demoLastTouch=Date.now()}
  else if(path==='/api/clear'){demoStop('cancelled','clear');demo.estop=false;demo.fault='none';demo.faultSource='none'}
  else if(path==='/api/zero'&&!demo.navActive){demo.x=demo.y=demo.yaw=0;demo.poseZeroed=true;demo.poseFrame++;demo.webEpoch++}
  else if(path==='/api/path'||path==='/api/avoid'||path==='/api/goto'){
   try{
    if(demo.estop||demo.navActive)throw Error('请先停车并解除急停');
    if(!demo.poseZeroed||Number(p.get('frame'))!==demo.poseFrame)throw Error('请先确认当前原点');
    const speed=Number(p.get('speed'));if(!Number.isFinite(speed)||speed<35||speed>220)throw Error('坐标导航速度须为35–220mm/s');
    const goal=path==='/api/goto'?{x:Number(p.get('x')),y:Number(p.get('y'))}:{x:demo.x,y:demo.y};
    let draft;
    // The path wire's last point is already its final target, not current car position.
    if(path==='/api/path'||path==='/api/avoid'){
     const lines=p.get('points').split(';');const last=lines.pop().split(',').map(Number);
     draft=buildCoordinatePath(demo,{x:last[0],y:last[1]},'custom',lines.map(row=>row.split(',').map(n=>Number(n)/1000).join(',')).join('\n'));
    }else draft=buildCoordinatePath(demo,goal,'direct');
    demo.navGuarded=path==='/api/avoid';demo.obstacles=[];
    if(demo.navGuarded){
     if(Number(p.get('frame'))!==demo.poseFrame)throw Error('原点已变化');
     const map=ObstaclePlanner.parse(p.get('map'));ObstaclePlanner.assertPath(map,demo,draft.points);
     demo.obstacleRadius=map.radius;demo.obstacleMargin=map.margin;
     demo.obstacles=map.items.map(o=>[o.kind,o.x1,o.y1,o.x2,o.y2,o.width]);
    }
    demo.navPoints=draft.points.map(o=>[o.x,o.y]);
    const last=draft.points[draft.points.length-1];demo.finalX=last.x;demo.finalY=last.y;demo.navCount=draft.points.length;
    demo.navActive=true;demo.navReason='none';demoLeaseToken='00000000000000a1';demoLastTouch=Date.now();
    plan={points:draft.points,speed,index:0,nextLeg:false,settledAt:0};demoLeg();
   }catch(e){code=409;error=e.message}
  }else{code=409;error='离线演示仅支持坐标路线、停车、急停和归零'}
  return {ok:code===200,status:code,json:async()=>({ok:code===200,error,epoch:demo.webEpoch,bootSession:demo.bootSession,...(['path','goto','avoid'].some(k=>path==='/api/'+k)&&code===200?{leaseToken:demoLeaseToken}:{})})};
 };
}
'use strict';
const $=id=>document.getElementById(id),keys=new Set(),buttonPointers=new Map(),pendingMotions=new Set(),seenSessions=new Set();
let vx=0,vy=0,stickDown=false,activePointer=null,sendBusy=false,pollBusy=false,actionBusy=false;
let bootSession=null,webEpoch=null,sessionGeneration=0,controlGeneration=0,abandonedThrough=-1,leaseToken='',ownedTask=null,confirmedTask=null;
let motionMayBeActive=false,stopIssued=false,lastGoodStatusAt=NaN,maxLinear=220,maxAngular=160;
const HTTP_TIMEOUT_MS=1000,STATUS_TIMEOUT_MS=850,STATUS_FRESH_MS=850,STATUS_MAX_AGE_MS=500;
const clockNow=()=>performance.now(),isEpoch=n=>Number.isInteger(n)&&n>=0&&n<=0xffffffff,isToken=s=>typeof s==='string'&&/^[0-9a-f]{16}$/.test(s);
const note=t=>{$('note').textContent=t};
function hasFreshStatus(){return Number.isFinite(lastGoodStatusAt)&&clockNow()-lastGoodStatusAt>=0&&clockNow()-lastGoodStatusAt<STATUS_FRESH_MS}
function hasPendingMotion(){return [...pendingMotions].some(r=>r.session===sessionGeneration&&r.generation===controlGeneration)}
function epochAhead(next,old){if(!isEpoch(next)||!isEpoch(old))return false;const delta=(next-old)>>>0;return delta>0&&delta<0x80000000}
function refreshMotionFlag(){motionMayBeActive=Boolean(ownedTask||leaseToken||hasPendingMotion())}
function clearLeaseLocal(){leaseToken='';ownedTask=null;++controlGeneration;refreshMotionFlag()}
function abandonLocal(message){abandonedThrough=Math.max(abandonedThrough,controlGeneration);resetInputs();clearLeaseLocal();confirmedTask=null;stopIssued=true;if(message)note(message)}
function invalidateStatus(){lastGoodStatusAt=NaN;$('connected').textContent='离线 / 状态未确认';$('imuState').textContent='连接中断，当前姿态已撤下';$('imuState').classList.add('error');$('zero').disabled=true;$('imuReconnect').disabled=true;for(const b of document.querySelectorAll('[data-control]'))b.disabled=true;$('pad').setAttribute('aria-disabled','true');for(const id of ['mode','x','y','yaw','l','r','fg'])$(id).textContent='--';$('counts').textContent='两轮反馈状态已过期';if(typeof drawMap==='function')drawMap()}
async function fetchJsonBounded(url,options={},timeout=HTTP_TIMEOUT_MS){
 const controller=new AbortController();let timer;
 try{return await Promise.race([fetch(url,{...options,cache:'no-store',signal:controller.signal}).then(async res=>({res,j:await res.json()})),new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();const error=Error('请求超时，结果未确认');error.transportFailure=true;reject(error)},timeout)})])}
 catch(e){if(e.status===undefined)e.transportFailure=true;throw e}finally{clearTimeout(timer)}
}
function taskIdentity(path,params){
 const points=path==='goto'?[[Number(params.x),Number(params.y)]]:String(params.points||'').split(';').map(row=>row.split(',').map(Number));
 return {kind:path,boot:bootSession,frame:Number(params.frame),requestEpoch:webEpoch,points,plan:String(params.plan||''),guarded:path==='avoid',map:String(params.map||'')};
}
function near(a,b){return Number.isFinite(a)&&Number.isFinite(b)&&Math.abs(a-b)<.01}
function sameTask(s,t){
 if(!s||!t||s.bootSession!==t.boot||s.poseFrame!==t.frame)return false;
 if(t.kind==='route')return typeof s.routePlan==='string'&&s.routePlan===t.plan;
 const last=t.points[t.points.length-1];if(!last||!near(Number(s.finalX),last[0])||!near(Number(s.finalY),last[1]))return false;
 // Full ordered points distinguish different paths ending at the same target.
 const points=s.navPoints;if(!Array.isArray(points)||points.length!==t.points.length||!points.every((p,i)=>Array.isArray(p)&&near(p[0],t.points[i][0])&&near(p[1],t.points[i][1])))return false;
 if(Boolean(s.navGuarded)!==t.guarded)return false;
 if(t.guarded){try{const map=ObstaclePlanner.parse(t.map);if(!near(s.obstacleRadius,map.radius)||!near(s.obstacleMargin,map.margin)||JSON.stringify(s.obstacles)!==JSON.stringify(map.items.map(o=>[o.kind,o.x1,o.y1,o.x2,o.y2,o.width])))return false}catch(e){return false}}
 return true;
}
function taskTerminal(s,t){
 if(!sameTask(s,t)||s.webEpoch!==t.terminalEpoch||s.mode!=='idle'||s.navActive||s.routeActive)return false;
 if(t.kind==='route')return ['completed','cancelled','failed'].includes(s.route)&&(s.route!=='completed'||s.fault==='none');
 return ['arrived-estimate','cancelled','failed'].includes(s.nav)&&(s.nav!=='arrived-estimate'||s.fault==='none');
}
function finishOwned(s,t){confirmedTask={...t};ownedTask=null;leaseToken='';++controlGeneration;refreshMotionFlag();stopIssued=true;note(s.fault!=='none'?'任务保护停车，请检查故障。':s.nav==='arrived-estimate'?'轮速与IMU估计已到目标附近，请现场确认位置。':'本页任务已结束；重新运行需要再次确认。')}
function acceptStatus(s,renewing=false,renewToken='',renewGeneration=controlGeneration,roundTrip=0){
 if(!s||!isToken(s.bootSession)||!isEpoch(s.webEpoch)||!Number.isFinite(s.snapshotAgeMs)||s.snapshotAgeMs<0||s.snapshotAgeMs>STATUS_MAX_AGE_MS)throw Error('设备状态过期或会话无效');
 if(s.bootSession!==bootSession){
  if(seenSessions.has(s.bootSession))return false;
  const restarting=bootSession!==null;seenSessions.add(s.bootSession);abandonLocal(restarting?'设备重启，旧任务已撤销；请停车后重新确认原点。':'');bootSession=s.bootSession;webEpoch=s.webEpoch;++sessionGeneration;
 }else if(epochAhead(webEpoch,s.webEpoch))return false;
 if(ownedTask){
  const t=ownedTask,initial=s.poseZeroed===true&&!t.seenActive&&!s.navActive&&!s.routeActive&&s.mode==='idle'&&s.webEpoch===t.ackEpoch&&s.poseFrame===t.frame&&clockNow()-t.acceptedAt<=500;
  if(taskTerminal(s,t))finishOwned(s,t);
  else if(!initial){
   if(s.webEpoch!==t.ackEpoch||!s.poseZeroed||!sameTask(s,t))abandonLocal('设备原点、目标或控制会话已变化，本页已退出旧任务；未停止新任务。');
   else if(renewing&&renewGeneration===controlGeneration&&renewToken===leaseToken&&s.leaseRenewed!==true)releaseForInactivity('本页续租失效，已请求停车。');
  }
  if(ownedTask&&(s.navActive||s.routeActive))ownedTask.seenActive=true;
 }else if(leaseToken&&(s.webEpoch!==webEpoch||(renewing&&renewGeneration===controlGeneration&&renewToken===leaseToken&&(s.leaseRenewed!==true||(s.mode==='idle'&&!s.consoleMode)))))abandonLocal('驾驶控制已结束或被替换；请松手后重新操作。');
 if(s.webEpoch!==webEpoch){webEpoch=s.webEpoch;if(!ownedTask&&!leaseToken&&hasPendingMotion())abandonLocal('控制会话已变化，旧请求不再接管。')}
 lastGoodStatusAt=clockNow()-s.snapshotAgeMs-Math.max(0,roundTrip);mapStatus=s;
 if(s.fault!=='none'&&(ownedTask||leaseToken))releaseForInactivity('设备已保护停车，请检查故障。');
 maxLinear=Math.min(220,Number(s.maxLinear)||220);maxAngular=Number(s.maxAngular)||160;
 renderMapStatus(s);renderStatus(s);return true;
}
async function post(path,params={}){
 const automatic=['goto','path','avoid','route'].includes(path),motion=automatic||path==='drive',safety=['stop','estop'].includes(path);
 if(!safety){
  if(!hasFreshStatus()||!bootSession||!isEpoch(webEpoch))throw Error('请等待设备状态同步');
  if(motion){
   if(!mapStatus?.consoleMode)throw Error('先停车并点击接管完整上位机');
   if(document.hidden)throw Error('请保持页面在前台');
   if(!MAP_DEMO&&(mapStatus?.controlMode!=='three-wheel-scan-lite-v4'||mapStatus?.driveTurnUnits!=='deg/s'))throw Error('固件接口不是R24三轮上位机，请核对版本');
   if(mapStatus.fault!=='none'||!mapStatus.ready||mapStatus.stage!=='MONITOR')throw Error(faultExplanation(mapStatus));
   if(!MAP_DEMO&&(!mapStatus.imuReady||!mapStatus.imuUsable))throw Error('真实IMU尚未就绪，请保持静止');
   if(automatic){
    if(ownedTask||leaseToken||hasPendingMotion()||mapStatus.mode!=='idle'||mapStatus.navActive||mapStatus.routeActive)throw Error('请先停车再提交新任务');
    if(!mapStatus.poseZeroed||!Number.isInteger(mapStatus.poseFrame)||Number(params.frame)!==mapStatus.poseFrame)throw Error('请停车并显式重置原点，再核对路线');
   }else if(ownedTask||mapStatus.navActive||mapStatus.routeActive||(mapStatus.mode!=='idle'&&!leaseToken))throw Error('设备有其他任务，请先停车');
  }
  params={...params,bootSession,epoch:webEpoch,leaseToken:leaseToken||''};
 }
 const body=new URLSearchParams(params);if(body.toString().length>1536)throw Error('地图和路线数据过长，请减少障碍或途经点');
 if(safety){resetInputs();confirmedTask=null;clearLeaseLocal();stopIssued=true;motionMayBeActive=false;}
 const request={session:sessionGeneration,generation:controlGeneration,boot:bootSession,epoch:webEpoch,possibleBefore:motionMayBeActive};
 const target=automatic?taskIdentity(path,params):null;
 if(motion){pendingMotions.add(request);motionMayBeActive=true;stopIssued=false;}
 try{
  const {res,j}=await fetchJsonBounded('/api/'+path,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body,keepalive:safety});
  const current=request.session===sessionGeneration&&request.generation===controlGeneration&&request.boot===bootSession;
  if(!safety&&!current){
   // Only an unresolved request from this same control generation can need a
   // late STOP. A newly observed owner/boot/epoch must never be stopped here.
   if(motion&&res.ok&&j.ok&&request.generation>abandonedThrough&&request.boot===bootSession&&webEpoch===request.epoch)void post('stop').catch(()=>{});
   const e=Error('旧响应已忽略，不会恢复动作');e.cancelled=true;throw e;
  }
  if(!res.ok||j.ok===false){const e=Error(j.error||'HTTP '+res.status);e.status=res.status;
   if(motion&&![400,401,403,409].includes(res.status))e.transportFailure=true;
   if(isEpoch(j.epoch)&&j.bootSession===bootSession&&j.epoch!==request.epoch)abandonLocal('设备控制会话已变化，拒绝旧操作；未接管其他任务。');throw e;
  }
  if(!safety&&j.bootSession!==request.boot){abandonLocal('启动会话已变化，本页不接管新会话。');throw Error('响应会话未确认')}
  if(!safety&&!isEpoch(j.epoch)){const e=Error('执行响应缺少有效控制序号');e.transportFailure=motion;throw e}
  if(motion){
   if(!j.leaseToken&&automatic){
    if(j.epoch!==((request.epoch+1)>>>0)){if(j.epoch===request.epoch){const e=Error('任务未返回有效授权或终态序号');e.transportFailure=true;throw e}abandonLocal('即时任务控制会话未确认；未重发任务。');throw Error('即时任务响应无效')}
    target.terminalEpoch=j.epoch;const until=clockNow()+500;
    for(;;){
     const remaining=until-clockNow();if(remaining<=0){abandonLocal('本次到点状态未确认；未重发或接管任务。');throw Error('到点状态未确认')}
     const {res:statusRes,j:s}=await fetchJsonBounded('/api/status',{},Math.max(1,remaining));
     if(request.generation!==controlGeneration||request.session!==sessionGeneration)throw Object.assign(Error('旧即时任务已取消'),{cancelled:true});
     if(!statusRes.ok||s.bootSession!==request.boot||s.poseFrame!==target.frame||![request.epoch,j.epoch].includes(s.webEpoch)){abandonLocal('会话或原点已变化，本页不确认旧任务。');throw Error('即时结果归属不匹配')}
     if(s.snapshotAgeMs>=0&&s.snapshotAgeMs<=500&&s.fault==='none'&&taskTerminal(s,target)){acceptStatus(s);confirmedTask={...target};note('估计已在目标附近，未启动新行程；请现场确认。');return j}
     await new Promise(resolve=>setTimeout(resolve,25));
    }
   }
   if(j.epoch!==request.epoch||webEpoch!==request.epoch){abandonLocal('动作授权已变化，本页未接管其他任务。');throw Error('动作授权未确认')}
   if(!isToken(j.leaseToken)){const e=Error('动作未返回有效私有授权');e.transportFailure=true;throw e}
   leaseToken=j.leaseToken;
   if(automatic){ownedTask={...target,ackEpoch:j.epoch,terminalEpoch:(j.epoch+1)>>>0,acceptedAt:clockNow(),seenActive:false};confirmedTask=null;}
  }else if(isEpoch(j.epoch)&&j.bootSession===bootSession){webEpoch=j.epoch;if(!safety&&path!=='status'){resetInputs();clearLeaseLocal()}}
  return j;
 }catch(error){
  if(motion&&request.generation===controlGeneration&&request.session===sessionGeneration&&error.transportFailure){invalidateStatus();releaseForInactivity('动作执行未确认，已请求停车；不会自动重试。')}
  throw error;
 }finally{pendingMotions.delete(request);refreshMotionFlag()}
}
const throttle=()=>Number($('speed').value)/100;
function updateStick(x,y){vx=Math.max(-1,Math.min(1,x));vy=Math.max(-1,Math.min(1,y));$('knob').style.left=(50+vx*34)+'%';$('knob').style.top=(50+vy*34)+'%'}
function keyAxis(){const has=(...k)=>k.some(x=>keys.has(x));return {x:(has('ArrowRight','d','right')?1:0)-(has('ArrowLeft','a','left')?1:0),y:(has('ArrowDown','s','down')?1:0)-(has('ArrowUp','w','up')?1:0)}}
function desired(){const a=stickDown?{x:vx,y:vy}:keyAxis();return {v:Math.round(-a.y*throttle()*maxLinear),w:Math.round(-a.x*throttle()*maxAngular),active:stickDown||keys.size>0}}
function manualReady(){const s=mapStatus;return Boolean(s?.consoleMode)&&hasFreshStatus()&&!actionBusy&&!discreteBusy&&!mapSubmitBusy&&!ownedTask&&s&&s.ready&&s.fault==='none'&&s.stage==='MONITOR'&&(!s.navActive&&!s.routeActive)&&(s.mode==='idle'||Boolean(leaseToken))&&(MAP_DEMO||(s.imuReady&&s.imuUsable&&s.controlMode==='three-wheel-scan-lite-v4'&&s.driveTurnUnits==='deg/s'))}
async function sendDrive(){const d=desired();if(!d.active||sendBusy||pollBusy)return;if(!manualReady()){resetInputs();note('请等待设备、IMU及停车状态就绪');return}sendBusy=true;try{await post('drive',{v:d.v,w:d.w})}catch(e){resetInputs();if(leaseToken)releaseForInactivity('驾驶状态未确认，已请求停车');note(e.message)}finally{sendBusy=false}}
function resetInputs(){keys.clear();buttonPointers.clear();stickDown=false;activePointer=null;updateStick(0,0);$('pad').classList.remove('padActive');for(const b of document.querySelectorAll('[data-control]'))b.classList.remove('pressed')}
function hasMotionToStop(){return !stopIssued&&(desired().active||hasPendingMotion()||motionMayBeActive||ownedTask||leaseToken)}
function releaseForInactivity(message='页面失焦或隐藏，已请求停车；不会自动恢复。'){const needed=hasMotionToStop();resetInputs();if(needed){note(message);void post('stop').catch(()=>note('停车请求未确认，请现场检查；等待断联保护。'))}else clearLeaseLocal()}
async function stop(){resetInputs();try{await post('stop');note('已请求停车，请确认实车已停')}catch(e){note('停车请求未确认，请现场检查；'+e.message)}}
const pad=$('pad');
function touchXY(e){const r=pad.getBoundingClientRect(),radius=r.width*.35;let x=(e.clientX-r.left-r.width/2)/radius,y=(e.clientY-r.top-r.height/2)/radius;const n=Math.hypot(x,y);if(n>1){x/=n;y/=n}updateStick(x,y)}
pad.addEventListener('pointerdown',e=>{if(e.button!==0||stickDown||!manualReady())return;e.preventDefault();stickDown=true;activePointer=e.pointerId;pad.setPointerCapture(e.pointerId);pad.classList.add('padActive');touchXY(e);void sendDrive()});
pad.addEventListener('pointermove',e=>{if(stickDown&&e.pointerId===activePointer)touchXY(e)});
function stopRemote(){if(desired().active){void sendDrive();return}if(hasMotionToStop()){if(sendBusy||hasPendingMotion())void stop();else void post('drive',{v:0,w:0}).catch(()=>stop());}}
function padUp(e){if(activePointer!==e.pointerId)return;stickDown=false;activePointer=null;updateStick(0,0);pad.classList.remove('padActive');stopRemote()}
for(const event of ['pointerup','pointercancel','lostpointercapture'])pad.addEventListener(event,padUp);
const normalize=k=>k.length===1?k.toLowerCase():k;
addEventListener('keydown',e=>{if(e.code==='Space'&&!['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)){e.preventDefault();void stop();return}if(e.repeat||['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName))return;const k=normalize(e.key);if(['w','a','s','d','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(k)&&manualReady()){e.preventDefault();keys.add(k);void sendDrive()}});
addEventListener('keyup',e=>{const k=normalize(e.key);if(keys.delete(k)){e.preventDefault();stopRemote()}});
for(const b of document.querySelectorAll('[data-control]')){const k=b.dataset.control;const release=e=>{if(buttonPointers.get(k)!==e.pointerId)return;buttonPointers.delete(k);keys.delete(k);b.classList.remove('pressed');stopRemote()};b.addEventListener('pointerdown',e=>{if(e.button!==0||!manualReady()||buttonPointers.has(k))return;e.preventDefault();buttonPointers.set(k,e.pointerId);b.setPointerCapture(e.pointerId);keys.add(k);b.classList.add('pressed');void sendDrive()});for(const event of ['pointerup','pointercancel','lostpointercapture'])b.addEventListener(event,release)}
$('stop').onclick=stop;$('stopSmall').onclick=stop;
$('estop').onclick=async()=>{try{await post('estop');note('已请求急停锁定，检查后手动清除')}catch(e){note('急停未确认，请现场检查；'+e.message)}};
$('clear').onclick=async()=>{if($('clear').disabled)return;actionBusy=true;resetInputs();try{await post('clear');note('故障清除请求已接受，不会恢复旧任务')}catch(e){note(e.message)}finally{actionBusy=false}};
$('speed').oninput=()=>{$('speedText').textContent=$('speed').value+'%'};
addEventListener('blur',()=>releaseForInactivity());document.addEventListener('visibilitychange',()=>{if(document.hidden)releaseForInactivity()});addEventListener('pagehide',()=>releaseForInactivity());
const faultLabels={'none':'无故障','e-stop':'急停锁定','io-fault':'电机输出硬件故障','imu-failed':'IMU保护停车','encoder-stall':'轮速反馈缺失 / 堵转','motion-response':'转向响应异常','navigation-failed':'导航保护停车','route-failed':'路线保护停车','motion-timeout':'动作超时'};
const sourceLabels={'none':'无','web':'网页停车','boot':'上电停车','manual-timeout':'驾驶指令超时','page-lost':'网页断联','completed':'动作完成','route-completed':'路线完成','clear':'清除故障','control':'控制保护','fg-missing':'FG反馈缺失','goal-no-progress':'没有接近目标','recovery-not-converged':'纠偏未收敛','pwm-write':'PWM输出故障','fg-isr-init':'FG中断初始化失败'};
const imuReasons={'ready':'姿态已就绪','warming':'静止暖机中','keep-still':'请保持静止','waiting-version':'等待版本回复','no-fresh-angle':'没有新鲜姿态','data-delayed':'数据延迟','imu-data-lost':'姿态丢失','unsupported-version':'版本未验证','mounting-tilted':'安装倾斜','angle-jump':'角度突变','invalid-angle':'角度异常'};
function finite(v,d=0){return Number.isFinite(v)?v.toFixed(d):'--'}
function faultExplanation(s){if(!s)return '等待设备状态';if(s.ioFault||s.fault==='io-fault')return '电机硬件输出故障，请排查硬件后重启';if(s.fault&&s.fault!=='none')return (faultLabels[s.fault]||s.fault)+' · '+(s.navReason||s.routeReason||s.faultSource||'请现场检查');return s.ready?'无故障；请确认停车与实地路线':'设备尚未就绪'}
function renderStatus(s){
 $('connected').textContent=MAP_DEMO?'离线演示':'已连接';$('mode').textContent=s.mode||'--';$('fault').textContent=faultLabels[s.fault]||s.fault;$('fault').className=s.fault==='none'?'':'error';
 $('x').textContent=s.poseZeroed?finite(s.x/1000,2):'未归零';$('y').textContent=s.poseZeroed?finite(s.y/1000,2):'未归零';$('yaw').textContent=s.poseZeroed?finite(s.yaw,1):'--';$('l').textContent=finite(s.left);$('r').textContent=finite(s.right);
 $('fg').textContent=Array.isArray(s.count)?s.count.slice(0,2).reduce((a,b)=>a+b,0):'--';$('counts').textContent=[0,1].map(i=>`M${i+1} FG ${s.count?.[i]??'--'} / ${finite(s.wheelSpeed?.[i])}mm/s · ${finite(s.duty?.[i],1)}%`).join(' · ');
 $('motorStartStatus').textContent='启转至首FG：'+[0,1].map(i=>`M${i+1} ${s.startDelayMs?.[i]>=0?s.startDelayMs[i]+'ms':'未捕获'}`).join(' · ')+'（约50ms采样分辨率）';
 $('wheelPidState').textContent='两轮PID：'+(s.wheelPidLoaded?'已读取保存参数':'设备当前参数')+' · '+[0,1].map(i=>`M${i+1} ${Array.isArray(s.wheelPid?.[i])?s.wheelPid[i].join('/'):'--'}`).join(' · ');
 $('faultDetail').textContent=faultExplanation(s)+(s.feedbackMotor?` · M${s.feedbackMotor} 目标${finite(s.feedbackTarget,1)}mm/s / 输出${finite(s.feedbackDuty,1)}% / 无FG ${s.feedbackSilenceMs??'--'}ms`:'');$('stopSource').textContent='最近停车来源：'+(sourceLabels[s.stopSource]||s.stopSource||'--');$('faultSource').textContent='故障来源：'+(sourceLabels[s.faultSource]||s.faultSource||'--');
 $('clear').hidden=s.fault==='none'&&!s.estop;$('clear').disabled=Boolean(s.ioFault)||s.mode!=='idle'||actionBusy||hasPendingMotion();
 const current=hasFreshStatus()&&s.imuReady&&s.imuUsable&&Number.isFinite(s.imuAgeMs)&&s.imuAgeMs>=0&&s.imuAgeMs<=180;
 const angles=current&&[s.imuYaw,s.imuPitch,s.imuRoll].every(Number.isFinite)?` · yaw ${finite(s.imuYaw,2)}° / pitch ${finite(s.imuPitch,1)}° / roll ${finite(s.imuRoll,1)}°`:' · 当前姿态未确认（已撤下旧角度）';
 $('imuState').textContent=MAP_DEMO?'离线动画，未连接真实陀螺仪':'IMU：'+(imuReasons[s.imuReason]||s.imuReason||'等待数据')+angles+` · 版本 ${s.imuVersion??'--'} / 年龄 ${s.imuAgeMs??'--'}ms / 收${s.imuRx??0}字节 / ${s.imuFrames??0}帧 / CRC错${s.imuCrc??0}`;$('imuState').className='tip'+(current||MAP_DEMO?'':' error');
 $('imuLinkHelp').textContent='UART2：模块TX→GPIO2，模块RX→GPIO1；3.3V供电、共地。重连会撤销旧原点，须静置暖机后重新归零。'+` · 复位${s.resetReason??'--'} / 循环最大间隔${s.loopMaxGapMs??'--'}ms / 日志丢弃${s.consoleDropped??0}`;
 const idle=s.mode==='idle'&&!s.navActive&&!s.routeActive&&!hasPendingMotion()&&!ownedTask&&!leaseToken&&!actionBusy&&!mapSubmitBusy;
 $('imuReconnect').disabled=MAP_DEMO||!hasFreshStatus()||!idle||s.imuCanReconnect!==true;$('zero').disabled=!hasFreshStatus()||!idle||s.fault!=='none'||(!MAP_DEMO&&!s.imuReady);
 $('mapSource').textContent=MAP_DEMO?'离线演示 · 理想动画':s.poseZeroed?'真实IMU＋FG估算 · frame '+s.poseFrame:'先停车并重置原点';
 const phases={'straight':'直行航向保持','turn':'转向','settling':'等待停稳','correction':'低速补转','line-follow':'沿线纠偏','recovery-brake':'偏航刹车','recovery-turn':'重新对准','position-settle':'到点复核','completed':'已结束','stopped':'已停车'};
 $('headingStatus').textContent='角度纠偏：'+(phases[s.headingPhase]||s.headingPhase||'待机')+(s.headingValid?` · 目标${finite(s.headingTarget,1)}° / 实际${finite(s.headingActual,1)}° / 偏差${finite(s.headingError,1)}°`:'')+` · 每段纠偏${s.pathRecoveries??0}/3；预算耗尽失败并停车，不按轮程冒充到点。`;
 if(s.nav==='arrived-estimate'&&!s.navActive)$('navState').textContent=taskTerminal(s,confirmedTask)?'本页任务估计到点，请现场确认':'设备报告估计到点（本页未确认归属）';
 for(const b of document.querySelectorAll('[data-control]'))b.disabled=!manualReady();pad.setAttribute('aria-disabled',String(!manualReady()));
}
async function poll(){
 if(pollBusy||sendBusy||hasPendingMotion()||actionBusy)return;pollBusy=true;const started=clockNow(),token=leaseToken,generation=controlGeneration,session=sessionGeneration,renewing=Boolean(token&&!document.hidden);
 try{const {res,j:s}=await fetchJsonBounded('/api/status',renewing?{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({bootSession,epoch:webEpoch,leaseToken:token})}:{},STATUS_TIMEOUT_MS);
  if(!res.ok||clockNow()-started>STATUS_TIMEOUT_MS)throw Error('状态超时');if(session!==sessionGeneration||generation!==controlGeneration)return;acceptStatus(s,renewing,token,generation,clockNow()-started);
 }catch(e){if(!hasFreshStatus()){releaseForInactivity('连接中断，已请求停车；不会自动恢复。');invalidateStatus()}}
 finally{pollBusy=false}
}
const ObstaclePlanner=(()=>{
 const LIMIT=10000,MAX=12,EPS=1,PAD=50;
 const sq=x=>x*x,dist=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y),inside=p=>[p.x,p.y].every(Number.isFinite)&&Math.abs(p.x)<=LIMIT&&Math.abs(p.y)<=LIMIT;
 function pointSegment2(p,a,b){const dx=b.x-a.x,dy=b.y-a.y,n=dx*dx+dy*dy,t=n?Math.min(1,Math.max(0,((p.x-a.x)*dx+(p.y-a.y)*dy)/n)):0;return sq(p.x-a.x-t*dx)+sq(p.y-a.y-t*dy)}
 const cross=(a,b)=>a.x*b.y-a.y*b.x;
 function segmentDistance2(a,b,c,d){
  const r={x:b.x-a.x,y:b.y-a.y},s={x:d.x-c.x,y:d.y-c.y},den=cross(r,s),q={x:c.x-a.x,y:c.y-a.y};
  if(Math.abs(den)>1e-5){const t=cross(q,s)/den,u=cross(q,r)/den;if(t>=0&&t<=1&&u>=0&&u<=1)return 0}
  return Math.min(pointSegment2(a,c,d),pointSegment2(b,c,d),pointSegment2(c,a,b),pointSegment2(d,a,b));
 }
 function rectHit(a,b,x1,y1,x2,y2){
  let lo=0,hi=1;
  for(const [v,d,l,h] of [[a.x,b.x-a.x,x1,x2],[a.y,b.y-a.y,y1,y2]]){
   if(Math.abs(d)<1e-5){if(v<l||v>h)return false;continue}
   let x=(l-v)/d,y=(h-v)/d;if(x>y)[x,y]=[y,x];lo=Math.max(lo,x);hi=Math.min(hi,y);if(lo>hi)return false;
  }
  return true;
 }
 function validate(map){
  if(!map||!Array.isArray(map.items)||!map.items.length||map.items.length>MAX)throw Error('请添加1～12个障碍');
  if(!Number.isFinite(map.radius)||map.radius<80||map.radius>1000||!Number.isFinite(map.margin)||map.margin<50||map.margin>1000)throw Error('车体半径须0.08～1米，额外余量须0.05～1米');
  for(const o of map.items){
   if(!inside({x:o.x1,y:o.y1})||!inside({x:o.x2,y:o.y2})||!Number.isFinite(o.width))throw Error('障碍坐标须在±10米内');
   if(o.kind==='R'){if(o.x2-o.x1<50||o.y2-o.y1<50||o.width!==0)throw Error('矩形长宽至少5厘米');}
   else if(o.kind==='W'){if(Math.hypot(o.x2-o.x1,o.y2-o.y1)<50||o.width<20||o.width>2000)throw Error('墙段至少5厘米长，厚度0.02～2米');}
   else throw Error('未知障碍形状');
  }
  return map;
 }
 function blocked(map,a,b=a){
  if(!inside(a)||!inside(b))return true;
  const p=map.radius+map.margin+EPS;
  return map.items.some(o=>o.kind==='R'?rectHit(a,b,o.x1-p,o.y1-p,o.x2+p,o.y2+p):segmentDistance2(a,b,{x:o.x1,y:o.y1},{x:o.x2,y:o.y2})<=sq(p+o.width/2));
 }
 function wire(map){validate(map);const f=n=>Number(n.toFixed(3));const text=`${f(map.radius)},${f(map.margin)}|`+map.items.map(o=>[o.kind,f(o.x1),f(o.y1),f(o.x2),f(o.y2),...(o.kind==='W'?[f(o.width)]:[])].join(',')).join(';');if(text.length>704)throw Error('障碍数据过多，请减少障碍或小数位');return text}
 function assertPath(map,start,points){
  validate(map);if(!inside(start)||blocked(map,start))throw Error('车位落入障碍安全区，请核对归零位置、车体尺寸和地图');
  let a=start,total=0;
  if(!points.length||points.length>12)throw Error('路线最多12个点');
  for(const b of points){if(!inside(b)||blocked(map,a,b))throw Error('路线经过障碍安全区，不能执行');const d=dist(a,b);if(d>5000.001)throw Error('路线单段超过5米');total+=d;a=b;}
  if(total>30000)throw Error('绕行路线超过30米');return total;
 }
 function plan(map,start,goal){
  validate(map);if(!inside(start)||!inside(goal))throw Error('车位和终点须在±10米内');
  if(blocked(map,start))throw Error('车位落入障碍安全区，请核对归零位置、车体尺寸和地图');
  if(blocked(map,goal))throw Error('终点落入障碍安全区，请重选终点');
  const nodes=[{...start},{...goal}],pad=map.radius+map.margin+EPS;
  const add=p=>{if(inside(p)&&!blocked(map,p)&&!nodes.some(n=>dist(n,p)<.1))nodes.push(p)};
  for(const o of map.items){
   if(o.kind==='R')for(const x of [o.x1-pad-PAD,o.x2+pad+PAD])for(const y of [o.y1-pad-PAD,o.y2+pad+PAD])add({x,y});
   else {
    const radius=(pad+o.width/2+PAD)/Math.cos(Math.PI/8),angle=Math.atan2(o.y2-o.y1,o.x2-o.x1);
    for(const [x,y] of [[o.x1,o.y1],[o.x2,o.y2]])for(let k=0;k<8;k++)add({x:x+radius*Math.cos(angle+k*Math.PI/4),y:y+radius*Math.sin(angle+k*Math.PI/4)});
   }
  }
  const n=nodes.length,cost=new Float64Array(n).fill(Infinity),prev=new Int16Array(n).fill(-1),used=new Uint8Array(n);cost[0]=0;
  // Visibility graph + Dijkstra; a small edge cost prefers fewer turns.
  // Work is bounded by <=194 nodes and 12 obstacles, with no external services.
  for(let turn=0;turn<n;turn++){
   let u=-1;for(let i=0;i<n;i++)if(!used[i]&&(u<0||cost[i]<cost[u]))u=i;
   if(u<0||!Number.isFinite(cost[u]))break;if(u===1)break;used[u]=1;
   for(let v=0;v<n;v++)if(v!==u&&!used[v]&&!blocked(map,nodes[u],nodes[v])){
    const c=cost[u]+dist(nodes[u],nodes[v])+50;if(c<cost[v]){cost[v]=c;prev[v]=u;}
   }
  }
  if(!Number.isFinite(cost[1]))throw Error('当前地图和安全余量下没有可行路线，请调整障碍或终点');
  const reversed=[];for(let v=1;v>=0;v=prev[v]){reversed.push(nodes[v]);if(v===0)break;}
  const route=reversed.reverse(),simple=[route[0]];
  for(let i=0;i<route.length-1;){let j=route.length-1;while(j>i+1&&blocked(map,route[i],route[j]))j--;simple.push(route[j]);i=j;}
  const points=[];
  for(let i=1;i<simple.length;i++){
   const a=simple[i-1],b=simple[i],steps=Math.max(1,Math.ceil(dist(a,b)/4990));
   for(let k=1;k<=steps;k++)points.push({x:Number((a.x+(b.x-a.x)*k/steps).toFixed(3)),y:Number((a.y+(b.y-a.y)*k/steps).toFixed(3))});
  }
  if(!points.length)points.push({...goal});
  const total=assertPath(map,start,points);
  return {points,total,wire:points.map(p=>`${p.x},${p.y}`).join(';'),mapWire:wire(map)};
 }
 function parse(text){
  if(typeof text!=='string'||text.length>704||!text.length)throw Error('障碍数据过长或为空');
  const parts=text.split('|');if(parts.length!==2)throw Error('障碍数据格式错误');
  const number=s=>{if(!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(s)||s.length>16)throw Error('障碍数值格式错误');return Number(s)};
  const config=parts[0].split(',');if(config.length!==2)throw Error('障碍尺寸格式错误');
  const map={radius:number(config[0]),margin:number(config[1]),items:[]};
  for(const row of parts[1].split(';')){const a=row.split(',');if(!((a[0]==='R'&&a.length===5)||(a[0]==='W'&&a.length===6)))throw Error('障碍数据格式错误');map.items.push({kind:a[0],x1:number(a[1]),y1:number(a[2]),x2:number(a[3]),y2:number(a[4]),width:a[0]==='W'?number(a[5]):0});}
  return validate(map);
 }
 return {validate,blocked,plan,assertPath,wire,parse,pointSegment2,segmentDistance2,rectHit};
})();
if(typeof module!=='undefined')module.exports=ObstaclePlanner;
let obstacles=[],obstacleDraft=null,obstacleFrameKey=null,avoidCache=null,obstacleInputError='',obstacleListMarkup=null,activeMapPanel='route',obstacleShape='rect',obstacleTaskKey=null;
const OBSTACLE_STORAGE='S3-THREE-WHEEL-R20-map-v1';
const obstacleCoordinateIds=['obstacleX1','obstacleY1','obstacleX2','obstacleY2'];
function clearObstacleCoordinateForm(){for(const id of obstacleCoordinateIds)$(id).value=''}
function writeObstacleCoordinates(o){for(const [i,id] of obstacleCoordinateIds.entries())$(id).value=Number((o[['x1','y1','x2','y2'][i]]/1000).toFixed(6));if(o.kind==='W')$('wallThickness').value=o.width/1000}
function selectedObstacleIndex(){const value=$('obstacleList').value;return value!==''&&Number.isInteger(Number(value))&&obstacles[Number(value)]?Number(value):-1}
function setMapPanel(panel){
 if(pathEditingBlocked())return;
 activeMapPanel=panel==='obstacles'?'obstacles':'route';obstacleDraft=null;obstacleInputError='';
 $('mapEditMode').value=activeMapPanel==='obstacles'?obstacleShape:'target';
 $('obstacleEditor').hidden=activeMapPanel!=='obstacles';$('routeEditor').hidden=activeMapPanel!=='route';
 for(const [id,active] of [['obstacleTab',activeMapPanel==='obstacles'],['routeTab',activeMapPanel==='route']]){$(id).ariaSelected=String(active);$(id).classList[active?'add':'remove']('active')}
 updateObstacleList();drawMap();
}
function loadObstacleCoordinates(){
 if(pathEditingBlocked())return;
 const n=selectedObstacleIndex();if(n<0)return;const o=obstacles[n];
 obstacleShape=o.kind==='W'?'wall':'rect';if(activeMapPanel==='obstacles')$('mapEditMode').value=obstacleShape;
 writeObstacleCoordinates(o);
 obstacleDraft=null;obstacleInputError='';updateObstacleList();drawMap();
}
function readObstacleMap(){return {items:obstacles.map(o=>({...o})),radius:Number($('obstacleRadius').value)*1000,margin:Number($('obstacleMargin').value)*1000}}
function saveObstacleMap(){
 if(!obstacleFrameKey)return;
 try{const map=readObstacleMap();if(map.items.length)ObstaclePlanner.validate(map);if(typeof localStorage!=='undefined')localStorage.setItem(OBSTACLE_STORAGE,JSON.stringify({frame:obstacleFrameKey,map,draft:Object.fromEntries(['goalX','goalY','goalSpeed','pathMode','waypointText','mapSpan'].map(id=>[id,$(id).value]))}));}catch(e){}
}
function invalidateMapOrigin(){
 obstacleFrameKey=null;obstacleTaskKey=null;obstacles=[];obstacleDraft=null;avoidCache=null;acceptedPath=null;mapHistory=[];obstacleInputError='';clearObstacleCoordinateForm();$('waypointText').value='';$('pathMode').value='direct';$('waypointEditor').hidden=true;$('goalX').value=1;$('goalY').value=0;
 try{localStorage.removeItem(OBSTACLE_STORAGE)}catch(e){}updateObstacleList();drawMap();
}
function syncObstacleFrame(s){
 if(s.poseZeroed!==true){if(obstacleFrameKey!==null||obstacles.length||obstacleDraft)invalidateMapOrigin();return;}
 if(!Number.isInteger(s.poseFrame)||s.poseFrame<1||!s.bootSession)return;
 const key=s.bootSession+':'+s.poseFrame;
 if(obstacleFrameKey!==key){
  const first=obstacleFrameKey===null;obstacleFrameKey=key;obstacleTaskKey=null;obstacles=[];obstacleDraft=null;obstacleInputError='';avoidCache=null;acceptedPath=null;mapHistory=[];clearObstacleCoordinateForm();$('obstacleList').value='';
  if(first)try{
   const saved=typeof localStorage!=='undefined'?JSON.parse(localStorage.getItem(OBSTACLE_STORAGE)||'null'):null;
   if(saved?.frame===key&&saved.map){if(saved.map.items.length)ObstaclePlanner.validate(saved.map);if(!Array.isArray(saved.map.items)||saved.map.items.length>12)throw Error('bad map');obstacles=saved.map.items.map(o=>({...o}));$('obstacleRadius').value=saved.map.radius/1000;$('obstacleMargin').value=saved.map.margin/1000;
    const d=saved.draft;if(d&&['direct','avoid','xy','yx','custom'].includes(d.pathMode)){for(const id of ['goalX','goalY'])if(String(d[id]).trim()&&Number.isFinite(Number(d[id]))&&Math.abs(Number(d[id]))<=10)$(id).value=d[id];if(Number(d.goalSpeed)>=35&&Number(d.goalSpeed)<=220)$('goalSpeed').value=d.goalSpeed;$('pathMode').value=d.pathMode;$('waypointText').value=typeof d.waypointText==='string'?d.waypointText.slice(0,2000):'';$('waypointEditor').hidden=d.pathMode!=='custom';if(['1000','2500','5000','10000'].includes(d.mapSpan))$('mapSpan').value=d.mapSpan;}
   }
  }catch(e){obstacles=[];}
  if(obstacles.length){writeObstacleCoordinates(obstacles[0]);obstacleShape=obstacles[0].kind==='W'?'wall':'rect';}
  if(!first){$('waypointText').value='';$('pathMode').value='direct';$('waypointEditor').hidden=true;$('goalX').value=1;$('goalY').value=0;note('设备重启或坐标已归零，旧障碍与预览已清空，请按当前原点重画');}
 }
 if(s.navActive&&s.navGuarded&&Array.isArray(s.obstacles)&&s.obstacles.length){
  try{
   const map={radius:s.obstacleRadius,margin:s.obstacleMargin,items:s.obstacles.map(a=>({kind:a[0],x1:a[1],y1:a[2],x2:a[3],y2:a[4],width:a[5]}))};ObstaclePlanner.validate(map);
   const taskKey=JSON.stringify([key,s.navPoints,s.finalX,s.finalY,map]);
   if(obstacleTaskKey!==taskKey){obstacleDraft=null;obstacleInputError='';avoidCache=null;clearObstacleCoordinateForm();$('obstacleList').value='';obstacleTaskKey=taskKey;}
   obstacles=map.items;$('obstacleRadius').value=map.radius/1000;$('obstacleMargin').value=map.margin/1000;
  }catch(e){}
 }else if(!s.navActive)obstacleTaskKey=null;
 updateObstacleList();saveObstacleMap();
}
function updateObstacleList(){
 const select=$('obstacleList'),old=select.value;
 const markup=obstacles.length?obstacles.map((o,i)=>`<option value="${i}">${i+1}. ${o.kind==='W'?'墙段':'矩形'} (${metres(o.x1)},${metres(o.y1)}) → (${metres(o.x2)},${metres(o.y2)})米</option>`).join(''):'<option value="">暂无障碍</option>';
 if(markup!==obstacleListMarkup){select.innerHTML=markup;obstacleListMarkup=markup;}
 if(obstacles[Number(old)]&&old!=='')select.value=old;
 $('obstacleInfo').textContent=obstacleDraft?`已选起点 (${metres(obstacleDraft.x)}, ${metres(obstacleDraft.y)})米，再点第二点完成；也可取消`:`已有${obstacles.length}/12个障碍。选择列表项可载入坐标，再点击“更新所选障碍”。`;
 renderMapInputHint();
}
function renderMapInputHint(){
 const mode=$('mapEditMode').value;
 $('mapModeText').textContent=mode==='rect'?'障碍设置 · 地图两点画矩形（两个对角）':mode==='wall'?'障碍设置 · 地图两点画墙段（两个端点）':'终点与路线 · 点击地图选择终点';
 let text=mode==='rect'?'画矩形：先点一个角，再点斜对角；第二点的X和Y都要不同。横墙或竖墙请选“墙段”。':mode==='wall'?'画墙段：点两个不同端点，水平、竖直或斜放都可以。':'选择终点：点击地图只更新目标；添加或修改障碍请切换“障碍设置”。';
 if(obstacleDraft)text=`第一点 (${metres(obstacleDraft.x)}, ${metres(obstacleDraft.y)})米已保留。`+text;
 if(obstacleInputError)text=obstacleInputError+(obstacleDraft?' 第一点仍保留，请在地图重选第二点，或取消本次绘制。':' 请检查障碍坐标及尺寸后重试。');
 if(mapStatus&&!hasFreshStatus())text+=' 当前可本地画图；恢复在线并刷新状态后才能确认行驶。';
 $('mapInputHint').textContent=text;$('mapInputHint').className='tip'+(obstacleInputError?' error':'');
 $('obstacleFormStatus').textContent=obstacleInputError||'填写后点击添加或更新才会保存障碍；这些操作不会让小车行驶。';
 $('obstacleFormStatus').className='tip'+(obstacleInputError?' error':'');
}
// Both numeric entry and two-click drawing validate an isolated candidate map.
// Failed additions/updates keep the old map and pending first point intact.
function makeObstacle(mode,a,b,width){
 const valid=p=>[p.x,p.y].every(Number.isFinite)&&Math.abs(p.x)<=10000&&Math.abs(p.y)<=10000;
 if(!valid(a)||!valid(b))throw Error('障碍坐标须为有限数值，且在±10米以内');
 a={x:Number(a.x.toFixed(6)),y:Number(a.y.toFixed(6))};b={x:Number(b.x.toFixed(6)),y:Number(b.y.toFixed(6))};
 if(mode==='rect'){
  if(Math.abs(b.x-a.x)<50||Math.abs(b.y-a.y)<50)throw Error('矩形第二点不能与第一点横向或纵向对齐，长宽都须至少5厘米；若画横墙或竖墙，请选择“墙段”');
  return {kind:'R',x1:Math.min(a.x,b.x),y1:Math.min(a.y,b.y),x2:Math.max(a.x,b.x),y2:Math.max(a.y,b.y),width:0};
 }
 if(mode!=='wall')throw Error('请在障碍设置中选择矩形或墙段');
 if(Math.hypot(b.x-a.x,b.y-a.y)<50)throw Error('墙段两个端点至少相隔5厘米');
 if(!Number.isFinite(width)||width<20||width>2000)throw Error('墙厚须为0.02～2米');
 return {kind:'W',x1:a.x,y1:a.y,x2:b.x,y2:b.y,width};
}
function commitObstacle(mode,a,b,width,replace=-1){
 if(pathEditingBlocked())throw Error('任务中或动作请求处理中，请先停车再编辑地图');
 if(replace<0&&obstacles.length>=12)throw Error('最多12个障碍，请先删除一个');
 if(replace>=0&&!obstacles[replace])throw Error('请先选择要更新的障碍');
 const candidate=makeObstacle(mode,a,b,width),map=readObstacleMap();
 if(replace<0)map.items.push(candidate);else map.items[replace]=candidate;
 ObstaclePlanner.validate(map);
 obstacles=map.items;obstacleDraft=null;obstacleInputError='';avoidCache=null;$('pathMode').value='avoid';$('waypointEditor').hidden=true;
 saveObstacleMap();updateObstacleList();$('obstacleList').value=String(replace<0?obstacles.length-1:replace);writeObstacleCoordinates(candidate);drawMap();
 note(replace<0?'障碍已添加；继续设置障碍或切换“终点与路线”，确认后才行驶':'所选障碍已更新，路线预览已重新检查；确认后才行驶');
}
function showObstacleInputError(e){obstacleInputError=e.message;updateObstacleList();drawMap();note(e.message)}
function obstacleMapClick(p){
 const mode=$('mapEditMode').value;if(mode!=='rect'&&mode!=='wall')return false;
 if(pathEditingBlocked())return true;
 if(obstacles.length>=12){showObstacleInputError(Error('最多12个障碍，请先删除一个'));return true;}
 if(!obstacleDraft){obstacleDraft={...p};obstacleInputError='';updateObstacleList();drawMap();return true;}
 try{commitObstacle(mode,obstacleDraft,p,Number($('wallThickness').value)*1000)}catch(e){showObstacleInputError(e)}return true;
}
function obstacleCoordinatesSubmit(update=false){
 if(pathEditingBlocked())return;
 try{
  const values=obstacleCoordinateIds.map(id=>String($(id).value).trim());
  if(values.some(s=>s===''))throw Error('请完整填写障碍X1、Y1、X2、Y2，单位米');
  const n=values.map(s=>Number(s)*1000);
  const index=update?selectedObstacleIndex():-1;if(update&&index<0)throw Error('请先在列表选择要更新的障碍');
  commitObstacle($('mapEditMode').value,{x:n[0],y:n[1]},{x:n[2],y:n[3]},Number($('wallThickness').value)*1000,index);
 }catch(e){showObstacleInputError(e)}
}
function obstacleSvg(){
 const k=180/mapSpan(),map=readObstacleMap(),pad=Number.isFinite(map.radius+map.margin)?Math.max(0,map.radius+map.margin+1):0,parts=[];
 for(let i=0;i<obstacles.length;i++){
  const o=obstacles[i],a=mapPoint(o.x1,o.y1),b=mapPoint(o.x2,o.y2);
  if(o.kind==='R'){
   parts.push(`<rect x="${a.x-pad*k}" y="${b.y-pad*k}" width="${(o.x2-o.x1+2*pad)*k}" height="${(o.y2-o.y1+2*pad)*k}" fill="#eea43c22" stroke="#eea43c" stroke-dasharray="4 3"/><rect x="${a.x}" y="${b.y}" width="${(o.x2-o.x1)*k}" height="${(o.y2-o.y1)*k}" fill="#ef596a99" stroke="#ff8390"/>`);
  }else parts.push(`<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#eea43c44" stroke-width="${(o.width+2*pad)*k}" stroke-linecap="round"/><line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#ff697a" stroke-width="${Math.max(2,o.width*k)}" stroke-linecap="round"/>`);
  parts.push(`<text x="${(a.x+b.x)/2+4}" y="${(a.y+b.y)/2-5}" fill="#ffb0b8" font-size="13">障碍${i+1}</text>`);
 }
 if(obstacleDraft){const p=mapPoint(obstacleDraft.x,obstacleDraft.y);parts.push(`<circle cx="${p.x}" cy="${p.y}" r="7" fill="#d18aff"/><text x="${p.x+10}" y="${p.y-8}" fill="#e1baff">再点第二点</text>`);}
 return parts;
}
function obstacleCoordinateDraft(base){
 if(obstacleDraft)throw Error(obstacleInputError||'请先完成或取消当前障碍绘制');
 const mode=$('pathMode').value,goal=selectedGoal();
 if(!obstacles.length){if(mode==='avoid')throw Error('请先添加障碍（填写坐标或在地图绘制），或选择直达目标');return base();}
 const map=readObstacleMap();ObstaclePlanner.validate(map);
 if(!Number.isInteger(mapStatus?.poseFrame)||mapStatus.poseFrame<1)throw Error('请等待设备状态与地图原点同步');
 let draft;
 if(mode==='avoid'){
  const key=JSON.stringify([mapPose.x,mapPose.y,goal,map]);
  if(avoidCache?.key===key)draft=avoidCache.value;
  else {draft=ObstaclePlanner.plan(map,mapPose,goal);avoidCache={key,value:draft};}
 }else {draft=base();ObstaclePlanner.assertPath(map,mapPose,draft.points);draft={...draft,mapWire:ObstaclePlanner.wire(map)};}
 return {...draft,guarded:true,frame:mapStatus.poseFrame};
}
function installObstacleEditor(){
 $('mapEditMode').value='target';
 $('obstacleTab').onclick=()=>setMapPanel('obstacles');$('routeTab').onclick=$('obstaclesDone').onclick=()=>setMapPanel('route');
 $('mapEditMode').addEventListener('change',()=>{if(pathEditingBlocked())return;obstacleShape=$('mapEditMode').value==='wall'?'wall':'rect';$('mapEditMode').value=activeMapPanel==='obstacles'?obstacleShape:'target';obstacleDraft=null;obstacleInputError='';updateObstacleList();drawMap()});
 $('obstacleList').addEventListener('change',loadObstacleCoordinates);
 $('addObstacleCoordinates').onclick=()=>obstacleCoordinatesSubmit(false);$('updateObstacleCoordinates').onclick=()=>obstacleCoordinatesSubmit(true);
 for(const id of [...obstacleCoordinateIds,'obstacleRadius','obstacleMargin','wallThickness'])$(id).addEventListener('input',()=>{if(pathEditingBlocked())return;obstacleInputError='';avoidCache=null;if(!obstacleCoordinateIds.includes(id))saveObstacleMap();updateObstacleList();drawMap()});
 $('cancelObstacle').onclick=()=>{if(pathEditingBlocked())return;obstacleDraft=null;obstacleInputError='';updateObstacleList();drawMap()};
 $('removeObstacle').onclick=()=>{if(pathEditingBlocked())return;const n=selectedObstacleIndex();if(n<0)return;obstacles.splice(n,1);obstacleDraft=null;obstacleInputError='';avoidCache=null;clearObstacleCoordinateForm();if(!obstacles.length&&$('pathMode').value==='avoid')$('pathMode').value='direct';saveObstacleMap();updateObstacleList();drawMap()};
 $('clearObstacles').onclick=()=>{if(pathEditingBlocked())return;obstacles=[];obstacleDraft=null;obstacleInputError='';avoidCache=null;clearObstacleCoordinateForm();if(!obstacles.length&&$('pathMode').value==='avoid')$('pathMode').value='direct';saveObstacleMap();updateObstacleList();drawMap();note('已清空障碍地图，未移动车位')};
 $('planAvoid').onclick=()=>{if(pathEditingBlocked())return;$('pathMode').value='avoid';$('waypointEditor').hidden=true;drawMap();try{const draft=coordinateDraft();note(`已规划${draft.points.length}个点、约${metres(draft.total)}米；点击确认才行驶`)}catch(e){note(e.message)}};
 updateObstacleList();
}
let discreteBusy=false,mapSubmitBusy=false;
let mapPose={x:0,y:0,yaw:0},mapHistory=[],mapStatus=null,acceptedPath=null,mapMarkup=null;
const navLabels={'idle':'待机','turning':'转向目标','settling':'刹车等待停稳','driving':'直线靠近','arrived-estimate':'估算到点','completed-distance':'行程结束，未确认到点','cancelled':'已取消','failed':'失败并停车'};
const navReasons={'ALIGNMENT_LIMIT':'纠偏预算耗尽，已停车','COORDINATE_NOT_CONFIRMED':'坐标原点未确认','STOP_OUTPUT_FAULT':'停车输出故障','AVOID_ALIGNMENT':'障碍路线纠偏失败，已停车','MAP_FRAME':'原点变化，请重画障碍','OBSTACLE_NEAR':'进入障碍安全区','OBSTACLE_DEVIATION':'返向目标会穿过障碍','OBSTACLE_BRAKING':'预计制动范围进入障碍','ODOMETRY_ONLY':'请实测核对终点','DISTANCE_ONLY':'含停止纠偏路段，请核对实车终点','IDEAL_ANIMATION':'理想动画','none':'','LEG_LIMIT':'下一段超出5米，请停车后重选','POSITION_MISMATCH':'本段到点误差超限','HEADING_MISMATCH':'转向未对准','TOTAL_TIMEOUT':'整段超时','FG_MISSING':'轮子反馈缺失','FG_NOT_QUIET':'轮子未停稳','PAGE_LOST':'页面断联','STOPPED':'已停车','FAULT':'保护停车'};
const metres=n=>(n/1000).toFixed(2);
function mapSpan(){const n=Number($('mapSpan').value);return [1000,2500,5000,10000].includes(n)?n:5000}
function selectedGoal(){return {x:Number($('goalX').value)*1000,y:Number($('goalY').value)*1000}}
function mapPoint(x,y){const k=180/mapSpan();return {x:320+x*k,y:220-y*k}}
function mapClickToWorld(clientX,clientY,rect){return {x:Math.round((((clientX-rect.left)*640/rect.width)-320)/(180/mapSpan())/50)*50,y:Math.round((220-(clientY-rect.top)*440/rect.height)/(180/mapSpan())/50)*50}}
function parseWaypointPoint(line){
 if(!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)\s*[,，]\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(line))throw Error('途经点每行填写 X,Y，单位米');
 const [x,y]=line.split(/[,，]/).map(n=>Number(n)*1000);
 if(![x,y].every(Number.isFinite)||Math.abs(x)>10000||Math.abs(y)>10000)throw Error('途经点坐标须在±10米以内');
 return {x,y};
}
function buildCoordinatePath(start,goal,mode,text=''){
 const valid=p=>[p.x,p.y].every(Number.isFinite)&&Math.abs(p.x)<=10000&&Math.abs(p.y)<=10000;
 if(!valid(start)||!valid(goal))throw Error('车位和目标坐标须在±10米以内');
 let points=[];
 if(mode==='xy')points.push({x:goal.x,y:start.y});
 else if(mode==='yx')points.push({x:start.x,y:goal.y});
 else if(mode==='custom'){
  const lines=String(text).split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
  if(lines.length>12)throw Error('最多12个点，包含最终目标');
  for(const line of lines)points.push(parseWaypointPoint(line));
 }else if(mode!=='direct')throw Error('请选择有效的走法');
 points.push({...goal});
 // Remove consecutive duplicates; preserve the final point even at zero distance.
 const cleaned=[];let previous=start,total=0;
 for(const point of points){
  if(Math.hypot(point.x-previous.x,point.y-previous.y)<.01)continue;
  const distance=Math.hypot(point.x-previous.x,point.y-previous.y);
  if(distance>5000)throw Error(`第${cleaned.length+1}段 (${metres(previous.x)},${metres(previous.y)}) → (${metres(point.x)},${metres(point.y)}) 长约${metres(distance)}米，超过5米；请增加途经点并核对上方终点`);
  total+=distance;cleaned.push(point);previous=point;
 }
 if(!cleaned.length)cleaned.push({...goal});
 if(cleaned.length>12)throw Error('最多12个点，包含最终目标');
 if(total>30000)throw Error('整条坐标路线须不超过30米');
 return {points:cleaned,total,wire:cleaned.map(p=>`${Number(p.x.toFixed(3))},${Number(p.y.toFixed(3))}`).join(';')};
}
function coordinateDraft(){
 if(['goalX','goalY','goalSpeed'].some(id=>String($(id).value).trim()===''))throw Error('请完整填写目标X、Y和速度');
 const speed=Number($('goalSpeed').value);if(!Number.isFinite(speed)||speed<35||speed>220)throw Error('坐标导航速度须为35–220mm/s');
 return {...obstacleCoordinateDraft(()=>buildCoordinatePath(mapPose,selectedGoal(),$('pathMode').value,$('waypointText').value)),speed};
}
function drawMap(){
 updateMapEditingControls();renderMapInputHint();
 const svg=$('mapSvg'),span=mapSpan(),k=180/span;let parts=[];
 for(let i=-4;i<=4;i++){const n=i*span/4,px=320+n*k,py=220-n*k;parts.push(`<path d="M ${px} 25 V 410 M 35 ${py} H 605" stroke="#1f384c" fill="none"/>`)}
 parts.push('<path d="M35 220 H605 M320 410 V25" stroke="#6a879f" fill="none"/><text x="606" y="211" fill="#b4c9db" font-size="13">+X</text><text x="330" y="23" fill="#b4c9db" font-size="13">+Y</text><text x="326" y="236" fill="#b4c9db" font-size="12">0</text>');
 parts.push(...obstacleSvg());
 if(mapHistory.length>1)parts.push(`<polyline points="${mapHistory.map(p=>{const q=mapPoint(p.x,p.y);return q.x.toFixed(1)+','+q.y.toFixed(1)}).join(' ')}" fill="none" stroke="#57d5ff" stroke-width="2"/>`);
 const goal=selectedGoal(),robot=mapPoint(mapPose.x,mapPose.y);let draft=null;
 try{
  if(mapStatus?.navActive){
   const telemetry=Array.isArray(mapStatus.navPoints)&&mapStatus.navPoints.length&&mapStatus.navPoints.every(a=>Array.isArray(a)&&a.length>=2&&a.slice(0,2).every(n=>Number.isFinite(n)&&Math.abs(n)<=10000))?mapStatus.navPoints.map(a=>({x:a[0],y:a[1]})):null;
   const points=telemetry||(acceptedPath?.bootSession===bootSession&&acceptedPath.frame===mapStatus.poseFrame?acceptedPath.points:[{x:mapStatus.goalX,y:mapStatus.goalY}]),remaining=points.slice(Math.max(0,(mapStatus.navPoint||1)-1));
   draft={points:remaining};$('pathPreview').textContent=`执行中：第${mapStatus.navPoint||1}/${mapStatus.navCount||1}个点，本点剩余约${metres(Number(mapStatus.goalError||0))}米`;
  }else{draft=coordinateDraft();$('pathPreview').textContent=`预览（米）：起点 (${metres(mapPose.x)}, ${metres(mapPose.y)}) → ${draft.points.map((p,i)=>`${i+1}. (${metres(p.x)}, ${metres(p.y)})`).join(' → ')}；合计约${metres(draft.total)}米。点击确认才执行。`}
  if(draft?.guarded)$('pathPreview').textContent+=' 已避开已设障碍及车体余量保护区。';
  $('pathPreview').classList.remove('error');
 }catch(e){$('pathPreview').textContent=e.message;$('pathPreview').classList.add('error')}
 if(draft){
  const points=[mapPose,...draft.points].map(p=>mapPoint(p.x,p.y));
  parts.push(`<polyline points="${points.map(p=>`${p.x},${p.y}`).join(' ')}" stroke="#ffd166" stroke-width="2" stroke-dasharray="6 6" fill="none"/>`);
  draft.points.forEach((p,i)=>{const q=mapPoint(p.x,p.y);parts.push(`<circle cx="${q.x}" cy="${q.y}" r="8" stroke="#ffd166" stroke-width="2" fill="#423b21"/><text x="${q.x+11}" y="${q.y-9}" fill="#ffd166" font-size="13">${(mapStatus?.navActive?(mapStatus.navPoint||1):1)+i}</text>`)});
 }
 if([goal.x,goal.y].every(Number.isFinite)){
  const g=mapPoint(goal.x,goal.y);parts.push(`<path d="M${g.x-13} ${g.y}h26 M${g.x} ${g.y-13}v26" stroke="#ffd166"/>`);
  $('goalInfo').textContent=`终点 (${metres(goal.x)}, ${metres(goal.y)}) 米`;
 }
 parts.push(`<g transform="translate(${robot.x} ${robot.y}) rotate(${-mapPose.yaw})"><circle r="13" fill="#123b52" stroke="#7de4ff"/><path d="M18 0 L-10 -9 L-5 0 L-10 9 Z" fill="#7de4ff"/></g><text x="18" y="430" fill="#b4c9db" font-size="12">青色：估算轨迹/车头　黄色：路线/点序　纵向半幅 ±${metres(span)}米</text>`);
 const markup=parts.join('');if(markup!==mapMarkup){svg.innerHTML=markup;mapMarkup=markup;}
}
function renderMapStatus(s){
 if(![s.x,s.y,s.yaw].every(Number.isFinite))return;
 mapStatus=s;mapPose={x:s.x,y:s.y,yaw:s.yaw};syncObstacleFrame(s);
 if(s.navActive&&[s.finalX,s.finalY].every(Number.isFinite)){$('goalX').value=s.finalX/1000;$('goalY').value=s.finalY/1000}
 const last=mapHistory[mapHistory.length-1];
 if(!last||Math.hypot(last.x-s.x,last.y-s.y)>2){mapHistory.push({x:s.x,y:s.y});if(mapHistory.length>600)mapHistory.shift()}
 $('navState').textContent=(navLabels[s.nav]||'待机')+(s.navCount?` · 点${s.navPoint}/${s.navCount}`:'')+(s.navReason&&s.navReason!=='none'?' · '+(navReasons[s.navReason]||sourceLabels[s.navReason]||s.navReason):'');
 drawMap();
}
function validateGoal(){const draft=coordinateDraft();return {...selectedGoal(),speed:draft.speed}}
// Drawing is local. A short status gap must not consume the pending corner.
// Sending motion remains guarded by hasFreshStatus() in gotoBtn and post().
function pathEditingBlocked(){return mapSubmitBusy||hasPendingMotion()||motionMayBeActive||discreteBusy||!mapStatus||!obstacleFrameKey||Boolean(mapStatus.navActive||mapStatus.routeActive||mapStatus.mode!=='idle')}
function updateMapEditingControls(){
 const busy=pathEditingBlocked();
 for(const id of ['goalX','goalY','goalSpeed','pathMode','waypointText','addWaypoint','clearWaypoints','useLastWaypoint','mapEditMode','obstacleRadius','obstacleMargin','wallThickness','removeObstacle','clearObstacles','cancelObstacle','planAvoid','obstacleList','obstacleTab','routeTab','obstaclesDone',...obstacleCoordinateIds,'addObstacleCoordinates','updateObstacleCoordinates'])$(id).disabled=busy;
 const s=mapStatus;$('gotoBtn').disabled=!s?.consoleMode||busy||Boolean(obstacleDraft)||!s||s.fault!=='none'||!s.ready||!hasFreshStatus()||(!MAP_DEMO&&s.imuReady!==true)||s.stage!=='MONITOR'||s.poseZeroed!==true||!Number.isInteger(s.poseFrame)||(!MAP_DEMO&&(s.controlMode!=='three-wheel-scan-lite-v4'||s.driveTurnUnits!=='deg/s'||s.imuUsable!==true));
}
$('mapSvg').addEventListener('pointerdown',e=>{if(e.isPrimary===false||e.button>0)return;e.preventDefault();if(pathEditingBlocked()){const text=!mapStatus?'请先等待首次设备状态，建立地图原点后再画图':'任务中或动作请求处理中，请先停车再编辑地图';$('mapInputHint').textContent=text;note(text);return}const p=mapClickToWorld(e.clientX,e.clientY,$('mapSvg').getBoundingClientRect());if(Math.abs(p.x)>10000||Math.abs(p.y)>10000){$('mapInputHint').textContent='请在±10米范围内选点';note('请在±10米范围内选点');return}if(obstacleMapClick(p))return;$('goalX').value=p.x/1000;$('goalY').value=p.y/1000;drawMap()});
for(const id of ['goalX','goalY','goalSpeed','mapSpan','waypointText'])$(id).addEventListener('input',drawMap);
$('pathMode').addEventListener('change',()=>{$('waypointEditor').hidden=$('pathMode').value!=='custom';drawMap()});
$('addWaypoint').onclick=()=>{if(pathEditingBlocked())return;const goal=selectedGoal();if(['goalX','goalY'].some(id=>!String($(id).value).trim())||![goal.x,goal.y].every(Number.isFinite)||Math.abs(goal.x)>10000||Math.abs(goal.y)>10000){note('先选择有效坐标');return}const lines=$('waypointText').value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);if(lines.length>=11){note('最多11个途经点，另保留一个最终目标');return}$('waypointText').value=[...lines,`${goal.x/1000},${goal.y/1000}`].join('\n');drawMap()};
$('clearWaypoints').onclick=()=>{if(pathEditingBlocked())return;$('waypointText').value='';drawMap()};
$('useLastWaypoint').onclick=()=>{
 if(pathEditingBlocked())return;
 try{
  const lines=$('waypointText').value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
  if(!lines.length)throw Error('先填写途经点列表');
  const point=parseWaypointPoint(lines[lines.length-1]);
  $('goalX').value=point.x/1000;$('goalY').value=point.y/1000;
  drawMap();note(`终点已设为列表末点 (${metres(point.x)}, ${metres(point.y)})米，请核对预览后再确认`);
 }catch(e){note(e.message)}
};
$('gotoBtn').onclick=async()=>{
 if(hasPendingMotion()||discreteBusy||mapSubmitBusy)return;
 resetInputs();try{
  if(!hasFreshStatus()||!mapStatus||!mapStatus.poseZeroed||mapStatus.navActive||mapStatus.routeActive||mapStatus.mode!=='idle')throw Error('请等待小车在线、停稳并刷新状态');
  const draft=coordinateDraft();const submitted={points:draft.points.map(p=>({...p})),bootSession,frame:mapStatus.poseFrame};
  mapSubmitBusy=true;drawMap();
  await post(draft.guarded?'avoid':'path',{points:draft.wire,speed:draft.speed,frame:mapStatus.poseFrame,...(draft.guarded?{map:draft.mapWire}:{})});acceptedPath=submitted;
  if(ownedTask)note(`坐标路线已接受，共${draft.points.length}个点；请保持页面亮屏前台`);
 }catch(e){note(e.message)}finally{mapSubmitBusy=false;drawMap()}
};
$('mapStop').onclick=stop;
$('imuReconnect').onclick=async()=>{
 if($('imuReconnect').disabled||hasPendingMotion()||!hasFreshStatus()||mapStatus?.imuCanReconnect!==true)return;
 resetInputs();actionBusy=true;try{await post('imu/reconnect');invalidateMapOrigin();note('已重试IMU查询，原点已撤销；请静置等待版本和角度，再重新归零')}catch(e){note(e.message)}finally{actionBusy=false}
};
$('clearTrack').onclick=()=>{mapHistory=[{x:mapPose.x,y:mapPose.y}];drawMap();note('仅清空显示轨迹，未修改车位')};
$('zero').onclick=async()=>{if($('zero').disabled||actionBusy)return;resetInputs();actionBusy=true;try{await post('zero');invalidateMapOrigin();note('归零请求已接受，等待新frame；请按新原点重画障碍并核对目标')}catch(e){note(e.message)}finally{actionBusy=false}};
if(MAP_DEMO){$('demoBanner').style.display='block';$('mapSource').textContent='离线演示 · 理想运动';$('connected').textContent='离线演示'}
installObstacleEditor();
drawMap();
setInterval(()=>{if(!hasFreshStatus()){releaseForInactivity('状态过期，已请求停车；不会自动恢复。');invalidateStatus()}else if(desired().active)void sendDrive()},150);
setInterval(poll,250);void poll();

$('consoleAcquire').onclick=async()=>{try{await post('inspection/arm',{value:1,confirm:1,owner:1,frame:mapStatus?.poseFrame});note('已接管完整上位机，尚未开始移动');}catch(e){note(e.message)}};
$('consoleReturn').onclick=async()=>{try{await post('stop');location.href='/';}catch(e){note(e.message)}};
setInterval(()=>{$('consoleOwnerState').textContent=mapStatus?.consoleMode?'手动/路径 owner 已启用':'未接管，动作不可发送';},300);
</script></body></html>
)HTML";
