bool canRequestMotion() {
  if(!inspection.armed()||!inspection.calibrated()||(!inspectionNavigation&&!consoleMode)||inspection.active()||!poseZeroed||!fpgaLink.executionLinkFresh(millis()))return false;
  if(consoleMode&&(scanPlan.running()||inspectionArrivalPending))return false;
  if(requestSource!=Source::Web&&!(requestSource==Source::ScanApproach&&scanPlan.running()))return false;
  if(ImuConfig::ENABLED&&!imu.ready(millis())&&
    !(mode==Mode::Manual&&owner==requestSource&&imu.usable(millis())))return false;
  if(routeActive()&&!routeInternal)return false;
  if(navigationActive()&&!navigationInternal)return false;
  if (!hardwareReady || ioFault || fault!=Fault::None || control.estop ||
      control.state!=Stage1Control::Monitor || mode==Mode::Pulse) return false;
  return mode==Mode::Idle || owner==requestSource;
}
bool anyMotion() { return mode!=Mode::Idle || control.state==Stage1Control::Running || navigationActive() || routeActive(); }
void snapshotFg(uint32_t counts[4]) {
  noInterrupts();for(uint8_t i=0;i<4;i++)counts[i]=fgCount[i];interrupts();
}
bool stopOutputs() { brakeAllImmediately();return !ioFault; }
void stopTest() { stopVehicle(); }
void clearAllFaults() {
  stopVehicle("clear");control.clear();
  if(ImuConfig::ENABLED && (fault==Fault::Imu||fault==Fault::MotionResponse) && !imu.ready(millis()))return;
  if(!ioFault) {fault=Fault::None;faultSource="none";}
  else control.emergencyStop();
}
void printLegacyStatus() {
  console.printf("HEADING phase=%s target=%.2f actual=%.2f error=%.2f corrections=%u limited=%u residual=%.2f note=%s tolerance=%.1fdeg\n",headingFeedback.phase,headingFeedback.target,headingFeedback.actual,headingFeedback.error,headingFeedback.corrections,headingFeedback.limited,headingFeedback.residual,headingFeedback.note,ImuMotion::TURN_TOL_DEG);
  if(goalDrive.valid)console.printf("PATH remaining=%.2f cross=%.2f alignments=%u distanceOnly=%u trims=%u/2 phase=%u\n",goalDrive.remaining,goalDrive.cross,goalDrive.recoveries,goalDrive.distanceOnly,goalDrive.trims,unsigned(goalDrive.phase));
  if(navigation.feedbackMotor)console.printf("FG_FAILURE M%u target=%.1f duty=%.1f silenceMs=%lu count=%lu\n",unsigned(navigation.feedbackMotor),navigation.feedbackTarget,navigation.feedbackDuty,(unsigned long)navigation.feedbackSilenceMs,(unsigned long)navigation.feedbackCount);
  console.printf("HEADING_SOURCE=UART2-IMU ready=%u heading=%.2f rate=%.2f RX=GPIO2 TX=GPIO1\n",imu.ready(millis()),imu.headingDeg(),imu.rateDegS);
  console.printf("STATUS mode=%s fault=%s x=%.1f y=%.1f yaw=%.1f L=%.1f R=%.1f",
    modeName(),faultName(),xMm,yMm,thetaRad*RAD2DEG,actualLeftMmS,actualRightMmS);
  for(uint8_t i=0;i<4;i++)console.printf(" %s{count=%lu,speed=%.1f,duty=%.0f}",
    WHEEL_NAME[i],(unsigned long)motor[i].lastCount,motor[i].measuredMmS,motor[i].dutyPercent);
  console.println();
  console.printf("STOP_SOURCE=%s FAULT_SOURCE=%s BOOT_SESSION=%s\n",stopSource,faultSource,bootSession);
  console.printf("NAV=%s TARGET_X=%.1f TARGET_Y=%.1f ERROR_MM=%.1f REASON=%s (odometry estimate)\n",navigationStageName(),navigation.goalX,navigation.goalY,navigation.errorMm,navigation.reason);
}
void printStatus() {
  portENTER_CRITICAL(&webMux);const bool httpOk=httpStarted;portEXIT_CRITICAL(&webMux);
  uint32_t counts[4];snapshotFg(counts);
  console.printf("STATE=%s ARM_MASK=%u ACTIVE_MASK=%u READY=%u UART_OK=%u IO_FAULT=%u ESTOP=%u BAUD=%lu LEVEL=%d RX_M1=%lu RX_FWD=%lu BYTES=%lu LINES=%lu BAD=%lu STALE=%lu\n",
    control.state==Stage1Control::Running?"RUNNING":control.state==Stage1Control::Armed?"ARMED":"MONITOR",
    control.armedMask,control.activeMask,hardwareReady,uartReady,ioFault,control.estop,
    (unsigned long)Serial1.baudRate(),gpio_get_level(static_cast<gpio_num_t>(FPGA_RX)),
    (unsigned long)receivedM1,(unsigned long)receivedForward,(unsigned long)fpgaRx.bytes,
    (unsigned long)fpgaRx.lines,(unsigned long)fpgaRx.bad,(unsigned long)fpgaRx.timeouts);
  console.printf("FG=%lu,%lu,%lu,%lu; DIR_FORWARD=%u,%u,%u,%u; DUTY=%u%%; PULSE=500ms\n",
    (unsigned long)counts[0],(unsigned long)counts[1],(unsigned long)counts[2],(unsigned long)counts[3],
    FORWARD_HIGH[0],FORWARD_HIGH[1],FORWARD_HIGH[2],FORWARD_HIGH[3],TEST_DUTY_PERCENT);
  console.print("LAST_HEX=");
  const uint8_t start=fpgaRx.recentCount==16?fpgaRx.recentHead:0;
  for(uint8_t i=0;i<fpgaRx.recentCount;i++)console.printf("%02X ",fpgaRx.recent[(start+i)%16]);
  console.println();
  console.printf("SIDE_SWAP=%u LOGICAL_LEFT=M%u,M%u LOGICAL_RIGHT=M%u,M%u\n",
    CarConfig::SWAP_CHASSIS_SIDES,unsigned(LEFT_A+1),unsigned(LEFT_B+1),unsigned(RIGHT_A+1),unsigned(RIGHT_B+1));
  console.printf("CAL_VERSION=%s DISTANCE_SCALE=%.3f EFFECTIVE_TRACK_MM=%.2f VERIFIED=0\n",FieldCalibration::VERSION,FieldCalibration::DISTANCE_SCALE,TRACK_EFFECTIVE_MM);
  console.printf("RUNTIME reset=%lu loopMaxGapMs=%lu consoleDropped=%lu AP=%u HTTP=%u IMU_crc=%lu unexpected=%lu late=%lu\n",(unsigned long)bootResetReason,(unsigned long)loopMaxGapMs,(unsigned long)console.dropped,apStarted,httpOk,(unsigned long)imu.crcErrors,(unsigned long)imu.unexpectedFrames,(unsigned long)imu.lateFrames);
  printLegacyStatus();
}
void printHelp() {
  console.println("R21 UART1 FPGA diagnostics; M1/M2 brakes locked, all motion disabled.");
  console.println("Web DRIVE: v mm/s, w deg/s; repeat within 650ms; v <=220, turn differential <=60mm/s");
  console.println("STOP / ESTOP / CLEAR / STATUS / HELP");
  console.println("Web MOVE/TURN/ARC/GOTO/PATH/ROUTE require a stopped ZERO and matching coordinate frame.");
}

void serviceDeadline() {
  const uint8_t finished=control.activeMask;
  const bool armed=control.state==Stage1Control::Armed;
  if(control.tick(millis())) {
    stopVehicle("completed");uint32_t counts[4];snapshotFg(counts);
    console.printf("DONE mask=%u pulse=500ms duty=%u%% FG_delta=%lu,%lu,%lu,%lu; disarmed\n",
      finished,TEST_DUTY_PERCENT,(unsigned long)(counts[0]-countAtStart[0]),
      (unsigned long)(counts[1]-countAtStart[1]),(unsigned long)(counts[2]-countAtStart[2]),
      (unsigned long)(counts[3]-countAtStart[3]));
    statusPending=true;
  } else if(armed && control.state==Stage1Control::Monitor) {
    stopVehicle();console.println("ARM EXPIRED; monitor only");statusPending=true;
  }
}
bool startPulse(Stage1Control::Trigger source) {
  return false; // webpage-only firmware
  if(!hardwareReady || !uartReady || ioFault || fault!=Fault::None || mode!=Mode::Idle ||
      !control.trigger(source,millis()))return false;
  snapshotFg(countAtStart);
  const uint16_t runDuty=PWM_MAX-(PWM_MAX*TEST_DUTY_PERCENT/100);
  bool ok=true;
  for(uint8_t i=0;i<4;i++) {
    const bool selected=(control.activeMask&(1u<<i))!=0;
    ok=ledcWrite(PIN_PWM[i],selected?runDuty:PWM_MAX)&&ok;
    motor[i].dutyPercent=selected?TEST_DUTY_PERCENT:0;
  }
  if(!ok){ioFault=true;hardwareReady=false;fault=Fault::Hardware;faultSource="test-pwm-write";}
  if(ioFault){stopVehicle("test-pwm-write");control.emergencyStop();statusPending=true;return false;}
  mode=Mode::Pulse;owner=Source::FpgaTest;
  for(uint8_t i=0;i<4;i++)if(control.activeMask&(1u<<i))writeBrake(i,false);
  return true;
}
void handleFpga(const char *line) {
  if(!strcmp(line,"STOP")){stopVehicle("fpga");statusPending=true;return;}
  if(!strcmp(line,"ESTOP")){stopVehicle("fpga");control.emergencyStop();if(!ioFault){fault=Fault::EStop;faultSource="fpga";}statusPending=true;return;}
  if(!strcmp(line,"M1TEST")){++receivedM1;startPulse(Stage1Control::M1Packet);}
  else if(!strcmp(line,"FWDTEST")){++receivedForward;startPulse(Stage1Control::ForwardPacket);}
  else return;
  statusPending=true;
}
bool armTest(uint8_t mask) {
  return false; // no FPGA or USB motion authorization
  if(!hardwareReady || !uartReady || ioFault || fault!=Fault::None || control.estop ||
     mode!=Mode::Idle || navigationActive() || routeActive() || !Stage1Control::validMask(mask))return false;
  // Web reverse/turn may have left direction inputs reversed. Change them only
  // while braked and after the original reversal/FG quiet intervals.
  for(uint8_t i=0;i<4;i++)if(motor[i].directionSign!=1) {
    if(uint32_t(millis()-stoppedSinceMs)<DIRECTION_BRAKE_MS ||
       uint32_t(millis()-motor[i].lastPulseMs)<DIRECTION_QUIET_MS)return false;
  }
  stopVehicle();if(ioFault)return false;
  for(uint8_t i=0;i<4;i++)if(motor[i].directionSign!=1)writeDirection(i,1);
  fpgaRx.clearLine();
  for(unsigned i=0;i<512 && Serial1.available();i++)Serial1.read();
  if(Serial1.available())return false;
  console.printf("ARMED mask=%u: %s within 10s; one 500ms pulse\n",mask,
    mask==Stage1Control::kAll?"press FPGA K4 (FWDTEST)":mask==1?"GO or M1TEST":"USB/Web GO");
  return control.arm(mask,millis());
}
bool zeroPoseChecked() {
  if(inspection.active()||inspectionArrivalPending)return false;
  if(ImuConfig::ENABLED&&(!imu.ready(millis())||!imuQuiet()))return false;
  zeroPose();return true;
}
bool legacyMotion(const char *line) {
  char command[24]={};unsigned len=0,n=0;float args[3]={};
  while(*line && isspace(static_cast<unsigned char>(*line)))++line;
  while(*line && !isspace(static_cast<unsigned char>(*line))) {
    if(len>=sizeof(command)-1)return false;
    command[len++]=toupper(static_cast<unsigned char>(*line++));
  }
  while(*line) {
    while(*line && isspace(static_cast<unsigned char>(*line)))++line;
    if(!*line)break;
    if(n>=3)return false;
    char *end=nullptr;float value=strtof(line,&end);
    if(end==line || !isFiniteNumber(value) || (*end && !isspace(static_cast<unsigned char>(*end))))return false;
    args[n++]=value;line=end;
  }
  if(!strcmp(command,"DRIVE") && n==2)return startManual(args[0],args[1]);
  if(!strcmp(command,"MOVE") && (n==1||n==2))return moveMm(args[0],n==2?args[1]:DEFAULT_MOVE_MM_S);
  if(!strcmp(command,"TURN") && (n==1||n==2))return turnDeg(args[0],n==2?args[1]:DEFAULT_TURN_MM_S);
  if(!strcmp(command,"ARC") && (n==2||n==3))return arcMmDeg(args[0],args[1],n==3?args[2]:DEFAULT_MOVE_MM_S);
  if(!strcmp(command,"GOTO") && (n==2||n==3))return startGoto(args[0],args[1],n==3?args[2]:40);
  return false;
}
void handleUsb(const char *line) {
  requestSource=Source::Usb;
  if(!strcmp(line,"STOP")||!strcmp(line,"ESTOP")) {
    stopVehicle("usb");
    if(!strcmp(line,"ESTOP")){control.emergencyStop();if(!ioFault){fault=Fault::EStop;faultSource="usb";}}
    console.println(control.estop?"ESTOP latched; CLEAR then re-arm required":"STOPPED; disarmed");
  } else if(!strcmp(line,"CLEAR")) {
    clearAllFaults();console.println("CLEARED; monitor only. IO_FAULT requires repair/restart");
  } else if(!strcmp(line,"STATUS"))statusPending=true;
  else if(!strcmp(line,"HELP"))helpPending=true;
  else if(!strcmp(line,"ZERO")) {
    if(mode==Mode::Idle&&!navigationActive()&&!routeActive()&&!inspection.active()){console.println(zeroPoseChecked()?"OK ZERO":"ZERO rejected: keep still and wait for IMU ready");}
  } else if(!strcmp(line,"GO")) {
    if(!startPulse(Stage1Control::UsbGo) && !anyMotion())console.println("GO REJECTED: ARM 1..4; ARM ALL requires FPGA FWDTEST");
  } else if(!strcmp(line,"ARM")||!strcmp(line,"ARM 1")||!strcmp(line,"ARM 2")||
            !strcmp(line,"ARM 3")||!strcmp(line,"ARM 4")||!strcmp(line,"ARM ALL")) {
    uint8_t mask=!strcmp(line,"ARM ALL")?15:strlen(line)==3?1:uint8_t(1u<<(line[4]-'1'));
    if(!armTest(mask) && !anyMotion())console.println("ARM REJECTED: stop first; check READY/UART/FAULT/ESTOP/direction quiet");
  } else {
    bool ok=legacyMotion(line);
    if(!anyMotion())console.println(ok?"OK":"ERR UNKNOWN_OR_REJECTED");
  }
}
void pollUsb() {
  if(usbLine.length && uint32_t(millis()-usbLine.lastByteMs)>=250){usbLine.length=0;usbLine.discard=true;}
  for(unsigned budget=0;budget<32 && Serial.available();budget++) {
    serviceDeadline();int c=Serial.read();if(c<0)break;usbLine.lastByteMs=millis();
    if(c=='\r')continue;
    if(c=='\n') {
      if(!usbLine.discard && usbLine.length){usbLine.data[usbLine.length]=0;handleUsb(usbLine.data);}
      usbLine.clear();
    } else if(c<32||c>126||usbLine.length>=sizeof(usbLine.data)-1){usbLine.length=0;usbLine.discard=true;}
    else if(!usbLine.discard)usbLine.data[usbLine.length++]=char(c);
  }
}
void pollFpga() {
  fpgaRx.expire(millis());
  for(unsigned budget=0;budget<32 && Serial1.available();budget++) {
    serviceDeadline();int c=Serial1.read();if(c<0)break;
    if(fpgaRx.feed(uint8_t(c),millis()))handleFpga(fpgaRx.data);
  }
}
void publishWebSnapshot() {
  WebSnapshot next;
  next.fpga=fpgaLink.snapshot(millis());
  next.scan=scanPlan;next.inspectionArrivalHeading=inspectionArrivalHeading;
  next.inspectionNavigation=inspectionNavigation;next.inspectionArrivalPending=inspectionArrivalPending;next.consoleMode=consoleMode;
  for(uint8_t i=0;i<4;i++)next.startDelayMs[i]=motor[i].startDelayMs;
  next.m4StartAssist=motor[3].startAssistActive;
  next.headingValid=headingFeedback.valid;next.headingLimited=headingFeedback.limited;
  next.headingTarget=headingFeedback.target;next.headingActual=imu.headingDeg();
  next.headingError=headingFeedback.error;next.headingResidual=headingFeedback.residual;
  next.headingCorrections=headingFeedback.corrections;
  next.goalTracked=goalDrive.valid;next.pathRemaining=goalDrive.remaining;next.pathCross=goalDrive.cross;
  next.pathRecoveries=goalDrive.recoveries;next.pathTrims=goalDrive.trims;next.pathDistanceOnly=goalDrive.distanceOnly;
  next.feedbackMotor=navigation.feedbackMotor;next.feedbackTarget=navigation.feedbackTarget;
  next.feedbackDuty=navigation.feedbackDuty;next.feedbackSilenceMs=navigation.feedbackSilenceMs;
  next.feedbackCount=navigation.feedbackCount;
  snprintf(next.headingPhase,sizeof(next.headingPhase),"%s",headingFeedback.phase);
  snprintf(next.headingNote,sizeof(next.headingNote),"%s",headingFeedback.note);
  snprintf(next.mode,sizeof(next.mode),"%s",modeName());
  snprintf(next.fault,sizeof(next.fault),"%s",faultName());
  snprintf(next.stopSource,sizeof(next.stopSource),"%s",stopSource);
  snprintf(next.faultSource,sizeof(next.faultSource),"%s",faultSource);
  next.loopMaxGapMs=loopMaxGapMs;next.bootResetReason=bootResetReason;next.consoleDropped=console.dropped;next.apStarted=apStarted;
  next.imuCrc=imu.crcErrors;next.imuUnexpected=imu.unexpectedFrames;next.imuLate=imu.lateFrames;
  next.responseTravelL=imuFault.travelL;next.responseTravelR=imuFault.travelR;next.responseCommand=imuFault.command;next.responseDuty=imuFault.duty;
  next.imuUsable=ImuConfig::ENABLED&&imu.usable(millis());
  next.imuRx=imu.rxBytes;next.imuRequests=imu.requests;next.imuRate=imu.rateDegS;
  next.imuLinkRestarts=imuLink.restarts;next.imuAutoRestarts=imuLink.autoRestarts;
  next.imuCanReconnect=ImuConfig::ENABLED&&!imu.ready(millis())&&imuQuiet()&&uint32_t(millis()-imuLink.lastRestartMs)>=2000;
  next.imuFaultValid=imuFault.valid;next.imuFaultAge=imuFault.age;next.imuFaultRoll=imuFault.roll;next.imuFaultPitch=imuFault.pitch;
  next.imuReady=ImuConfig::ENABLED&&imu.ready(millis());next.imuAvailable=ImuConfig::ENABLED&&imu.available(millis());
  next.imuVersion=imu.version;next.imuAge=imu.frames?uint32_t(millis()-imu.lastSampleMs):0xffffffffu;
  next.imuYaw=imu.yaw;next.imuRoll=imu.roll;next.imuPitch=imu.pitch;
  next.imuFrames=imu.frames;next.imuBad=imu.badFrames;next.imuTimeouts=imu.timeouts;
  snprintf(next.imuReason,sizeof(next.imuReason),"%s",imu.reason(millis()));
  next.x=xMm;next.y=yMm;next.yaw=thetaRad*RAD2DEG;
  next.left=actualLeftMmS;next.right=actualRightMmS;
  snapshotFg(next.count);
  for(uint8_t i=0;i<4;i++){next.speed[i]=motor[i].measuredMmS;next.duty[i]=motor[i].dutyPercent;}
  next.epoch=webEpoch;next.stage=uint8_t(control.state);next.armed=control.armedMask;next.active=control.activeMask;
  next.ready=hardwareReady;next.uart=uartReady;next.ioFault=ioFault;next.estop=control.estop;
  next.rxForward=receivedForward;next.rxM1=receivedM1;next.bytes=fpgaRx.bytes;next.bad=fpgaRx.bad;next.ageMs=millis();
  snprintf(next.navStage,sizeof(next.navStage),"%s",navigationStageName());
  snprintf(next.navReason,sizeof(next.navReason),"%s",navigation.reason);
  snprintf(next.routeStage,sizeof(next.routeStage),"%s",routeStageName());
  snprintf(next.routeReason,sizeof(next.routeReason),"%s",route.reason);
  next.routeActive=routeActive();next.routeCount=route.plan.count;
  next.routeStep=route.plan.count?uint8_t(route.index<route.plan.count?route.index+1:route.plan.count):0;
  next.routeKind=route.index<route.plan.count?route.plan.steps[route.index].kind:0;
  next.routeRemaining=routeRemaining();
  next.poseFrame=poseFrame;next.poseZeroed=poseZeroed;next.navGuarded=navigation.plan.guarded;
  next.obstacleMap=navigation.plan.obstacles;
  for(uint8_t i=0;i<PathLimits::MAX_POINTS;i++)next.navPoints[i]=navigation.plan.points[i];
  next.navActive=navigationActive();next.goalX=navigation.goalX;next.goalY=navigation.goalY;next.goalError=navigationDistance();
  next.navCount=navigation.plan.count;next.navPoint=navigation.plan.count?navigation.index+1:0;
  if(navigation.plan.count){next.finalX=navigation.plan.points[navigation.plan.count-1].x;next.finalY=navigation.plan.points[navigation.plan.count-1].y;}
  portENTER_CRITICAL(&webMux);webSnapshot=next;portEXIT_CRITICAL(&webMux);
}
void serviceWebStop() {
  portENTER_CRITICAL(&webMux);uint8_t request=webStopRequest;webStopRequest=0;portEXIT_CRITICAL(&webMux);
  if(request){stopVehicle("web");if(request&2){control.emergencyStop();if(!ioFault){fault=Fault::EStop;faultSource="web";}}statusPending=true;}
}
void processWebCommands() {
  if(!webCommands || !webResults)return;
  WebCommand cmd;
  if(xQueueReceive(webCommands,&cmd,0)!=pdTRUE)return;
  bool ok=false;
  const bool fresh=uint32_t(millis()-cmd.receivedMs)<=WEB_COMMAND_MAX_AGE_MS;
  requestSource=Source::Web;
  const bool motionCommand=cmd.operation==WebOp::Drive||cmd.operation==WebOp::Move||cmd.operation==WebOp::Turn||cmd.operation==WebOp::Arc||cmd.operation==WebOp::Goto||cmd.operation==WebOp::Route||cmd.operation==WebOp::Path||cmd.operation==WebOp::AvoidPath;
  const bool automaticCommand=motionCommand&&cmd.operation!=WebOp::Drive;
  const bool linkCommand=cmd.operation==WebOp::FpgaStart||cmd.operation==WebOp::FpgaCancel;
  const bool coordinateMatches=(!automaticCommand||(poseZeroed&&cmd.coordinateFrame==poseFrame))&&(!linkCommand||cmd.coordinateFrame==poseFrame);
  // A second page must STOP before taking over; it cannot acquire the first
  // page's private lease simply by submitting another DRIVE request.
  const bool ownsLease=!motionCommand||owner!=Source::Web||!strcmp(cmd.leaseToken,webLeaseToken);
  if(fresh && cmd.epoch==webEpoch && ownsLease && coordinateMatches && (!motionCommand||consoleMode||cmd.operation==WebOp::Goto)) {
    switch(cmd.operation) {
      case WebOp::Drive:ok=startManual(cmd.a,cmd.b);break;
      case WebOp::Move:ok=moveMm(cmd.a,cmd.b);break;
      case WebOp::Turn:ok=turnDeg(cmd.a,cmd.b);break;
      case WebOp::Arc:ok=arcMmDeg(cmd.a,cmd.b,cmd.c);break;
      case WebOp::Clear:clearAllFaults();ok=!ioFault&&fault==Fault::None;break;
      case WebOp::Zero:if(mode==Mode::Idle&&!navigationActive()&&!routeActive()&&!inspection.active()){ok=zeroPoseChecked();}break;
      case WebOp::Goto:ok=consoleMode?startGoto(cmd.a,cmd.b,cmd.c):startInspectionGoto(cmd.a,cmd.b,cmd.c);break;
      case WebOp::Path:case WebOp::AvoidPath:ok=startNavigationPath(cmd.pathPlan);break;
      case WebOp::Route:ok=startRoute(cmd.routePlan);break;
      case WebOp::Arm:ok=armTest(uint8_t(cmd.a));break;
      case WebOp::Go:ok=startPulse(Stage1Control::UsbGo);break;
      case WebOp::ImuReconnect:ok=restartImuLink();break;
      case WebOp::FpgaStart:ok=startFpgaTask(cmd.linkTask,cmd.linkPoint,cmd.linkConfig,cmd.a==1?gb4::TaskMode::DIAGNOSTIC_CONTINUOUS:gb4::TaskMode::FORMAL_REVIEW);break;
      case WebOp::FpgaCancel:ok=cancelFpgaTask(cmd.linkTask,cmd.linkPoint,cmd.linkConfig,cmd.linkEpoch);break;
      case WebOp::InspectionArm:ok=cmd.coordinateFrame==poseFrame&&localInspectionArm(cmd.a!=0,cmd.b==1);break;
      case WebOp::InspectionCalibration:ok=cmd.coordinateFrame==poseFrame&&localInspectionCalibration(cmd.a!=0);break;
      case WebOp::ScanConfigure:ok=cmd.coordinateFrame==poseFrame&&!anyMotion()&&!inspection.active()&&scanPlan.parse(cmd.scanText);break;
      case WebOp::ScanStart:ok=cmd.coordinateFrame==poseFrame&&startScanQueue(cmd.a==1?ScanPlan::DiagnosticCandidates:ScanPlan::Formal,cmd.b==1);break;
      case WebOp::ScanContinue:ok=cmd.coordinateFrame==poseFrame&&continueScanQueue();break;
    }
  }
  WebResult result;result.id=cmd.id;result.ok=ok;result.epoch=webEpoch;
  if(ok && owner==Source::Web) {
    portENTER_CRITICAL(&webMux);
    if(!webLeaseToken[0])snprintf(webLeaseToken,sizeof(webLeaseToken),"%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());
    webLastTouchMs=millis();
    snprintf(result.leaseToken,sizeof(result.leaseToken),"%s",webLeaseToken);
    portEXIT_CRITICAL(&webMux);
  }
  xQueueSend(webResults,&result,0);
  requestSource=Source::Usb;
}
void serviceWebLease() {
  uint32_t touched;
  portENTER_CRITICAL(&webMux);touched=webLastTouchMs;portEXIT_CRITICAL(&webMux);
  if(owner==Source::Web && uint32_t(millis()-touched)>WEB_PAGE_LEASE_MS) {
    if(navigationActive())navigation.reason="PAGE_LOST";
    if(routeActive())route.reason="PAGE_LOST";
    stopVehicle("page-lost");
  }
}
void robotSetup() {
  for(uint8_t i=0;i<2;i++){digitalWrite(PIN_BRK[i],LOW);pinMode(PIN_BRK[i],OUTPUT);}
  hardwareReady=true;
  for(uint8_t i=0;i<2;i++) {
    digitalWrite(PIN_PWM[i],HIGH);pinMode(PIN_PWM[i],OUTPUT);
    pinMode(PIN_DIR[i],OUTPUT);writeDirection(i,1);
    attached[i]=ledcAttach(PIN_PWM[i],PWM_FREQ_HZ,PWM_BITS);
    hardwareReady=attached[i] && hardwareReady;pinMode(PIN_FG[i],INPUT_PULLUP);
  }
  if(!hardwareReady){ioFault=true;fault=Fault::Hardware;faultSource="boot";}
  stopVehicle("boot");
  // Assert every brake/PWM output before accessing persistent storage.
  // Read only; absent/invalid data uses R12's original .12/.25/0 defaults.
  wheelPi=WheelPiProfile{};wheelPi.saved=WheelPiStorage::read(wheelPi.gains);
  if(!installFgInterrupts()) {
    hardwareReady=false;ioFault=true;fault=Fault::Hardware;faultSource="fg-isr-init";
    brakeAllImmediately();
  }
  lastControlMs=millis();for(uint8_t i=0;i<4;i++)motor[i].lastPulseMs=millis();
  Serial.begin(115200);
#ifdef ARDUINO
  bootResetReason=uint32_t(esp_reset_reason());
#endif
  console.printf("FG_ISR direct=%s core=%u; WiFi setup next\n",fgInterruptReady?"OK":"FAILED",unsigned(fgInterruptCore));
  // Real sensor on UART2; UART1/FPGA remains disabled.
  openImuPort(millis());
  openFpgaPort(millis());
  webCommands=xQueueCreate(1,sizeof(WebCommand));webResults=xQueueCreate(1,sizeof(WebResult));
  setupWifi();
  // A new boot may reuse an epoch. Bind browser commands to this boot as well.
  snprintf(bootSession,sizeof(bootSession),"%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());
  publishWebSnapshot();
  if(webCommands && webResults)
    webTaskReady=xTaskCreatePinnedToCore(webTask,"robot-web",16384,nullptr,1,nullptr,0)==pdPASS;
  console.printf("%s; calibration=%s; sideSwap=1; scale=0.70; physical retest pending\n",FIRMWARE_VERSION,FieldCalibration::VERSION);
  if(!webTaskReady)console.println("WEB TASK NOT STARTED; motors remain stopped; USB diagnostic output only");
  console.println("R24 V4: local arm/calibration default false; ESP owns bounded point ledger and true parked6s; FPGA requests finite10deg.");
}
void robotLoop() {
  const uint32_t loopNow=millis();
  if(loopLastMs)loopMaxGapMs=uint32_t(loopNow-loopLastMs)>loopMaxGapMs?uint32_t(loopNow-loopLastMs):loopMaxGapMs;
  loopLastMs=loopNow;
  serviceWebStop();serviceDeadline();serviceImu();serviceFpgaLink();serviceDeadline();
  processWebCommands();serviceWebStop();serviceWebLease();controlStep();serviceNavigation();serviceRoute();serviceDeadline();
  publishWebSnapshot();
  if(!anyMotion() && fpgaRx.bytes!=lastReportedBytes && uint32_t(millis()-lastRxReportMs)>=500) {
    lastReportedBytes=fpgaRx.bytes;lastRxReportMs=millis();statusPending=true;
  }
  if(!anyMotion()) {
    if(statusPending){statusPending=false;printStatus();}
    if(helpPending){helpPending=false;printHelp();}
    console.flush();
  }
  delay(1);
}
