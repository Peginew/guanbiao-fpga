bool anyMotion();
bool imuQuiet() {
  if(mode!=Mode::Idle||routeActive()||navigationActive()||inspection.active()||inspectionArrivalPending||control.state!=Stage1Control::Monitor)return false;
  for(uint8_t i=0;i<4;i++)if(CarConfig::motorEnabled(i)&&(motor[i].driven||motor[i].switching||
    uint32_t(millis()-motor[i].lastPulseMs)<DIRECTION_QUIET_MS))return false;
  return uint32_t(millis()-stoppedSinceMs)>=DIRECTION_BRAKE_MS;
}
void imuMotionFault(const char *reason) {
  poseZeroed=false;
  if(fault==Fault::None){
    imuFault.valid=true;imuFault.age=imu.frames?uint32_t(millis()-imu.lastSampleMs):0xffffffffu;
    imuFault.roll=imu.roll;imuFault.pitch=imu.pitch;imuFault.bad=imu.badFrames;imuFault.timeouts=imu.timeouts;
    fault=Fault::Imu;faultSource=reason;
  }
  stopVehicle(reason);statusPending=true;
}
void turnResponseFault(uint32_t now) {
    poseZeroed=false;
    // Fresh angle frames with no turn response are not a serial timeout.
    // Freeze command/FG evidence before braking destroys the live output state.
    imuFault.valid=true;imuFault.age=uint32_t(now-imu.lastSampleMs);
    imuFault.roll=imu.roll;imuFault.pitch=imu.pitch;
    imuFault.travelL=avgLeftMm-segment.startL;imuFault.travelR=avgRightMm-segment.startR;
    imuFault.command=fmaxf(fabsf(motor[LEFT_A].targetMmS),fabsf(motor[RIGHT_A].targetMmS));
    imuFault.duty=fmaxf(motor[LEFT_A].dutyPercent,motor[RIGHT_A].dutyPercent);
    fault=Fault::MotionResponse;faultSource="turn-response-missing";
    stopVehicle("turn-response-missing");statusPending=true;
}
void openImuPort(uint32_t now) {
  Serial2.setRxBufferSize(1024);Serial2.setTxBufferSize(256);
  Serial2.begin(ImuConfig::BAUD,SERIAL_8N1,ImuConfig::RX,ImuConfig::TX);
  gpio_pullup_en(static_cast<gpio_num_t>(ImuConfig::RX));
  imuLink.portMs=now;
}
bool restartImuLink(bool automatic=false) {
  const uint32_t now=millis();
  if(!ImuConfig::ENABLED||!imuQuiet()||imu.ready(now)||uint32_t(now-imuLink.lastRestartMs)<2000)return false;
  stopVehicle("imu-reconnect"); // revoke pending commands; never resume a task
  poseZeroed=false;
  // Keep the UART driver alive. Reset only the read transaction/parser and
  // require version + stationary warmup. No module register writes.
  imu.restartTransport();imuLink.portMs=now;
  imuLink.lastRestartMs=now;++imuLink.restarts;
  if(automatic)++imuLink.autoRestarts;
  statusPending=true;return true;
}
void serviceImu() {
  if(!ImuConfig::ENABLED)return;
  const uint32_t now=millis();const bool quiet=imuQuiet();
  // Drain pending replies before processing the request timeout.
  // Bounded RX and non-blocking TX: motor STOP/lease/control work keeps running.
  unsigned budget=128;
  while(budget--&&Serial2.available())imu.feed(uint8_t(Serial2.read()),now,quiet,thetaRad*RAD2DEG);
  imu.tick(now,quiet);
  // A lost sensor reference also invalidates an idle coordinate frame.
  // Fresh warmup may restore manual driving, but only explicit ZERO restores GOTO.
  if(poseZeroed&&!imu.usable(now))poseZeroed=false;
  if(!imu.usable(now)&&(mode==Mode::Manual||mode==Mode::Segment||routeActive()||navigationActive()||inspection.active()||inspectionArrivalPending))
    imuMotionFault(imu.reason(now));
  // Version reads continue once per second until the module replies. Do not
  // repeatedly end/begin UART: that discards late power-up replies and adds
  // driver teardown to the same loop which owns motor deadlines.
  if(uint32_t(now-imuLink.portMs)<1000)return; // module power-up settling
  if(Serial2.availableForWrite()>=8) {
    uint8_t command[8];const size_t n=imu.request(now,command);
    if(n && Serial2.write(command,n)!=n)imuMotionFault("imu-uart-write");
  }
}
void initImuSegment(float left,float right) {
  imuMotion=ImuMotionState{};
  goalDrive=GoalDriveState{};
  imuMotion.startDeg=imu.headingDeg();
  imuMotion.progressHeading=imu.headingDeg();imuMotion.progressMs=millis();
  if(fabsf(left-right)<0.001f) {
    imuMotion.kind=ImuMotionState::Straight;
    imuMotion.targetDeg=imu.headingDeg();
    // Planned route heading stays fixed across its straight legs.
    if(routeActive())imuMotion.targetDeg+=ImuHeading::wrap(route.headingRad*RAD2DEG-thetaRad*RAD2DEG);
    else if(navigation.stage==NavStage::Driving)
      imuMotion.targetDeg+=ImuHeading::wrap(atan2f(navigation.goalY-yMm,navigation.goalX-xMm)*RAD2DEG-thetaRad*RAD2DEG);
    initGoalDrive(left);
  } else if(fabsf(left+right)<0.001f) {
    imuMotion.kind=ImuMotionState::Turn;
    imuMotion.targetDeg=imu.headingDeg()+(right-left)/TRACK_EFFECTIVE_MM*RAD2DEG;
    imuMotion.turnDirection=signf(imuMotion.targetDeg-imuMotion.startDeg);
  }
}
void completeImuSegment(uint32_t now) {
  if(routeActive())finishRouteSegment(now);
  else if(navigationActive())finishNavigationSegment(now);
  else {stopVehicle("completed");statusPending=true;}
}
// Returns true when this module owns the segment's targets, including settling.
bool calculateImuSegment(uint32_t now) {
  if(!ImuConfig::ENABLED || imuMotion.kind==ImuMotionState::WheelArc)return false;
  if(imuMotion.kind==ImuMotionState::Straight)return calculateGoalDrive(now);
  const float error=imuMotion.targetDeg-imu.headingDeg();
  recordHeading(imuMotion.settling?"settling":imuMotion.headingOnly?"correction":
    imuMotion.kind==ImuMotionState::Straight?"straight":"turn",imuMotion.targetDeg,imuMotion.corrections);
  if(imuMotion.settling) {
    setWheelTargets(0,0);
    if(uint32_t(now-imuMotion.settleMs)>ImuMotion::SETTLE_TIMEOUT_MS){imuMotionFault("imu-fg-not-quiet");return true;}
    if(uint32_t(now-imuMotion.settleMs)<ImuMotion::SETTLE_MS)return true;
    for(uint8_t i=0;i<4;i++)if(CarConfig::motorEnabled(i)&&uint32_t(now-motor[i].lastPulseMs)<DIRECTION_QUIET_MS)return true;
    if(fabsf(error)<=ImuMotion::TURN_TOL_DEG) {headingFeedback.phase="completed";completeImuSegment(now);return true;}
    // At most two improving trims, including a reverse trim after overshoot.
    // Direction changes are allowed only after the brake/FG quiet interval.
    if(imuMotion.corrections>=ImuMotion::MAX_CORRECTIONS||
       (imuMotion.corrections&&fabsf(error)>imuMotion.previousTrimError-.5f)) {
      stopForHeading("turn-not-converged",imuMotion.targetDeg,imuMotion.corrections);return true;
    }
    imuMotion.previousTrimError=fabsf(error);
    ++imuMotion.corrections;imuMotion.settling=false;imuMotion.headingOnly=true;
    imuMotion.turnDirection=signf(error);
    imuMotion.startDeg=imu.headingDeg();
    imuMotion.progressHeading=imu.headingDeg();imuMotion.progressMs=now;
  }
  float l=0,r=0;
  // Use measured yaw change (not unverified gyro-Z) to anticipate braking.
  // Never reverse immediately at target crossing: brake and settle first.
  const float direction=imuMotion.turnDirection;
  const bool crossed=error*direction<=0;
  const float toward=fmaxf(0,imu.rateDegS*direction);
  const float ageSeconds=float(uint32_t(now-imu.lastSampleMs))*0.001f;
  const float lead=clampf(toward*(0.12f+ageSeconds),ImuMotion::BRAKE_ENTRY_DEG,4.0f);
  if(crossed||fabsf(error)<=lead) {
    brakeAllImmediately();imuMotion.settling=true;imuMotion.settleMs=now;return true;
  }
  const float requested=imuMotion.targetDeg-imuMotion.startDeg;
  if((imu.headingDeg()-imuMotion.startDeg)*signf(requested)<-5.0f) {
    imuMotionFault("imu-turn-direction");return true;
  }
  if(fabsf(imu.headingDeg()-imuMotion.progressHeading)>=0.5f) {
    imuMotion.progressHeading=imu.headingDeg();imuMotion.progressMs=now;
  } else if(uint32_t(now-imuMotion.progressMs)>ImuMotion::NO_YAW_PROGRESS_MS) {
    turnResponseFault(now);return true;
  }
  const float travel=fmaxf(fabsf(avgLeftMm-segment.startL),fabsf(avgRightMm-segment.startR));
  const float nominal=fmaxf(fabsf(segment.goalL),fabsf(segment.goalR));
  if(travel>3.0f*nominal+150.0f){imuMotionFault("imu-wheel-travel");return true;}
  const float speed=imuMotion.headingOnly?fminf(segment.maxSpeedMmS,ImuMotion::CORRECTION_MAX_SPEED):segment.maxSpeedMmS;
  ImuMotion::turn(error,speed,l,r);setWheelTargets(l,r);return true;
}
