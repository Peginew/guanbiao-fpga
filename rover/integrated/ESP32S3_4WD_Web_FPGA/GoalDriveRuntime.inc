void imuMotionFault(const char *reason);
void failRoute(const char *reason);
void initGoalDrive(float signedDistance) {
  goalDrive=GoalDriveState{};
  goalDrive.valid=true;
  goalDrive.direction=signf(signedDistance);
  goalDrive.sx=xMm;goalDrive.sy=yMm;
  float bearing=thetaRad;
  if(routeActive()) {
    bearing=route.headingRad;goalDrive.sx=route.plannedX;goalDrive.sy=route.plannedY;
    goalDrive.holdFinalHeading=true;goalDrive.finalHeading=bearing*RAD2DEG;
  }
  goalDrive.gx=goalDrive.sx+signedDistance*cosf(bearing);
  goalDrive.gy=goalDrive.sy+signedDistance*sinf(bearing);
  if(navigation.stage==NavStage::Driving) {
    goalDrive.gx=navigation.goalX;goalDrive.gy=navigation.goalY;
    if(navigation.index&&!navigation.previousDistanceOnly){goalDrive.sx=navigation.plan.points[navigation.index-1].x;goalDrive.sy=navigation.plan.points[navigation.index-1].y;}
    else if(!navigation.index){goalDrive.sx=navigation.startX;goalDrive.sy=navigation.startY;}
  }
  goalDrive.length=hypotf(goalDrive.gx-goalDrive.sx,goalDrive.gy-goalDrive.sy);
  goalDrive.tolerance=GoalControl::clamp(goalDrive.length*.03f,3,15);
  goalDrive.bestDistance=hypotf(goalDrive.gx-xMm,goalDrive.gy-yMm);
  goalDrive.launchX=xMm;goalDrive.launchY=yMm;goalDrive.progressMs=millis();
  for(uint8_t i=0;i<4;i++)goalDrive.startCount[i]=fgCount[i];
}
void failGoalDrive(const char *reason) {
  const float error=isFiniteNumber(goalDrive.error)?goalDrive.error:0;
  if(navigationActive()){recordHeading("stopped",imu.headingDeg()+error,goalDrive.recoveries);limitHeading(reason);navigationFailed(reason);return;}
  if(routeActive()){recordHeading("stopped",imu.headingDeg()+error,goalDrive.recoveries);limitHeading(reason);failRoute(reason);return;}
  stopForHeading(reason,imu.headingDeg()+error,goalDrive.recoveries);
}
bool goalQuiet(uint32_t now) {
  if(uint32_t(now-goalDrive.phaseMs)>GoalControl::SETTLE_TIMEOUT_MS){imuMotionFault("imu-fg-not-quiet");return false;}
  if(uint32_t(now-goalDrive.phaseMs)<GoalControl::SETTLE_MS)return false;
  for(uint8_t i=0;i<4;i++)if(CarConfig::motorEnabled(i)&&uint32_t(now-motor[i].lastPulseMs)<DIRECTION_QUIET_MS)return false;
  return true;
}
void beginDistanceFinish(uint32_t now) {
  (void)now;
  // Every R20 finite straight movement has a coordinate endpoint. Exhausting
  // correction attempts must stop with a failure, never become blind mileage.
  failGoalDrive("ALIGNMENT_LIMIT");
}
void beginGoalRecovery(uint32_t now,bool finalHeading=false) {
  if(goalDrive.recoveries>=GoalControl::MAX_RECOVERIES){beginDistanceFinish(now);return;}
  brakeAllImmediately();
  goalDrive.recoveryCheck=false;goalDrive.headingPending=false;
  ++goalDrive.recoveries;goalDrive.trims=0;goalDrive.finalAlign=finalHeading;
  goalDrive.phase=GoalDriveState::WaitAlign;goalDrive.phaseMs=now;goalDrive.alignMs=now;
}
void beginGoalHeadingCheck(uint32_t now) {
  // Braking is not an alignment attempt. Re-evaluate the live geometry after
  // coasting and fresh IMU frames, then charge quota only if a turn is needed.
  brakeAllImmediately();goalDrive.recoveryCheck=true;goalDrive.headingPending=false;
  goalDrive.finalAlign=false;goalDrive.phase=GoalDriveState::WaitAlign;
  goalDrive.phaseMs=now;goalDrive.alignMs=now;
}
float goalHeadingError(const GoalControl::Guidance &g) {
  const float desired=g.bearing+(goalDrive.direction<0?180:0);
  return GoalControl::wrap(desired-thetaRad*RAD2DEG);
}
void startGoalTurn(uint32_t now) {
  const auto g=GoalControl::guidance(goalDrive.sx,goalDrive.sy,goalDrive.gx,goalDrive.gy,xMm,yMm,segment.maxSpeedMmS);
  if(goalDrive.finalAlign)goalDrive.error=GoalControl::wrap(goalDrive.finalHeading-thetaRad*RAD2DEG);
  else {
    // Near a passed endpoint, a bounded reverse approach avoids a 180deg turn.
    // Direction is changed only after the wheels have stopped.
    if(g.distance<120)goalDrive.direction=fabsf(GoalControl::wrap(g.bearing-thetaRad*RAD2DEG))>90?-1:1;
    goalDrive.error=goalHeadingError(g);
  }
  if(goalDrive.recoveryCheck) {
    goalDrive.recoveryCheck=false;
    if(g.distance<=goalDrive.tolerance||fabsf(goalDrive.error)<=GoalControl::ALIGN_RELEASE_DEG) {
      goalDrive.phase=g.distance<=goalDrive.tolerance?GoalDriveState::Finish:GoalDriveState::Driving;
      goalDrive.phaseMs=now;
      // Do not renew progressMs: repeated brake-only checks must not postpone
      // the unchanged no-progress deadline indefinitely.
      return;
    }
    if(goalDrive.recoveries>=GoalControl::MAX_RECOVERIES){beginDistanceFinish(now);return;}
    ++goalDrive.recoveries;goalDrive.trims=0;
  }
  const float bound=g.distance<120&&!goalDrive.finalAlign?100:GoalControl::ABORT_DEG;
  if(fabsf(goalDrive.error)>bound){failGoalDrive("recovery-angle-limit");return;}
  goalDrive.alignTarget=imu.headingDeg()+goalDrive.error;
  goalDrive.turnStart=imu.headingDeg();goalDrive.turnDirection=signf(goalDrive.error);
  goalDrive.progressHeading=imu.headingDeg();goalDrive.headingProgressMs=now;
  goalDrive.previousTrimError=fabsf(goalDrive.error);
  goalDrive.phase=GoalDriveState::Turning;
}
bool calculateGoalDrive(uint32_t now) {
  if(!isFiniteNumber(xMm)||!isFiniteNumber(yMm)||!isFiniteNumber(thetaRad)){failGoalDrive("goal-invalid-pose");return true;}
  const auto g=GoalControl::guidance(goalDrive.sx,goalDrive.sy,goalDrive.gx,goalDrive.gy,xMm,yMm,segment.maxSpeedMmS);
  goalDrive.remaining=g.distance;goalDrive.cross=g.cross;
  const float corridor=GoalControl::clamp(goalDrive.length*.25f,150,300);
  // In distance-only finish, corridor error remains reported without more
  // corrections or radial goal chasing. A successful third alignment retains
  // normal coordinate guidance and its corridor guard.
  if(!goalDrive.distanceOnly&&(fabsf(g.cross)>corridor||g.distance>goalDrive.length+300)){failGoalDrive("path-corridor-limit");return true;}
  uint64_t pulses=0;
  for(uint8_t i=0;i<4;i++)if(CarConfig::motorEnabled(i))pulses+=uint32_t(fgCount[i]-goalDrive.startCount[i]);
  if(float(pulses)*MM_PER_PULSE*.5f>3*goalDrive.length+1000){failGoalDrive("recovery-travel-limit");return true;}
  if(goalDrive.distanceOnly) {
    const float travelled=goalDrive.direction*.5f*((avgLeftMm-goalDrive.distanceStartL)+(avgRightMm-goalDrive.distanceStartR));
    goalDrive.remaining=fmaxf(0,goalDrive.distanceBudget-travelled);
    recordHeading(goalDrive.phase==GoalDriveState::DistanceSettle?"distance-settle":"distance-only",goalDrive.distanceHeading,goalDrive.recoveries);
    if(goalDrive.phase==GoalDriveState::DistanceSettle) {
      setWheelTargets(0,0);if(!goalQuiet(now))return true;
      goalDrive.phase=GoalDriveState::Done;headingFeedback.phase="distance-completed";
      completeImuSegment(now);return true;
    }
    // No steering/re-alignment in this phase. Sensor, feedback, time, total
    // wheel-travel and gross unexpected body rotation guards remain active.
    if(fabsf(GoalControl::wrap(imu.headingDeg()-goalDrive.distanceHeading))>GoalControl::ABORT_DEG){failGoalDrive("distance-heading-limit");return true;}
    if(goalDrive.remaining<=goalDrive.tolerance) {
      brakeAllImmediately();goalDrive.phase=GoalDriveState::DistanceSettle;goalDrive.phaseMs=now;return true;
    }
    if(goalDrive.remaining<goalDrive.bestDistance-5){goalDrive.bestDistance=goalDrive.remaining;goalDrive.progressMs=now;}
    else if(uint32_t(now-goalDrive.progressMs)>GoalControl::PROGRESS_MS){failGoalDrive("goal-no-progress");return true;}
    const float creep=fminf(segment.maxSpeedMmS,45);
    float speed=fminf(segment.maxSpeedMmS,fmaxf(creep,RouteSpeed::brakingSpeed(goalDrive.remaining)));
    if(hypotf(xMm-goalDrive.launchX,yMm-goalDrive.launchY)<180)speed=fminf(speed,60);
    setWheelTargets(speed*goalDrive.direction,speed*goalDrive.direction);return true;
  }
  if(goalDrive.phase==GoalDriveState::Driving||
     (goalDrive.phase==GoalDriveState::WaitAlign&&goalDrive.recoveryCheck)) {
    if(g.distance<goalDrive.bestDistance-5){goalDrive.bestDistance=g.distance;goalDrive.progressMs=now;}
    else if(uint32_t(now-goalDrive.progressMs)>GoalControl::PROGRESS_MS){failGoalDrive("goal-no-progress");return true;}
  }
  if(goalDrive.phase==GoalDriveState::WaitAlign) {
    setWheelTargets(0,0);recordHeading("recovery-brake",imu.headingDeg()+goalDrive.error,goalDrive.recoveries);
    if(goalQuiet(now))startGoalTurn(now);
    return true;
  }
  if(goalDrive.phase==GoalDriveState::Turning||goalDrive.phase==GoalDriveState::SettleAlign) {
    goalDrive.error=goalDrive.alignTarget-imu.headingDeg();
    recordHeading("recovery-turn",goalDrive.alignTarget,goalDrive.recoveries);
    if(uint32_t(now-goalDrive.alignMs)>GoalControl::ALIGN_TIMEOUT_MS){failGoalDrive("recovery-timeout");return true;}
    if(goalDrive.phase==GoalDriveState::SettleAlign) {
      setWheelTargets(0,0);if(!goalQuiet(now))return true;
      if(fabsf(goalDrive.error)<=GoalControl::TURN_TOL_DEG) {
        goalDrive.phase=goalDrive.finalAlign?GoalDriveState::Finish:GoalDriveState::Driving;
        goalDrive.headingPending=false;
        goalDrive.phaseMs=now;goalDrive.progressMs=now;goalDrive.bestDistance=g.distance;
        goalDrive.launchX=xMm;goalDrive.launchY=yMm;return true;
      }
      if(goalDrive.trims>=GoalControl::MAX_TRIMS||fabsf(goalDrive.error)>goalDrive.previousTrimError-.5f){beginGoalRecovery(now,goalDrive.finalAlign);return true;}
      ++goalDrive.trims;goalDrive.previousTrimError=fabsf(goalDrive.error);
      goalDrive.turnStart=imu.headingDeg();goalDrive.turnDirection=signf(goalDrive.error);
      goalDrive.progressHeading=imu.headingDeg();goalDrive.headingProgressMs=now;goalDrive.phase=GoalDriveState::Turning;
    }
    const float direction=goalDrive.turnDirection;
    if(goalDrive.error*direction<=0||fabsf(goalDrive.error)<=GoalControl::brakeLead(direction,imu.rateDegS,float(uint32_t(now-imu.lastSampleMs))*.001f)) {
      brakeAllImmediately();goalDrive.phase=GoalDriveState::SettleAlign;goalDrive.phaseMs=now;return true;
    }
    if((imu.headingDeg()-goalDrive.turnStart)*direction<-5){imuMotionFault("imu-turn-direction");return true;}
    if(fabsf(imu.headingDeg()-goalDrive.progressHeading)>.5f){goalDrive.progressHeading=imu.headingDeg();goalDrive.headingProgressMs=now;}
    else if(uint32_t(now-goalDrive.headingProgressMs)>ImuMotion::NO_YAW_PROGRESS_MS){turnResponseFault(now);return true;}
    float l,r;ImuMotion::turn(goalDrive.error,fminf(segment.maxSpeedMmS,30),l,r);setWheelTargets(l,r);return true;
  }
  if(goalDrive.phase==GoalDriveState::Finish) {
    setWheelTargets(0,0);recordHeading("position-settle",imu.headingDeg(),goalDrive.recoveries);
    if(!goalQuiet(now))return true;
    if(g.distance>goalDrive.tolerance+5){beginGoalRecovery(now);return true;}
    if(goalDrive.holdFinalHeading) {
      goalDrive.error=GoalControl::wrap(goalDrive.finalHeading-thetaRad*RAD2DEG);
      if(fabsf(goalDrive.error)>GoalControl::TURN_TOL_DEG){beginGoalRecovery(now,true);return true;}
    }
    goalDrive.phase=GoalDriveState::Done;headingFeedback.phase="completed";completeImuSegment(now);return true;
  }
  if(g.distance<=goalDrive.tolerance) {
    brakeAllImmediately();goalDrive.phase=GoalDriveState::Finish;goalDrive.phaseMs=now;return true;
  }
  goalDrive.error=goalHeadingError(g);imuMotion.targetDeg=imu.headingDeg()+goalDrive.error;
  recordHeading("line-follow",imuMotion.targetDeg,goalDrive.recoveries);
  const float headingError=fabsf(goalDrive.error);
  if(headingError<=GoalControl::ALIGN_RELEASE_DEG||
     (goalDrive.headingPending&&goalDrive.headingTriggerSign!=signf(goalDrive.error)))goalDrive.headingPending=false;
  if(headingError>GoalControl::ALIGN_TRIGGER_DEG&&!goalDrive.headingPending) {
    goalDrive.headingPending=true;goalDrive.headingTriggerMs=now;
    goalDrive.headingTriggerSign=signf(goalDrive.error);
  }
  if(headingError>=GoalControl::ALIGN_BRAKE_DEG||
     (goalDrive.headingPending&&uint32_t(now-goalDrive.headingTriggerMs)>=GoalControl::ALIGN_CONFIRM_MS)) {
    beginGoalHeadingCheck(now);return true;
  }
  // Continuous braking profile instead of an abrupt speed drop at 120mm.
  // Do not demand a sub-creep base speed while the endpoint is still outside
  // its tolerance; completion always brakes, never snaps the pose to goal.
  const float creep=fminf(segment.maxSpeedMmS,45);
  float speed=fminf(segment.maxSpeedMmS,fmaxf(creep,RouteSpeed::brakingSpeed(g.distance)));
  if(hypotf(xMm-goalDrive.launchX,yMm-goalDrive.launchY)<180)speed=fminf(speed,60);
  if(goalDrive.headingPending)speed=fminf(speed,60);
  // Keep the robot slower while it is still reducing a small heading error.
  speed=fmaxf(fminf(creep,60),speed*GoalControl::clamp(1-fabsf(goalDrive.error)*.035f,.6f,1));
  float l,r;
  // Keep proportional heading correction; damp with a filtered yaw rate and
  // bound how fast the differential command can switch between left/right.
  const float base=speed*goalDrive.direction;
  GoalControl::steer(base,goalDrive.error,goalDrive.steering.rate,l,r);
  const float limit=fminf(60,fmaxf(0,fabsf(base)-25));
  const float delta=StraightStability::smooth(goalDrive.steering,.5f*(r-l),imu.rateDegS,now,limit);
  l=base-delta;r=base+delta;
  setWheelTargets(l,r);return true;
}
