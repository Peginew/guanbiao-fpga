// UART1, the inspection executor and motor ownership belong only to robotLoop.
FpgaUartLink fpgaLink(inspection);
uint32_t fpgaEpoch(){return inspection.motionEpoch();}
InspectionExecutor::Sensors inspectionSensors(){
  InspectionExecutor::Sensors s;const uint32_t now=millis();
  s.hardware=hardwareReady;s.fault=ioFault||fault!=Fault::None;s.estop=control.estop;
  s.imuReady=imu.ready(now);s.imuAgeMs=imu.frames?uint32_t(now-imu.lastSampleMs):0xffffffffu;s.imuSample=imu.frames;
  s.poseValid=poseZeroed;s.poseFrame=poseFrame;s.headingDeg=imu.headingDeg();s.rateDegS=imu.rateDegS;
  s.leftSpeed=actualLeftMmS;s.rightSpeed=actualRightMmS;s.leftTravel=avgLeftMm;s.rightTravel=avgRightMm;
  s.navOwner=navigationActive()||routeActive()||(owner!=Source::Inspection&&(mode==Mode::Manual||mode==Mode::Pulse));
  s.braked=true;s.fgQuietMs=0xffffffffu;uint32_t counts[4];snapshotFg(counts);
  for(uint8_t i=0;i<2;i++){
    const uint32_t quiet=counts[i]!=motor[i].lastCount?0:uint32_t(now-motor[i].lastPulseMs);
    if(quiet<s.fgQuietMs)s.fgQuietMs=quiet;
    s.braked=s.braked&&!motor[i].driven&&!motor[i].switching&&fabsf(motor[i].targetMmS)<.001f&&fabsf(motor[i].rampMmS)<.001f&&motor[i].dutyPercent==0&&gpio_get_level(static_cast<gpio_num_t>(PIN_BRK[i]))==LOW;
  }
  s.linkFresh=fpgaLink.stateUsable(now);return s;
}
bool inspectionOutputPermit(){
  const uint32_t now=millis();
  if(!inspection.armed()||!inspection.calibrated()||!hardwareReady||ioFault||fault!=Fault::None||control.estop||control.state!=Stage1Control::Monitor||!poseZeroed||!imu.ready(now)||!fpgaLink.executionLinkFresh(now))return false;
  if(owner==Source::Inspection)return inspection.active()&&inspection.driving()&&!inspection.output().brake&&inspection.context().poseFrame==poseFrame;
  if(owner==Source::ScanApproach)return scanPlan.running()&&inspectionNavigation&&navigationActive()&&!inspection.active();
  return owner==Source::Web&&!inspection.active()&&((inspectionNavigation&&navigationActive())||(consoleMode&&!scanPlan.running()&&!inspectionArrivalPending));
}
void invalidateFpgaObservationOnStop(){
  const auto f=fpgaLink.snapshot(millis());
  fpgaLink.cancelTask(f.taskId,f.pointId,f.configId,f.observationEpoch,millis());
  if(inspection.active()||inspection.actionActive())inspection.cancel(fault==Fault::Imu?InspectionExecutor::Reason::IMU_FAULT:fault!=Fault::None||ioFault?InspectionExecutor::Reason::OUTPUT_FAULT:InspectionExecutor::Reason::USER_CANCEL);
  else inspection.revokeArm();
  inspectionNavigation=inspectionArrivalPending=false;pendingInspectionTask=pendingInspectionPoint=0;
  consoleMode=false;
  if(scanPlan.running())scanPlan.stop();scanLaunchPending=scanAlignStarted=scanDwellStarted=false;
}
void openFpgaPort(uint32_t now){
  // Exactly one writer; no software TX ring. An idle 128-byte hardware FIFO
  // can accept the complete32-byte frame without waiting for wire drain.
  Serial1.setRxBufferSize(1024);Serial1.setTxBufferSize(0);
  Serial1.begin(115200,SERIAL_8N1,FPGA_RX,RESERVED_TX);
  gpio_pullup_en(static_cast<gpio_num_t>(FPGA_RX));uartReady=true;fpgaLink.beginAttempt(esp_random(),now);
}
bool fpgaSensorStationary(uint32_t now){return InspectionExecutor::rawQuiet(inspectionSensors())&&inspection.stationaryAge(now)>=gb4::cfg::PARK_CONFIRM_MS;}
void serviceInspectionOutputs(){
  if(owner!=Source::Inspection)return;
  const auto o=inspection.output();
  if(!inspection.active()||o.brake||!inspectionOutputPermit()){
    brakeAllImmediately();mode=Mode::Idle;
    if(!inspection.active()&&!inspectionArrivalPending)owner=Source::None;
    return;
  }
  mode=Mode::Segment;
  const float differential=o.turnDegS*DEG2RAD*TRACK_EFFECTIVE_MM*.5f;
  setWheelTargets(o.linearMmS-differential,o.linearMmS+differential);
}
void confirmInspectionDriveStarted(){
  if(owner!=Source::Inspection||!inspection.driving()||!inspectionOutputPermit())return;
  bool actual=false;
  for(uint8_t i=0;i<2;i++)actual=actual||(motor[i].driven&&motor[i].dutyPercent>0&&gpio_get_level(static_cast<gpio_num_t>(PIN_BRK[i]))==HIGH);
  if(actual){const auto before=inspection.motionEpoch();inspection.notifyDriveStarted();if(before!=inspection.motionEpoch())fpgaLink.actuatorStateChanged();}
}
bool localInspectionCalibration(bool confirmed){return inspection.confirmCalibration(confirmed,inspectionSensors());}
bool localInspectionArm(bool enabled,bool forConsole){
  if(!enabled){stopVehicle("inspection-disarm");return true;}
  if(consoleMode!=forConsole)stopVehicle("control-owner-change");
  if(inspection.active()||scanPlan.running()||inspectionNavigation||inspectionArrivalPending||navigationActive()||routeActive())return false;
  const bool ok=inspection.armLocal(true,inspectionSensors());if(ok){consoleMode=forConsole;portENTER_CRITICAL(&webMux);webLeaseToken[0]=0;portEXIT_CRITICAL(&webMux);++webEpoch;}return ok;
}
bool startFpgaTask(uint16_t task,uint16_t point,uint16_t config,gb4::TaskMode taskMode=gb4::TaskMode::FORMAL_REVIEW){
  if(mode!=Mode::Idle||navigationActive()||routeActive()||inspectionNavigation||inspectionArrivalPending)return false;
  if(!fpgaSensorStationary(millis()))return false;
  fpgaLink.configurePlan(scanPlan.id()?scanPlan.id():1,4,10000,taskMode);
  const bool accepted=fpgaLink.startTask(task,point,config,fpgaEpoch(),millis(),taskMode);
  if(accepted){
    navigation.nextLegPending=false;cancelRoute("inspection-takeover");owner=Source::Inspection;
    portENTER_CRITICAL(&webMux);webLeaseToken[0]=0;portEXIT_CRITICAL(&webMux);++webEpoch;
  }
  return accepted;
}
bool cancelFpgaTask(uint16_t task,uint16_t point,uint16_t config,uint32_t epoch){
  const bool accepted=fpgaLink.cancelTask(task,point,config,epoch,millis());
  if(accepted){inspection.cancel();brakeAllImmediately();mode=Mode::Idle;owner=Source::None;inspectionNavigation=inspectionArrivalPending=false;++webEpoch;}
  return accepted;
}
bool startInspectionGoto(float x,float y,float speed){
  if(!inspection.armed()||!inspection.calibrated()||inspection.active()||navigationActive()||routeActive()||mode!=Mode::Idle||!poseZeroed||!fpgaLink.executionLinkFresh(millis()))return false;
  const auto f=fpgaLink.snapshot(millis());if(f.taskId==65535)return false;
  pendingInspectionTask=f.taskId?uint16_t(f.taskId+1):1;pendingInspectionPoint=scanPlan.running()?scanPlan.current().id:1;inspectionNavigation=true;
  const bool ok=startGoto(x,y,speed);
  if(!ok){inspectionNavigation=false;pendingInspectionTask=pendingInspectionPoint=0;}
  return ok;
}
bool inspectionArrived(){
  if(!inspectionNavigation||!pendingInspectionTask||!pendingInspectionPoint)return false;
  brakeAllImmediately();if(ioFault||fault!=Fault::None||control.estop)return false;
  navigation.nextLegPending=false;navigation.stage=NavStage::Arrived;navigation.reason="ODOMETRY_ONLY";
  cancelRoute("inspection-takeover");route=RouteState{};
  inspectionNavigation=false;inspectionArrivalPending=true;inspectionArrivalMs=millis();
  inspectionArrivalHeading=imu.headingDeg();scanAlignStarted=scanDwellStarted=false;
  stoppedSinceMs=millis();mode=Mode::Idle;owner=Source::Inspection;
  portENTER_CRITICAL(&webMux);webLeaseToken[0]=0;portEXIT_CRITICAL(&webMux);++webEpoch;
  return true;
}
bool startScanQueue(ScanPlan::Mode scanMode,bool continuous){
  if(consoleMode||mode!=Mode::Idle||navigationActive()||routeActive()||inspection.active()||inspectionArrivalPending||!inspection.armed()||!inspection.calibrated()||!poseZeroed||!fpgaLink.executionLinkFresh(millis())||!scanPlan.begin(scanMode,continuous))return false;
  scanLaunchPending=true;return true;
}
bool continueScanQueue(){
  if(mode!=Mode::Idle||navigationActive()||inspection.active()||!inspection.armed()||!inspection.calibrated()||!fpgaLink.executionLinkFresh(millis())||!scanPlan.manualContinue())return false;
  scanLaunchPending=true;return true;
}
void serviceScanQueue(uint32_t now){
  if(scanLaunchPending){
    scanLaunchPending=false;
    scanPointAt=now;fpgaLink.beginPointScope(scanPlan.id(),scanPlan.current().id,poseFrame,now);
    const auto saved=requestSource;requestSource=Source::ScanApproach;
    const bool started=startInspectionGoto(scanPlan.current().x,scanPlan.current().y,40);requestSource=saved;
    if(!started){scanPlan.fail();stopVehicle("scan-approach-rejected");return;}
  }
  if(scanPlan.running()&&uint32_t(now-scanPointAt)>=600000){scanPlan.fail();stopVehicle("scan-point-total-timeout");return;}
  if(inspectionArrivalPending){
    if(now-inspectionArrivalMs>=45000){scanPlan.fail();stopVehicle("scan-arrival-timeout");return;}
    if(!fpgaSensorStationary(now)){scanDwellStarted=false;return;}
    if(scanPlan.running()&&!scanAlignStarted){
      scanPlan.aligning();scanAlignStarted=true;
      const float delta=ScanPlan::wrap(scanPlan.firstBearing()-thetaRad*RAD2DEG);
      if(fabsf(delta)>.3f){const auto f=fpgaLink.snapshot(now);InspectionExecutor::Context c{f.localSession,f.peerSession,f.linkNonce,fpgaEpoch(),poseFrame,pendingInspectionTask,pendingInspectionPoint,4};if(!inspection.beginAlignment(c,delta,inspectionSensors(),now)){scanPlan.fail();stopVehicle("scan-alignment-rejected");return;}}
    }
    if(inspection.aligning()){
      if(inspection.feedback().status==InspectionExecutor::Status::FAULT){scanPlan.fail();stopVehicle("scan-alignment-failed");return;}
      if(inspection.actionActive())return;
      inspection.finishTask();
    }
    // Six seconds is a genuine continuously parked local inhibit, never a delay().
    if(!scanDwellStarted){scanDwellStarted=true;scanDwellAt=now;return;}
    if(now-scanDwellAt<6000)return;
    const auto m=scanPlan.running()&&scanPlan.mode()==ScanPlan::DiagnosticCandidates?gb4::TaskMode::DIAGNOSTIC_CONTINUOUS:gb4::TaskMode::FORMAL_REVIEW;
    fpgaLink.configurePlan(scanPlan.id()?scanPlan.id():1,scanPlan.running()?scanPlan.maxSteps():4,10000,m);
    if(fpgaLink.startTask(pendingInspectionTask,pendingInspectionPoint,4,fpgaEpoch(),now,m)){
      inspectionArrivalPending=false;pendingInspectionTask=pendingInspectionPoint=0;owner=Source::Inspection;scanPlan.aligned();++webEpoch;
    }
  }
  const auto f=fpgaLink.snapshot(now);
  if(scanPlan.stage()==ScanPlan::Inspect&&f.taskState==FpgaUartLink::Completed){
    ScanPlan::Reading r;r.candidate=f.candidateRead&&f.pointId==scanPlan.current().id&&f.poseFrame==poseFrame&&fpgaSensorStationary(now);r.formal=false;r.rawQ16=f.rawBarQ16;r.source=f.readSourceFrame;r.session=f.peerSession;r.nonce=f.linkNonce;r.pose=f.poseFrame;r.epoch=f.observationEpoch;
    if(!scanPlan.record(r)){scanPlan.fail();stopVehicle("scan-result-context");return;}
    if(scanPlan.mayAdvance()&&scanPlan.advance()&&scanPlan.stage()==ScanPlan::Approach)scanLaunchPending=true;
    if(!scanPlan.running()){brakeAllImmediately();mode=Mode::Idle;owner=Source::None;}
    ++webEpoch;
  }
  if(scanPlan.stage()==ScanPlan::Inspect&&f.taskState==FpgaUartLink::Failed){scanPlan.fail();stopVehicle("scan-task-failed");}
}
void serviceFpgaLink(){
  const uint32_t now=millis();const auto beforeEpoch=inspection.motionEpoch();const auto beforeStatus=inspection.feedback().status;
  fpgaLink.vehicleState(inspectionSensors(),fpgaEpoch(),now);
  unsigned budget=144;while(budget--&&Serial1.available())fpgaLink.feed(uint8_t(Serial1.read()),now);
  fpgaLink.expire(now);
  if(fpgaLink.needsSession()){
    if(owner==Source::Inspection||inspectionNavigation||inspectionArrivalPending)stopVehicle("fpga-link-lost");
    fpgaLink.beginAttempt(esp_random(),now);
  }
  if(inspectionNavigation&&!inspectionOutputPermit()){
    // Initial ownership is Web; a lost permit must cancel, never resume later.
    if(!inspection.armed()||!imu.ready(now)||!fpgaLink.executionLinkFresh(now))stopVehicle("inspection-goto-permit-lost");
  }
  serviceScanQueue(now);
  // Safety stops bypass the50ms PID cadence; new motion starts only in controlStep.
  if(owner==Source::Inspection&&(inspection.output().brake||!inspection.active())){
    brakeAllImmediately();mode=Mode::Idle;if(!inspection.active()&&!inspectionArrivalPending)owner=Source::None;
  }
  if(beforeEpoch!=inspection.motionEpoch()||beforeStatus!=inspection.feedback().status)fpgaLink.actuatorStateChanged();
  // Do not consume nextTx or freeze telemetry while another frame is on wire.
  // RX, expiry and real safety brakes above run even while TX remains busy.
  if(uart_wait_tx_done(UART_NUM_1,0)==ESP_OK&&Serial1.availableForWrite()>=int(FpgaWire::SIZE)){
    uint8_t frame[FpgaWire::SIZE];if(fpgaLink.nextTx(now,frame)&&Serial1.write(frame,sizeof(frame))!=sizeof(frame))fpgaLink.transportFailure();
  }
}
