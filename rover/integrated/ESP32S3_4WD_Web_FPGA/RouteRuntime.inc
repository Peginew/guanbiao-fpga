bool routeActive() {
  return route.stage==RouteStage::Running||route.stage==RouteStage::Settling||route.stage==RouteStage::Waiting;
}
const char *routeStageName() {
  switch(route.stage) {
    case RouteStage::Running:return route.aligning?"heading-correction":"running";
    case RouteStage::Settling:return "settling";
    case RouteStage::Waiting:return "waiting";
    case RouteStage::Completed:return "completed-estimate";
    case RouteStage::Cancelled:return "cancelled";
    case RouteStage::Failed:return "failed";
    default:return "idle";
  }
}
void cancelRoute(const char *reason) {
  if(!routeActive())return;
  route.reason=reason;
  route.stage=fault!=Fault::None||ioFault||control.estop?RouteStage::Failed:RouteStage::Cancelled;
}
void failRoute(const char *reason) {
  route.stage=RouteStage::Failed;route.reason=reason;
  setFault(Fault::Route);
}
float routeHeadingError() {
  return atan2f(sinf(route.headingRad-thetaRad),cosf(route.headingRad-thetaRad));
}
bool startRouteOwnedSegment(float left,float right,float speed,const char *label) {
  const Source saved=requestSource;requestSource=routeSource;routeInternal=true;
  route.stage=RouteStage::Running;
  const bool ok=startSegment(left,right,speed,label);
  routeInternal=false;requestSource=saved;
  if(!ok)failRoute("STEP_REJECTED");
  return ok;
}
bool startRouteAlignment(bool beforeStep) {
  const float degrees=routeHeadingError()*RAD2DEG;
  if(fabsf(degrees)>RouteLimits::MAX_ALIGN_DEG) {failRoute("HEADING_DEVIATION");return false;}
  if(route.headingCorrections>=RouteLimits::MAX_HEADING_CORRECTIONS) {failRoute("HEADING_NOT_REACHED");return false;}
  ++route.headingCorrections;route.aligning=true;route.alignmentBeforeStep=beforeStep;
  const float side=TRACK_EFFECTIVE_MM*0.5f*degrees*DEG2RAD;
  // Use the same calibrated geometry, with a bounded speed for small corrections.
  return startRouteOwnedSegment(-side,side,fminf(route.plan.speed,40.0f),"route-align");
}
bool beginRouteStep() {
  if(route.index>=route.plan.count) {
    stopVehicle("route-completed");
    if(ioFault||fault!=Fault::None||control.estop){route.stage=RouteStage::Failed;route.reason="STOP_OUTPUT_FAULT";return false;}
    route.stage=RouteStage::Completed;route.reason="ODOMETRY_ONLY";return true;
  }
  const RouteStep &step=route.plan.steps[route.index];
  route.stageSinceMs=millis();
  if(step.kind=='W') {
    route.aligning=false;brakeAllImmediately();mode=Mode::Idle;
    if(ioFault||fault!=Fault::None||control.estop){failRoute("STOP_OUTPUT_FAULT");return false;}
    route.stage=RouteStage::Waiting;return true;
  }
  const float residual=routeHeadingError();
  if(step.kind=='M') {
    if(!ImuConfig::ENABLED&&fabsf(residual)*RAD2DEG>RouteLimits::HEADING_TOL_DEG)return startRouteAlignment(true);
    route.aligning=false;
    // Equal wheel endpoints would undo heading correction at the end. Preserve
    // the requested centre travel while budgeting the required differential.
    const float differential=ImuConfig::ENABLED?0:TRACK_EFFECTIVE_MM*0.5f*residual;
    return startRouteOwnedSegment(step.value-differential,step.value+differential,route.plan.speed,"route-move");
  }
  route.aligning=false;
  if(fabsf(residual)*RAD2DEG>RouteLimits::MAX_ALIGN_DEG) {failRoute("HEADING_DEVIATION");return false;}
  // Keep full +/-360-degree requests; only the inherited residual is wrapped.
  // Planned headings stay fixed instead of accumulating each stop's overshoot.
  const float side=TRACK_EFFECTIVE_MM*0.5f*(step.value*DEG2RAD+residual);
  const bool ok=startRouteOwnedSegment(-side,side,RouteSpeed::turnLimit(route.plan.speed),"turn");
  if(ok)route.headingRad=atan2f(sinf(route.headingRad+step.value*DEG2RAD),cosf(route.headingRad+step.value*DEG2RAD));
  return ok;
}
bool startRoute(const RoutePlan &incoming) {
  if(LINK_DIAGNOSTIC_ONLY)return false;
  if(requestSource!=Source::Web||!poseZeroed||incoming.speed>WEB_MAX_LINEAR_MM_S)return false;
  if(mode!=Mode::Idle||routeActive()||navigationActive()||!canRequestMotion())return false;
  // Revalidate even when called directly (not via HTTP). No partial execution.
  char encoded[RouteLimits::MAX_TEXT+1]={};size_t used=0;
  if(!incoming.count||incoming.count>RouteLimits::MAX_STEPS)return false;
  for(uint8_t i=0;i<incoming.count;i++) {
    const int n=snprintf(encoded+used,sizeof(encoded)-used,"%s%c:%.3f",i?";":"",incoming.steps[i].kind,incoming.steps[i].value);
    if(n<0||size_t(n)>=sizeof(encoded)-used)return false;
    used+=size_t(n);
  }
  RoutePlan checked;
  if(!parseRoutePlan(encoded,incoming.speed,TRACK_EFFECTIVE_MM,checked))return false;
  const uint32_t now=millis();
  if(uint32_t(now-stoppedSinceMs)<DIRECTION_BRAKE_MS)return false;
  for(uint8_t i=0;i<4;i++)if(CarConfig::motorEnabled(i)&&uint32_t(now-motor[i].lastPulseMs)<DIRECTION_QUIET_MS)return false;
  headingFeedback=HeadingFeedback{};
  route=RouteState{};route.plan=checked;route.poseFrame=poseFrame;routeSource=requestSource;
  route.startedMs=now;route.deadlineMs=checked.nominalMs*3+uint32_t(checked.count)*6000+4000;
  for(uint8_t i=0;i<checked.count;i++)if(checked.steps[i].kind=='M')route.deadlineMs+=60000;
  route.plannedX=xMm;route.plannedY=yMm;
  route.headingRad=thetaRad;route.stage=RouteStage::Waiting;owner=requestSource;
  return beginRouteStep();
}
void finishRouteSegment(uint32_t now) {
  if(goalDrive.distanceOnly){failRoute("COORDINATE_NOT_CONFIRMED");return;}
  if(ImuConfig::ENABLED&&!route.aligning&&route.plan.steps[route.index].kind=='M') {
    route.plannedX=goalDrive.gx;route.plannedY=goalDrive.gy;
  }
  // Brake WITHOUT calling stopVehicle: the route and page lease span all steps.
  brakeAllImmediately();mode=Mode::Idle;
  if(ioFault||fault!=Fault::None||control.estop){failRoute("STOP_OUTPUT_FAULT");return;}
  route.stage=RouteStage::Settling;route.stageSinceMs=now;
}
void serviceRoute() {
  if(!routeActive())return;
  if(fault!=Fault::None||ioFault||control.estop){cancelRoute("FAULT");return;}
  if(!poseZeroed||route.poseFrame!=poseFrame){failRoute("MAP_FRAME");return;}
  const uint32_t now=millis();
  if(uint32_t(now-route.startedMs)>route.deadlineMs){failRoute("TOTAL_TIMEOUT");return;}
  if(ImuConfig::ENABLED&&!imu.ready(now))return; // hold step boundaries during bounded IMU pause
  if(route.stage==RouteStage::Running) {
    // Include low-speed operations; missing FG must not run until a long 5m deadline.
    for(uint8_t i=0;i<4;i++)if(CarConfig::motorEnabled(i)&&motor[i].driven&&motor[i].dutyPercent>0&&
      uint32_t(now-motor[i].driveStartMs)>=RouteLimits::FG_TIMEOUT_MS&&
      uint32_t(now-motor[i].lastPulseMs)>=RouteLimits::FG_TIMEOUT_MS) {
      failRoute("FG_MISSING");return;
    }
    return;
  }
  if(route.stage==RouteStage::Waiting) {
    if(uint32_t(now-route.stageSinceMs)<uint32_t(route.plan.steps[route.index].value))return;
  } else {
    if(uint32_t(now-route.stageSinceMs)>RouteLimits::SETTLE_TIMEOUT_MS){failRoute("FG_NOT_QUIET");return;}
    if(uint32_t(now-route.stageSinceMs)<RouteLimits::SETTLE_MS)return;
    for(uint8_t i=0;i<4;i++)if(CarConfig::motorEnabled(i)&&uint32_t(now-motor[i].lastPulseMs)<DIRECTION_QUIET_MS)return;
  }
  if(route.stage==RouteStage::Settling) {
    // Encoder samples continue during braking, so this includes measured coast
    // after both sides first reached their travel targets.
    if(!ImuConfig::ENABLED&&fabsf(routeHeadingError())*RAD2DEG>RouteLimits::HEADING_TOL_DEG) {
      startRouteAlignment(route.aligning&&route.alignmentBeforeStep);return;
    }
    if(route.aligning&&route.alignmentBeforeStep) {
      route.aligning=false;beginRouteStep();return;
    }
  }
  route.aligning=false;route.headingCorrections=0;
  ++route.index;beginRouteStep();
}
float routeRemaining() {
  if(!routeActive()||route.index>=route.plan.count)return 0;
  const auto &step=route.plan.steps[route.index];
  if(ImuConfig::ENABLED&&mode==Mode::Segment&&(route.aligning||step.kind=='T'))
    return fabsf(imuMotion.targetDeg-imu.headingDeg());
  if(route.aligning)return step.kind=='M'?(route.alignmentBeforeStep?fabsf(step.value):0):fabsf(routeHeadingError()*RAD2DEG);
  if(route.stage==RouteStage::Settling)return 0;
  if(step.kind=='W')return fmaxf(0,step.value-float(uint32_t(millis()-route.stageSinceMs)));
  if(ImuConfig::ENABLED&&step.kind=='M'&&mode==Mode::Segment)return goalDrive.remaining;
  const float progress=0.5f*((avgLeftMm-segment.startL)*signf(segment.goalL)+(avgRightMm-segment.startR)*signf(segment.goalR));
  const float goal=0.5f*(fabsf(segment.goalL)+fabsf(segment.goalR));
  const float remaining=fmaxf(0,goal-progress);
  return step.kind=='M'?remaining:remaining/(TRACK_EFFECTIVE_MM*0.5f*DEG2RAD);
}
void correctRouteStraight(float &left,float &right,float travelL,float travelR) {
  if(ImuConfig::ENABLED)return; // centre-distance + IMU controller owns R4 straight targets
  if(!routeActive()||route.aligning||route.plan.steps[route.index].kind!='M'||!left||!right)return;
  // Finish at heading-compensated wheel endpoints. Suppress correction near the
  // endpoint and never reverse a wheel to compensate for heading error.
  if(fabsf(segment.goalL)-travelL*signf(segment.goalL)<60||
     fabsf(segment.goalR)-travelR*signf(segment.goalR)<60)return;
  // Historical wheel-only behavior retained for the legacy host regression.
  // Production R4 returns above: ImuRuntime owns centre-distance heading hold.
  const float error=atan2f(sinf(route.headingRad-thetaRad),cosf(route.headingRad-thetaRad));
  const float correction=clampf(error*80.0f,-route.plan.speed*0.30f,route.plan.speed*0.30f);
  const float direction=signf(segment.goalL);
  left=direction*clampf((left-correction)*direction,10,route.plan.speed*1.30f);
  right=direction*clampf((right+correction)*direction,10,route.plan.speed*1.30f);
}
