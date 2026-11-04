bool navigationActive() {
  return navigation.stage==NavStage::Turning || navigation.stage==NavStage::Settling || navigation.stage==NavStage::Driving;
}
const char *navigationStageName() {
  switch(navigation.stage) {
    case NavStage::Turning:return "turning";
    case NavStage::Settling:return "settling";
    case NavStage::Driving:return "driving";
    case NavStage::Arrived:return "arrived-estimate";
    case NavStage::DistanceCompleted:return "completed-distance";
    case NavStage::Cancelled:return "cancelled";
    case NavStage::Failed:return "failed";
    default:return "idle";
  }
}
void cancelNavigation() {
  if(navigationActive()) {
    navigation.stage=fault!=Fault::None||ioFault||control.estop?NavStage::Failed:NavStage::Cancelled;
    if(!strcmp(navigation.reason,"none"))navigation.reason="STOPPED";
  }
}
float navigationDistance() {return hypotf(navigation.goalX-xMm,navigation.goalY-yMm);}
float navigationHeadingError() {
  const float angle=atan2f(navigation.goalY-yMm,navigation.goalX-xMm)-thetaRad;
  return atan2f(sinf(angle),cosf(angle))*RAD2DEG;
}
bool navigationSegment(float left,float right,const char *label) {
  const Source saved=requestSource;requestSource=navigationSource;navigationInternal=true;
  const float speed=fabsf(left+right)<.001f?fminf(navigation.speed,PathLimits::TURN_SPEED):navigation.speed;
  const bool ok=startSegment(left,right,speed,label);
  navigationInternal=false;requestSource=saved;return ok;
}
void navigationFailed(const char *reason) {
  navigation.reason=reason;navigation.stage=NavStage::Failed;
  setFault(Fault::Navigation);
}
bool beginNavigationDrive() {
  const float distance=navigationDistance();navigation.errorMm=distance;
  // Submitted legs remain strictly <=5000mm. A turn or the previous stop can
  // leave up to one accepted endpoint tolerance; do not reject that tiny coast
  // as a newly oversized leg after the already-validated task has started.
  if(distance>NAV_MAX_LEG_MM+NAV_POSITION_TOL_MM || !isFiniteNumber(distance)) {
    navigationFailed("LEG_LIMIT");return false;
  }
  if(distance<=POSITION_TOL_MM) {
    navigation.stage=NavStage::Driving;finishNavigationSegment(millis());return true;
  }
  if(!ImuConfig::ENABLED&&fabsf(navigationHeadingError())>8.0f) {
    navigationFailed("HEADING_MISMATCH");
    return false;
  }
  navigation.stage=NavStage::Driving;
  if(!navigationSegment(distance,distance,"goto-drive")) {
    navigationFailed("DRIVE_REJECTED");return false;
  }
  return true;
}
bool beginNavigationLeg() {
  // Consecutive duplicate / already reached points are skipped in a bounded loop.
  for(;;) {
    navigation.goalX=navigation.plan.points[navigation.index].x;
    navigation.goalY=navigation.plan.points[navigation.index].y;
    navigation.errorMm=navigationDistance();navigation.nextLegPending=false;
    if(navigation.errorMm>POSITION_TOL_MM)break;
    if(navigation.index+1<navigation.plan.count){++navigation.index;continue;}
    const bool distanceOnly=navigation.distanceOnlyUsed;
    if(!distanceOnly&&inspectionNavigation)return inspectionArrived();
    stopVehicle("completed");
    if(ioFault||fault!=Fault::None||control.estop){navigation.stage=NavStage::Failed;navigation.reason="STOP_OUTPUT_FAULT";return false;}
    navigation.stage=distanceOnly?NavStage::DistanceCompleted:NavStage::Arrived;
    navigation.reason=distanceOnly?"DISTANCE_ONLY":"ODOMETRY_ONLY";return true;
  }
  if(navigation.errorMm>NAV_MAX_LEG_MM+NAV_POSITION_TOL_MM){navigationFailed("LEG_LIMIT");return false;}
  const float heading=navigationHeadingError();
  // Small bearing errors are corrected by the forward line controller.
  // Avoid forcing a tiny in-place turn below gearbox breakaway speed.
  if(fabsf(heading)<=4.0f)return beginNavigationDrive();
  const float side=TRACK_EFFECTIVE_MM*0.5f*heading*DEG2RAD;
  navigation.stage=NavStage::Turning;
  if(!navigationSegment(-side,side,"goto-turn")) {
    navigationFailed("TURN_REJECTED");return false;
  }
  return true;
}
bool navigationObstacleSafe(uint32_t now) {
  (void)now;
  if(!navigationActive()||!navigation.plan.guarded)return true;
  const auto &map=navigation.plan.obstacles;
  if(navigation.plan.poseFrame!=poseFrame){navigationFailed("MAP_FRAME");return false;}
  if(ObstacleGeometry::pointBlocked(map,xMm,yMm)) {navigationFailed("OBSTACLE_NEAR");return false;}
  if(ObstacleGeometry::segmentBlocked(map,xMm,yMm,navigation.goalX,navigation.goalY)) {navigationFailed("OBSTACLE_DEVIATION");return false;}
  const float measured=.5f*(actualLeftMmS+actualRightMmS);
  const float requested=.5f*(motor[LEFT_A].targetMmS+motor[RIGHT_A].targetMmS);
  const float v=fmaxf(fabsf(measured),fabsf(requested));
  if(v>1) {
    const float direction=fabsf(measured)>5?signf(measured):signf(requested);
    const float lead=v*RouteSpeed::REACTION_SECONDS+v*v/(2*RouteSpeed::BRAKE_ACCEL)+10;
    if(ObstacleGeometry::segmentBlocked(map,xMm,yMm,xMm+direction*lead*cosf(thetaRad),yMm+direction*lead*sinf(thetaRad))) {
      navigationFailed("OBSTACLE_BRAKING");return false;
    }
  }
  return true;
}
bool startNavigationPath(const PathPlan &incoming) {
  if(LINK_DIAGNOSTIC_ONLY)return false;
  // Every route point and obstacle map belongs to the explicitly zeroed frame.
  if((requestSource!=Source::Web&&!(requestSource==Source::ScanApproach&&scanPlan.running()&&inspectionNavigation))||!poseZeroed||incoming.poseFrame!=poseFrame||
     incoming.speed>WEB_MAX_LINEAR_MM_S)return false;
  if(mode!=Mode::Idle||!canRequestMotion()||navigationActive()||routeActive())return false;
  if(!incoming.count||incoming.count>PathLimits::MAX_POINTS||!isFiniteNumber(incoming.speed)||
     incoming.speed<NAV_MIN_SPEED||incoming.speed>NAV_MAX_SPEED||
     !isFiniteNumber(xMm)||!isFiniteNumber(yMm)||!isFiniteNumber(thetaRad))return false;
  if(incoming.guarded&&(!ObstacleGeometry::valid(incoming.obstacles)||incoming.poseFrame!=poseFrame||ObstacleGeometry::pointBlocked(incoming.obstacles,xMm,yMm)))return false;
  // Revalidate the complete plan on the motor loop, including current position.
  float previousX=xMm,previousY=yMm,total=0;
  for(uint8_t i=0;i<incoming.count;i++) {
    const PathPoint &point=incoming.points[i];
    if(!isFiniteNumber(point.x)||!isFiniteNumber(point.y)||fabsf(point.x)>NAV_COORD_LIMIT_MM||fabsf(point.y)>NAV_COORD_LIMIT_MM)return false;
    const float distance=hypotf(point.x-previousX,point.y-previousY);
    if(incoming.guarded&&ObstacleGeometry::segmentBlocked(incoming.obstacles,previousX,previousY,point.x,point.y))return false;
    if(distance>NAV_MAX_LEG_MM)return false;
    total+=distance;previousX=point.x;previousY=point.y;
  }
  if(total>PathLimits::TOTAL_MM)return false;
  headingFeedback=HeadingFeedback{};navigation=NavigationState{};
  navigation.plan=incoming;navigation.speed=incoming.speed;navigationSource=requestSource;
  navigation.startX=xMm;navigation.startY=yMm;
  navigation.startedMs=millis();
  navigation.deadlineMs=uint32_t(fmaxf(float(NAV_MAX_TASK_MS),total/incoming.speed*4000+incoming.count*60000+4000));
  navigation.stage=NavStage::Settling;owner=requestSource;
  return beginNavigationLeg();
}
bool startGoto(float x,float y,float speed) {
  if(LINK_DIAGNOSTIC_ONLY)return false;
  PathPlan plan;plan.count=1;plan.speed=speed;plan.poseFrame=poseFrame;plan.points[0].x=x;plan.points[0].y=y;
  return startNavigationPath(plan);
}
void finishNavigationSegment(uint32_t now) {
  if(navigation.stage==NavStage::Turning) {
    brakeAllImmediately();mode=Mode::Idle;
    if(ioFault){navigation.stage=NavStage::Failed;navigation.reason="IO_FAULT";return;}
    navigation.stage=NavStage::Settling;navigation.settleSinceMs=now;
  } else if(navigation.stage==NavStage::Driving) {
    const float error=navigationDistance();navigation.errorMm=error;
    const bool distanceOnly=goalDrive.distanceOnly;
    if(distanceOnly){navigationFailed("COORDINATE_NOT_CONFIRMED");return;}
    navigation.distanceOnlyUsed=navigation.distanceOnlyUsed||distanceOnly;
    navigation.previousDistanceOnly=distanceOnly;
    if(error<=NAV_POSITION_TOL_MM||distanceOnly) {
      if(navigation.index+1<navigation.plan.count) {
        // Keep task ownership / page lease alive between legs. STOP cancels all.
        brakeAllImmediately();mode=Mode::Idle;
        if(ioFault){navigation.stage=NavStage::Failed;navigation.reason="IO_FAULT";return;}
        ++navigation.index;navigation.nextLegPending=true;
        navigation.goalX=navigation.plan.points[navigation.index].x;
        navigation.goalY=navigation.plan.points[navigation.index].y;navigation.errorMm=navigationDistance();
        navigation.stage=NavStage::Settling;navigation.settleSinceMs=now;
      } else {
        const bool incompletePose=navigation.distanceOnlyUsed;
        if(!incompletePose&&inspectionNavigation){inspectionArrived();return;}
        stopVehicle("completed");
        if(ioFault||fault!=Fault::None||control.estop){navigation.stage=NavStage::Failed;navigation.reason="STOP_OUTPUT_FAULT";return;}
        navigation.stage=incompletePose?NavStage::DistanceCompleted:NavStage::Arrived;
        navigation.reason=incompletePose?"DISTANCE_ONLY":"ODOMETRY_ONLY";
      }
    } else navigationFailed("POSITION_MISMATCH");
  }
}
void serviceNavigation() {
  if(!navigationActive())return;
  if(fault!=Fault::None||ioFault||control.estop) {navigation.reason="FAULT";cancelNavigation();return;}
  if(!poseZeroed||navigation.plan.poseFrame!=poseFrame){navigationFailed("MAP_FRAME");return;}
  const uint32_t now=millis();navigation.errorMm=navigationDistance();
  if(!navigationObstacleSafe(now))return;
  if(uint32_t(now-navigation.startedMs)>=navigation.deadlineMs) {navigationFailed("TOTAL_TIMEOUT");return;}
  if(ImuConfig::ENABLED&&!imu.ready(now))return; // hold step boundaries during bounded IMU pause
  // Unlike the legacy PI stall threshold, navigation needs feedback even at
  // low requested speeds. Exclude braked reversal/settling intervals.
  if(navigation.stage==NavStage::Turning||navigation.stage==NavStage::Driving) {
    for(uint8_t i=0;i<4;i++)if(CarConfig::motorEnabled(i)&&motor[i].driven&&motor[i].dutyPercent>0&&
      uint32_t(now-motor[i].driveStartMs)>=NAV_FG_TIMEOUT_MS&&
      uint32_t(now-motor[i].lastPulseMs)>=NAV_FG_TIMEOUT_MS) {
      captureMissingWheelFeedback(i,now);
      navigationFailed("FG_MISSING");return;
    }
  }
  if(navigation.stage!=NavStage::Settling)return;
  if(uint32_t(now-navigation.settleSinceMs)>=NAV_SETTLE_TIMEOUT_MS) {navigationFailed("FG_NOT_QUIET");return;}
  if(uint32_t(now-navigation.settleSinceMs)<DIRECTION_BRAKE_MS)return;
  for(uint8_t i=0;i<4;i++)if(CarConfig::motorEnabled(i)&&uint32_t(now-motor[i].lastPulseMs)<DIRECTION_QUIET_MS)return;
  if(navigation.nextLegPending)beginNavigationLeg();else beginNavigationDrive();
}
