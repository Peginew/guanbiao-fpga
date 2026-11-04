WebSnapshot takeWebSnapshot() {
  portENTER_CRITICAL(&webMux);WebSnapshot s=webSnapshot;portEXIT_CRITICAL(&webMux);return s;
}
// WebServer String preserves decoded %00. Reject embedded NUL before any
// C-string comparison/parser, so the complete HTTP value is always checked.
bool plainWebText(const String &s) { return strlen(s.c_str())==s.length(); }
bool allowWebRequest() {
  // The AP password is the access boundary. Do not allow an unrelated website
  // or a rebound hostname to issue anonymous vehicle requests from the phone.
  const String ap=WiFi.softAPIP().toString();
  String apPort=ap;apPort+=":80";
  const String host=server.hostHeader();
  String origin="http://";origin+=ap;
  String originPort=origin;originPort+=":80";
  const String supplied=server.header("Origin");
  if(!plainWebText(host)||!plainWebText(supplied)||
     (strcmp(host.c_str(),ap.c_str())&&strcmp(host.c_str(),apPort.c_str())) ||
     (server.hasHeader("Origin")&&strcmp(supplied.c_str(),origin.c_str())&&strcmp(supplied.c_str(),originPort.c_str()))) {
    server.send(403,"application/json","{\"ok\":false,\"error\":\"Open the car AP address directly\"}");return false;
  }
  return true;
}
void respondJson(bool ok,const char *error="",int status=400,uint32_t epoch=0,const char *lease="") {
  String payload="{\"ok\":";payload+=ok?"true":"false";
  payload+=",\"error\":\"";payload+=error;payload+="\",\"epoch\":";
  payload+=String((unsigned long)epoch);
  payload+=",\"bootSession\":\"";payload+=bootSession;
  payload+="\",\"leaseToken\":\"";payload+=lease;payload+="\"}";
  server.sendHeader("Cache-Control","no-store");server.send(ok?200:status,"application/json",payload);
}
bool getFloatArg(const char *name,float &out) {
  if(!server.hasArg(name))return false;
  const String s=server.arg(name);
  if(!s.length()||s.length()>25||!plainWebText(s))return false;
  char *end=nullptr;const float v=strtof(s.c_str(),&end);
  if(end==s.c_str()||*end!='\0'||!isFiniteNumber(v))return false;
  out=v;return true;
}
bool getUintArg(const char *name,uint32_t &out) {
  if(!server.hasArg(name))return false;
  const String s=server.arg(name);
  if(!s.length()||s.length()>10||!plainWebText(s))return false;
  uint64_t value=0;
  for(unsigned i=0;i<s.length();i++) {
    char c=s.c_str()[i];if(c<'0'||c>'9')return false;
    value=value*10+uint8_t(c-'0');if(value>0xffffffffULL)return false;
  }
  out=uint32_t(value);return true;
}
bool renewStatusLease(const WebSnapshot &s) {
  uint32_t epoch=0;const String session=server.arg("bootSession"),token=server.arg("leaseToken");
  if(!getUintArg("epoch",epoch)||epoch!=s.epoch||uint32_t(millis()-s.ageMs)>250||
    !plainWebText(session)||session.length()!=16||strcmp(session.c_str(),bootSession)||
    !plainWebText(token)||token.length()!=16)return false;
  portENTER_CRITICAL(&webMux);
  const bool ok=webLeaseToken[0]&&!strcmp(token.c_str(),webLeaseToken);
  if(ok)webLastTouchMs=millis();
  portEXIT_CRITICAL(&webMux);return ok;
}
void appendFpgaStatus(String &p,const FpgaLinkSnapshot &f){
  p+=",\"fpga\":{\"online\":";p+=f.online?"true":"false";
  p+=",\"negotiated\":";p+=f.negotiated?"true":"false";
  p+=",\"visionFresh\":";p+=f.visionFresh?"true":"false";
  p+=",\"located\":";p+=f.located?"true":"false";
  p+=",\"locked\":";p+=f.locked?"true":"false";
  p+=",\"readable\":";p+=f.readable?"true":"false";
  p+=",\"healthy\":";p+=f.healthy?"true":"false";
  p+=",\"candidateRead\":";p+=f.candidateRead?"true":"false";
  p+=",\"formalReadingValid\":false,\"benchOnly\":";p+=f.benchOnly?"true":"false";
  p+=",\"refValid\":";p+=f.refValid?"true":"false";
  p+=",\"canStart\":";p+=f.canStart?"true":"false";
  p+=",\"stationaryReport\":";p+=f.stationaryReport?"true":"false";
  p+=",\"motionLocked\":";p+=f.motionLocked?"true":"false";
  p+=",\"localArmed\":";p+=f.localArmed?"true":"false";
  p+=",\"calibrationConfirmed\":";p+=f.calibrationConfirmed?"true":"false";
  char signature[9];snprintf(signature,sizeof(signature),"%08lX",(unsigned long)gb4::kConfigSignature);
  p+=",\"protocolVersion\":4,\"frameBytes\":32,\"configSignature\":\"";p+=signature;p+='"';
  p+=",\"workflowStage\":";p+=String(unsigned(f.workflowStage));
  p+=",\"cameraSource\":";p+=String((unsigned long)f.cameraSource);
  p+=",\"observationSource\":";p+=String((unsigned long)f.observationSource);
  p+=",\"boxLeft\":";p+=String(float(f.boxLeft),0);p+=",\"boxTop\":";p+=String(float(f.boxTop),0);
  p+=",\"boxRight\":";p+=String(float(f.boxRight),0);p+=",\"boxBottom\":";p+=String(float(f.boxBottom),0);
  p+=",\"boxHeight\":";p+=String(unsigned(f.boxHeight));p+=",\"observationFlags\":";p+=String(unsigned(f.observationFlags));
  p+=",\"actionId\":";p+=String((unsigned long)f.actionId);p+=",\"windowId\":";p+=String((unsigned long)f.windowId);
  p+=",\"actionStatus\":";p+=String(unsigned(f.actionStatus));p+=",\"actionPhase\":";p+=String(unsigned(f.actionPhase));
  p+=",\"reason\":";p+=String(unsigned(f.reason));p+=",\"yawRelMdeg\":";p+=String(float(f.yawRelMdeg),0);
  p+=",\"deltaYawMdeg\":";p+=String(float(f.deltaYawMdeg),0);p+=",\"deltaTranslationMm\":";p+=String(float(f.deltaTranslationMm),0);
  p+=",\"cumAngleCdeg\":";p+=String(unsigned(f.cumAngleCdeg));p+=",\"cumTranslationMm\":";p+=String(unsigned(f.cumTranslationMm));
  p+=",\"stationaryMs\":";p+=String(unsigned(f.stationaryMs));p+=",\"imuAgeMs\":";p+=String(unsigned(f.imuAgeMs));
  p+=",\"actions\":";p+=String((unsigned long)f.actions);p+=",\"taskElapsedMs\":";p+=String((unsigned long)f.taskElapsedMs);
  p+=",\"localSession\":";p+=String((unsigned long)f.localSession);
  p+=",\"bindingToken\":";p+=String((unsigned long)f.bindingToken);
  p+=",\"taskKey\":";p+=String((unsigned long)f.taskKey);
  p+=",\"readyStep\":";p+=f.readyStep?"true":"false";
  p+=",\"readyRead\":";p+=f.readyRead?"true":"false";
  p+=",\"bboxAvailable\":false";
  p+=",\"peerSession\":";p+=String((unsigned long)f.peerSession);
  p+=",\"ageMs\":";p+=f.ageMs==0xffffffffu?String("-1"):String((unsigned long)f.ageMs);
  p+=",\"visionAgeMs\":";p+=f.visionAgeMs==0xffffffffu?String("-1"):String((unsigned long)f.visionAgeMs);
  p+=",\"txFrames\":";p+=String((unsigned long)f.txFrames);p+=",\"rxFrames\":";p+=String((unsigned long)f.rxFrames);
  p+=",\"rxBytes\":";p+=String((unsigned long)f.rxBytes);p+=",\"crcErrors\":";p+=String((unsigned long)f.crcErrors);
  p+=",\"formatErrors\":";p+=String((unsigned long)f.formatErrors);p+=",\"staleFrames\":";p+=String((unsigned long)f.staleFrames);
  p+=",\"disconnects\":";p+=String((unsigned long)f.disconnects);p+=",\"motionRejected\":";p+=String((unsigned long)f.motionRejected);
  p+=",\"partialTimeouts\":";p+=String((unsigned long)f.partialTimeouts);
  p+=",\"taskId\":";p+=String(unsigned(f.taskId));p+=",\"pointId\":";p+=String(unsigned(f.pointId));
  p+=",\"configId\":";p+=String(unsigned(f.configId));p+=",\"observationEpoch\":";p+=String(unsigned(f.observationEpoch));
  p+=",\"taskState\":";p+=String(unsigned(f.taskState));p+=",\"ackCode\":";p+=String(unsigned(f.ackCode));
  p+=",\"pipelineState\":";p+=String(unsigned(f.pipelineState));p+=",\"quality\":";p+=String(unsigned(f.quality));
  p+=",\"refMode\":";p+=String(unsigned(f.refMode));p+=",\"sourceFrame\":";p+=String((unsigned long)f.sourceFrame);
  p+=",\"readSourceFrame\":";p+=String((unsigned long)f.readSourceFrame);p+=",\"sourceFloor\":";p+=String((unsigned long)f.sourceFloor);
  p+=",\"centerX\":";p+=String(unsigned(f.centerX));p+=",\"centerY\":";p+=String(unsigned(f.centerY));p+=",\"diameter\":";p+=String(unsigned(f.diameter));
  p+=",\"rawBarQ16\":";p+=String(unsigned(f.rawBarQ16));p+=",\"candidatePsi\":";p+=String(float(f.rawBarQ16)/65536.f*14.5037738f,4);
  p+=",\"refHundredths\":";p+=String(unsigned(f.refHundredths));p+=",\"readAgeMs\":";p+=String(unsigned(f.readAgeMs));p+='}';
}
void handleStatus(bool renew=false) {
  if(!allowWebRequest())return;
  const WebSnapshot s=takeWebSnapshot();
  // GET stays read-only. Only POST with this task's private token may renew.
  const bool leaseRenewed=renew&&renewStatusLease(s);
  String p;p.reserve(8192);
  p="{\"leaseRenewed\":";p+=leaseRenewed?"true":"false";p+=",\"mode\":\"";p+=s.mode;p+="\",\"fault\":\"";p+=s.fault;
  p+="\",\"stopSource\":\"";p+=s.stopSource;p+="\",\"faultSource\":\"";p+=s.faultSource;
  p+="\",\"x\":";p+=String(s.x,2);p+=",\"y\":";p+=String(s.y,2);
  p+=",\"yaw\":";p+=String(s.yaw,2);p+=",\"left\":";p+=String(s.left,2);
  p+=",\"right\":";p+=String(s.right,2);
  p+=",\"maxLinear\":";p+=String(WEB_MAX_LINEAR_MM_S,1);
  p+=",\"startDelayMs\":[";
  for(uint8_t i=0;i<2;i++){if(i)p+=',';if(s.startDelayMs[i]==0xffffffffu)p+="-1";else p+=String((unsigned long)s.startDelayMs[i]);}p+=']';
  p+=",\"m4StartAssist\":";p+=s.m4StartAssist?"true":"false";
  p+=",\"wheelPidLoaded\":";p+=wheelPi.saved?"true":"false";
  p+=",\"driveFeedforwardScale\":1.0,\"wheelPid\":[";
  for(uint8_t i=0;i<2;i++){if(i)p+=',';p+='[';p+=String(wheelPi.gains[i].kp,4);p+=',';p+=String(wheelPi.gains[i].ki,4);p+=',';p+=String(wheelPi.gains[i].kd,4);p+=']';}p+=']';
  p+=",\"maxAngular\":";p+=String(WEB_MAX_ANGULAR_DEG_S,1);
  p+=",\"minArcRadius\":";p+=String(TRACK_EFFECTIVE_MM*0.5f,1);
  p+=",\"count\":[";
  for(uint8_t i=0;i<2;i++){if(i)p+=',';p+=String((unsigned long)s.count[i]);}
  p+="],\"wheelSpeed\":[";
  for(uint8_t i=0;i<2;i++){if(i)p+=',';p+=String(s.speed[i],2);}
  p+="],\"duty\":[";
  for(uint8_t i=0;i<2;i++){if(i)p+=',';p+=String(s.duty[i],1);}
  p+="],\"stage\":\"";
  p+=s.stage==Stage1Control::Running?"RUNNING":s.stage==Stage1Control::Armed?"ARMED":"MONITOR";
  p+="\",\"armed\":";p+=String(unsigned(s.armed));
  p+=",\"active\":";p+=String(unsigned(s.active));
  p+=",\"ready\":";p+=s.ready?"true":"false";
  p+=",\"uart\":";p+=s.uart?"true":"false";
  p+=",\"ioFault\":";p+=s.ioFault?"true":"false";
  p+=",\"estop\":";p+=s.estop?"true":"false";
  p+=",\"rxForward\":";p+=String((unsigned long)s.rxForward);
  p+=",\"rxM1\":";p+=String((unsigned long)s.rxM1);
  p+=",\"rxBytes\":";p+=String((unsigned long)s.bytes);
  p+=",\"rxBad\":";p+=String((unsigned long)s.bad);
  p+=",\"webEpoch\":";p+=String((unsigned long)s.epoch);
  p+=",\"epoch\":";p+=String((unsigned long)s.epoch); // R23 monitor alias; retain original webEpoch.
  p+=",\"bootSession\":\"";p+=bootSession;p+='"';
  p+=",\"snapshotAgeMs\":";p+=String((unsigned long)(millis()-s.ageMs));
  p+=",\"firmware\":\"";p+=FIRMWARE_VERSION;
  p+="\",\"calibrationProfile\":\"";p+=FieldCalibration::VERSION;
  p+="\",\"calibrationApplied\":true,\"distanceScale\":";p+=String(FieldCalibration::DISTANCE_SCALE,3);
  p+=",\"effectiveTrackMm\":";p+=String(TRACK_EFFECTIVE_MM,2);
  p+=",\"sideSwap\":true,\"calibrated\":false,\"nav\":\"";p+=s.navStage;p+="\",\"navReason\":\"";p+=s.navReason;
  p+="\",\"navActive\":";p+=s.navActive?"true":"false";
  p+=",\"goalX\":";p+=String(s.goalX,2);p+=",\"goalY\":";p+=String(s.goalY,2);
  p+=",\"goalError\":";p+=String(s.goalError,2);
  p+=",\"poseFrame\":";p+=String((unsigned long)s.poseFrame);
  p+=",\"navGuarded\":";p+=s.navGuarded?"true":"false";
  p+=",\"obstacleRadius\":";p+=String(s.obstacleMap.radius,3);
  p+=",\"obstacleMargin\":";p+=String(s.obstacleMap.margin,3);
  p+=",\"obstacles\":[";
  if(s.navGuarded)for(uint8_t i=0;i<s.obstacleMap.count;i++){
    if(i)p+=',';const auto &o=s.obstacleMap.items[i];p+="[\"";p+=o.kind;p+="\",";
    p+=String(o.x1,3);p+=',';p+=String(o.y1,3);p+=',';p+=String(o.x2,3);p+=',';p+=String(o.y2,3);p+=',';p+=String(o.width,3);p+=']';
  }
  p+="],\"navPoints\":[";
  for(uint8_t i=0;i<s.navCount;i++){if(i)p+=',';p+='[';p+=String(s.navPoints[i].x,3);p+=',';p+=String(s.navPoints[i].y,3);p+=']';}
  p+=']';
  p+=",\"navPoint\":";p+=String(unsigned(s.navPoint));p+=",\"navCount\":";p+=String(unsigned(s.navCount));
  p+=",\"finalX\":";p+=String(s.finalX,2);p+=",\"finalY\":";p+=String(s.finalY,2);
  p+=",\"routeMaxSpeed\":";p+=String(WEB_MAX_LINEAR_MM_S,1);p+=",\"routeTurnMaxSpeed\":60";
  p+=",\"route\":\"";p+=s.routeStage;p+="\",\"routeReason\":\"";p+=s.routeReason;
  p+="\",\"routeActive\":";p+=s.routeActive?"true":"false";
  p+=",\"routeStep\":";p+=String(unsigned(s.routeStep));
  p+=",\"routeCount\":";p+=String(unsigned(s.routeCount));
  p+=",\"routeKind\":\"";if(s.routeKind)p+=s.routeKind;p+='"';
  p+=",\"routeRemaining\":";p+=String(s.routeRemaining,2);
  p+=",\"imuAvailable\":";p+=s.imuAvailable?"true":"false";
  p+=",\"imuUsable\":";p+=s.imuUsable?"true":"false";
  p+=",\"imuRx\":";p+=String((unsigned long)s.imuRx);p+=",\"imuRequests\":";p+=String((unsigned long)s.imuRequests);
  p+=",\"imuRate\":";p+=String(s.imuRate,2);
  p+=",\"headingValid\":";p+=s.headingValid?"true":"false";
  p+=",\"headingLimited\":";p+=s.headingLimited?"true":"false";
  p+=",\"headingTarget\":";p+=String(s.headingTarget,2);
  p+=",\"goalTracked\":";p+=s.goalTracked?"true":"false";
  p+=",\"pathRemaining\":";p+=String(s.pathRemaining,2);
  p+=",\"pathCross\":";p+=String(s.pathCross,2);
  p+=",\"pathRecoveries\":";p+=String(unsigned(s.pathRecoveries));
  p+=",\"pathTrims\":";p+=String(unsigned(s.pathTrims));
  p+=",\"pathDistanceOnly\":";p+=s.pathDistanceOnly?"true":"false";
  p+=",\"feedbackMotor\":";p+=String(unsigned(s.feedbackMotor));
  p+=",\"feedbackTarget\":";p+=String(s.feedbackTarget,1);
  p+=",\"feedbackDuty\":";p+=String(s.feedbackDuty,1);
  p+=",\"feedbackSilenceMs\":";p+=String((unsigned long)s.feedbackSilenceMs);
  p+=",\"feedbackCount\":";p+=String((unsigned long)s.feedbackCount);
  p+=",\"headingActual\":";p+=String(s.headingActual,2);
  p+=",\"headingError\":";p+=String(s.headingError,2);
  p+=",\"headingResidual\":";p+=String(s.headingResidual,2);
  p+=",\"headingCorrections\":";p+=String(unsigned(s.headingCorrections));
  p+=",\"headingPhase\":\"";p+=s.headingPhase;p+='"';
  p+=",\"headingNote\":\"";p+=s.headingNote;p+='"';
  p+=",\"headingTolerance\":";p+=String(ImuMotion::TURN_TOL_DEG,1);
  p+=",\"alignTriggerDeg\":";p+=String(GoalControl::ALIGN_TRIGGER_DEG,1);
  p+=",\"alignReleaseDeg\":";p+=String(GoalControl::ALIGN_RELEASE_DEG,1);
  p+=",\"alignConfirmMs\":";p+=String((unsigned long)GoalControl::ALIGN_CONFIRM_MS);
  p+=",\"maxPathRecoveries\":";p+=String(unsigned(GoalControl::MAX_RECOVERIES));
  p+=",\"maxTurnTrims\":";p+=String(unsigned(ImuMotion::MAX_CORRECTIONS));
  p+=",\"imuFaultValid\":";p+=s.imuFaultValid?"true":"false";
  p+=",\"imuFaultAge\":";p+=String((unsigned long)s.imuFaultAge);
  p+=",\"imuFaultRoll\":";p+=String(s.imuFaultRoll,2);p+=",\"imuFaultPitch\":";p+=String(s.imuFaultPitch,2);
  p+=",\"imuReady\":";p+=s.imuReady?"true":"false";
  p+=",\"imuReason\":\"";p+=s.imuReason;p+='"';
  p+=",\"imuVersion\":";p+=String(unsigned(s.imuVersion));
  p+=",\"imuAgeMs\":";p+=String((unsigned long)s.imuAge);
  p+=",\"imuYaw\":";p+=String(s.imuYaw,2);
  p+=",\"imuRoll\":";p+=String(s.imuRoll,2);p+=",\"imuPitch\":";p+=String(s.imuPitch,2);
  p+=",\"imuFrames\":";p+=String((unsigned long)s.imuFrames);
  p+=",\"imuBad\":";p+=String((unsigned long)s.imuBad);
  p+=",\"imuTimeouts\":";p+=String((unsigned long)s.imuTimeouts);
  p+=",\"imuLinkRestarts\":";p+=String((unsigned long)s.imuLinkRestarts);
  p+=",\"imuAutoRestarts\":";p+=String(unsigned(s.imuAutoRestarts));
  p+=",\"loopMaxGapMs\":";p+=String((unsigned long)s.loopMaxGapMs);
  p+=",\"resetReason\":";p+=String((unsigned long)s.bootResetReason);
  p+=",\"consoleDropped\":";p+=String((unsigned long)s.consoleDropped);
  p+=",\"apStarted\":";p+=s.apStarted?"true":"false";
  p+=",\"imuCrc\":";p+=String((unsigned long)s.imuCrc);
  p+=",\"imuUnexpected\":";p+=String((unsigned long)s.imuUnexpected);
  p+=",\"imuLate\":";p+=String((unsigned long)s.imuLate);
  p+=",\"responseTravelL\":";p+=String(s.responseTravelL,1);
  p+=",\"responseTravelR\":";p+=String(s.responseTravelR,1);
  p+=",\"responseCommand\":";p+=String(s.responseCommand,1);
  p+=",\"responseDuty\":";p+=String(s.responseDuty,1);
  p+=",\"imuCanReconnect\":";p+=s.imuCanReconnect?"true":"false";
  p+=",\"headingSource\":\"";p+=s.imuReady?"uart2-imu":"unavailable-for-motion";p+='"';
  p+=",\"positionSource\":\"fg-distance+imu-heading\",\"controlMode\":\"three-wheel-scan-lite-v4\",\"driveTurnUnits\":\"deg/s\"";
  p+=",\"activeMotors\":[1,2],\"angleCorrection\":true,\"coordinateNavigation\":true,\"motionEnabled\":";p+=s.fpga.localArmed&&s.fpga.calibrationConfirmed?"true":"false";
  p+=",\"inspectionNavigation\":";p+=s.inspectionNavigation?"true":"false";p+=",\"inspectionArrivalPending\":";p+=s.inspectionArrivalPending?"true":"false";
  p+=",\"consoleMode\":";p+=s.consoleMode?"true":"false";
  p+=",\"maxTurnWheelSpeed\":";p+=String(MAX_TURN_WHEEL_MM_S,1);
  p+=",\"leftMotor\":";p+=String(unsigned(CarConfig::LEFT_MOTOR+1));p+=",\"rightMotor\":";p+=String(unsigned(CarConfig::RIGHT_MOTOR+1));
  p+=",\"poseZeroed\":";p+=s.poseZeroed?"true":"false";p+=",\"fieldCalibratedForR20\":false";
  appendFpgaStatus(p,s.fpga);
  p+=",\"scan\":{\"stage\":";p+=String(unsigned(s.scan.stage()));p+=",\"mode\":";p+=String(unsigned(s.scan.mode()));p+=",\"continuous\":";p+=s.scan.continuous()?"true":"false";
  p+=",\"planId\":";p+=String((unsigned long)s.scan.id());p+=",\"index\":";p+=String(unsigned(s.scan.index()));p+=",\"count\":";p+=String(unsigned(s.scan.count()));p+=",\"arrivalHeading\":";p+=String(s.inspectionArrivalHeading,3);p+=",\"formalReadingValid\":false,\"points\":[";
  for(unsigned i=0;i<s.scan.count();i++){if(i)p+=',';const auto&a=s.scan.point(i);const auto&r=s.scan.reading(i);p+="{\"id\":";p+=String(unsigned(a.id));p+=",\"x\":";p+=String(a.x,1);p+=",\"y\":";p+=String(a.y,1);p+=",\"bearing\":";p+=String(a.bearing,2);p+=",\"halfAngle\":";p+=String(a.halfAngle,1);p+=",\"candidate\":";p+=r.candidate?"true":"false";p+=",\"formal\":false,\"rawBarQ16\":";p+=String(unsigned(r.rawQ16));p+=",\"readSource\":";p+=String((unsigned long)r.source);p+=",\"session\":";p+=String((unsigned long)r.session);p+=",\"nonce\":";p+=String((unsigned long)r.nonce);p+=",\"poseFrame\":";p+=String((unsigned long)r.pose);p+=",\"epoch\":";p+=String((unsigned long)r.epoch);p+='}';}p+="]}";
  p+='}';
  server.sendHeader("Cache-Control","no-store");server.send(200,"application/json",p);
}
void routePost(const char *operation) {
  if(!allowWebRequest())return;
  const bool automatic=!strcmp(operation,"goto")||!strcmp(operation,"path")||!strcmp(operation,"avoid")||!strcmp(operation,"route")||!strcmp(operation,"move")||!strcmp(operation,"turn")||!strcmp(operation,"arc");
  if(((automatic&&strcmp(operation,"goto"))||!strcmp(operation,"drive"))&&!takeWebSnapshot().consoleMode){respondJson(false,"Switch explicitly to the full console owner before manual or route control",409,takeWebSnapshot().epoch);return;}
  const bool linkOperation=!strcmp(operation,"fpga-start")||!strcmp(operation,"fpga-cancel");
  const bool localControl=!strcmp(operation,"inspection-arm")||!strcmp(operation,"inspection-calibration");
  const bool scanOperation=!strcmp(operation,"scan-configure")||!strcmp(operation,"scan-start")||!strcmp(operation,"scan-continue");
  if(!automatic&&!linkOperation&&!localControl&&!scanOperation&&strcmp(operation,"drive")&&strcmp(operation,"stop")&&strcmp(operation,"estop")&&strcmp(operation,"clear")&&strcmp(operation,"touch")&&strcmp(operation,"zero")&&strcmp(operation,"imu-reconnect")){respondJson(false,"Unsupported R23 operation",410);return;}
  if(!strcmp(operation,"stop")||!strcmp(operation,"estop")) {
    portENTER_CRITICAL(&webMux);webStopRequest|=!strcmp(operation,"estop")?2:1;portEXIT_CRITICAL(&webMux);
    // Request acceptance is distinct from motor-loop confirmation in status.
    respondJson(true,"",200,takeWebSnapshot().epoch);return;
  }
  WebCommand cmd;static uint32_t nextId=0;
  cmd.id=++nextId;cmd.receivedMs=millis();
  const String requestSession=server.arg("bootSession");
  if(!server.hasArg("bootSession")||requestSession.length()!=16||!plainWebText(requestSession)||strcmp(requestSession.c_str(),bootSession)) {
    respondJson(false,"Device restarted; refresh status and operate again",409,takeWebSnapshot().epoch);return;
  }
  if(!getUintArg("epoch",cmd.epoch)){respondJson(false,"Wait for current status epoch",409,takeWebSnapshot().epoch);return;}
  const String requestLease=server.arg("leaseToken");
  if(requestLease.length()>16||!plainWebText(requestLease)){respondJson(false,"Invalid control page lease",400);return;}
  snprintf(cmd.leaseToken,sizeof(cmd.leaseToken),"%s",requestLease.c_str());
  if(!strcmp(operation,"touch")) {
    const uint32_t epoch=takeWebSnapshot().epoch;
    portENTER_CRITICAL(&webMux);
    const bool accepted=cmd.epoch==epoch && webLeaseToken[0] && !strcmp(cmd.leaseToken,webLeaseToken);
    if(accepted)webLastTouchMs=millis();
    portEXIT_CRITICAL(&webMux);
    respondJson(accepted,accepted?"":"Control page lease ended",409,epoch);return;
  }
  if(automatic) {
    uint32_t frame=0;const WebSnapshot s=takeWebSnapshot();
    if(!getUintArg("frame",frame)||!frame||frame!=s.poseFrame||!s.poseZeroed||uint32_t(millis()-s.ageMs)>250){respondJson(false,"Zero the stationary three-wheel car and use the current coordinate frame",409,s.epoch);return;}
    cmd.coordinateFrame=frame;cmd.pathPlan.poseFrame=frame;
  }
  if(linkOperation||localControl||scanOperation){
    const WebSnapshot s=takeWebSnapshot();uint32_t frame=0;
    if(!getUintArg("frame",frame)||!frame||frame!=s.poseFrame||uint32_t(millis()-s.ageMs)>250){respondJson(false,"Refresh current diagnostic coordinate frame",409,s.epoch);return;}
    cmd.coordinateFrame=frame;cmd.linkEpoch=s.fpga.observationEpoch;
  }
  bool valid=true;
  if(scanOperation){
    if(!strcmp(operation,"scan-configure")){const String text=server.arg("plan");ScanPlan parsed;valid=plainWebText(text)&&text.length()<=1800&&parsed.parse(text.c_str());cmd.operation=WebOp::ScanConfigure;if(valid)snprintf(cmd.scanText,sizeof(cmd.scanText),"%s",text.c_str());}
    else if(!strcmp(operation,"scan-start")){uint32_t m=0,c=0,confirm=0;valid=getUintArg("mode",m)&&m<=1&&getUintArg("continuous",c)&&c<=1&&getUintArg("confirm",confirm)&&confirm==1;cmd.operation=WebOp::ScanStart;cmd.a=float(m);cmd.b=float(c);}
    else{uint32_t confirm=0;valid=getUintArg("confirm",confirm)&&confirm==1;cmd.operation=WebOp::ScanContinue;}
  }
  else if(linkOperation){
    uint32_t task=0,point=0,config=0;
    valid=getUintArg("task",task)&&getUintArg("point",point)&&getUintArg("config",config)&&task&&task<=65535&&point&&point<=65535&&config==4;
    cmd.operation=!strcmp(operation,"fpga-start")?WebOp::FpgaStart:WebOp::FpgaCancel;
    cmd.linkTask=uint16_t(task);cmd.linkPoint=uint16_t(point);cmd.linkConfig=uint16_t(config);
    uint32_t taskMode=0;if(server.hasArg("mode"))valid=valid&&getUintArg("mode",taskMode)&&taskMode<=1;cmd.a=float(taskMode);
  }
  else if(localControl){
    uint32_t value=0,confirm=0;valid=getUintArg("value",value)&&value<=1;
    if(value)valid=valid&&getUintArg("confirm",confirm)&&confirm==1;
    cmd.operation=!strcmp(operation,"inspection-arm")?WebOp::InspectionArm:WebOp::InspectionCalibration;cmd.a=float(value);
    uint32_t controlOwner=0;if(server.hasArg("owner"))valid=valid&&getUintArg("owner",controlOwner)&&controlOwner<=1;cmd.b=float(controlOwner);
  }
  else if(!strcmp(operation,"drive")){cmd.operation=WebOp::Drive;valid=getFloatArg("v",cmd.a)&&getFloatArg("w",cmd.b)&&fabsf(cmd.a)<=WEB_MAX_LINEAR_MM_S&&fabsf(cmd.b)<=WEB_MAX_ANGULAR_DEG_S;}
  else if(!strcmp(operation,"move")){cmd.operation=WebOp::Move;valid=getFloatArg("mm",cmd.a)&&getFloatArg("speed",cmd.b)&&fabsf(cmd.a)<=5000&&cmd.b>=20&&cmd.b<=WEB_MAX_LINEAR_MM_S;}
  else if(!strcmp(operation,"turn")){cmd.operation=WebOp::Turn;valid=getFloatArg("deg",cmd.a)&&getFloatArg("speed",cmd.b)&&fabsf(cmd.a)<=360&&cmd.b>=20&&cmd.b<=MAX_TURN_WHEEL_MM_S;}
  else if(!strcmp(operation,"arc")){cmd.operation=WebOp::Arc;valid=getFloatArg("radius",cmd.a)&&getFloatArg("deg",cmd.b)&&getFloatArg("speed",cmd.c)&&cmd.a>=TRACK_EFFECTIVE_MM*.5f&&cmd.a<=10000&&fabsf(cmd.b)<=360&&cmd.c>=20&&cmd.c<=WEB_MAX_LINEAR_MM_S;}
  else if(!strcmp(operation,"goto")){
    cmd.operation=WebOp::Goto;
    valid=getFloatArg("x",cmd.a)&&getFloatArg("y",cmd.b)&&getFloatArg("speed",cmd.c)&&cmd.c>=NAV_MIN_SPEED&&cmd.c<=WEB_MAX_LINEAR_MM_S&&fabsf(cmd.a)<=NAV_COORD_LIMIT_MM&&fabsf(cmd.b)<=NAV_COORD_LIMIT_MM;
  }
  else if(!strcmp(operation,"path")||!strcmp(operation,"avoid")) {
    const bool guarded=!strcmp(operation,"avoid");cmd.operation=guarded?WebOp::AvoidPath:WebOp::Path;
    float speed=0;const String points=server.arg("points");
    valid=getFloatArg("speed",speed)&&speed<=WEB_MAX_LINEAR_MM_S&&server.hasArg("points")&&plainWebText(points)&&parsePathPlan(points.c_str(),speed,cmd.pathPlan);
    if(valid){cmd.pathPlan.poseFrame=cmd.coordinateFrame;cmd.pathPlan.guarded=guarded;}
    if(valid&&guarded){const String map=server.arg("map");valid=server.hasArg("map")&&plainWebText(map)&&ObstacleGeometry::parse(map.c_str(),cmd.pathPlan.obstacles);}
  }
  else if(!strcmp(operation,"route")) {
    cmd.operation=WebOp::Route;float speed=0;const String text=server.arg("plan");
    valid=getFloatArg("speed",speed)&&speed<=WEB_MAX_LINEAR_MM_S&&server.hasArg("plan")&&plainWebText(text)&&parseRoutePlan(text.c_str(),speed,TRACK_EFFECTIVE_MM,cmd.routePlan);
  }
  else if(!strcmp(operation,"clear"))cmd.operation=WebOp::Clear;
  else if(!strcmp(operation,"zero"))cmd.operation=WebOp::Zero;
  else if(!strcmp(operation,"imu-reconnect"))cmd.operation=WebOp::ImuReconnect;

  else valid=false;
  if(!valid){respondJson(false,"Invalid arguments",400);return;}
  if(!webCommands||!webResults){respondJson(false,"Web bridge unavailable",503);return;}
  WebResult result;
  while(xQueueReceive(webResults,&result,0)==pdTRUE){}
  if(xQueueSend(webCommands,&cmd,0)!=pdTRUE){respondJson(false,"Command queue busy",409);return;}
  bool matched=false;const uint32_t waitingSince=millis();
  for(;;) {
    const uint32_t elapsed=uint32_t(millis()-waitingSince);
    if(elapsed>=100)break;
    const uint32_t remaining=100-elapsed;
    if(xQueueReceive(webResults,&result,pdMS_TO_TICKS(remaining))!=pdTRUE)break;
    if(result.id==cmd.id){matched=true;break;}
    // A late reply for an earlier timed-out HTTP request is not this command's
    // result. Keep waiting: returning early could leave a fresh move queued.
  }
  if(!matched) {
    respondJson(false,"Command acknowledgement timeout",504);return;
  }
  respondJson(result.ok,result.ok?"":"Stop first, refresh status, check fault/authorization",409,result.epoch,result.leaseToken);
}
void setupHttp() {
  const char *collectedHeaders[]={"Origin"};server.collectHeaders(collectedHeaders,1);
  server.on("/",HTTP_GET,[](){if(allowWebRequest()){
    server.sendHeader("Cache-Control","no-store");
    server.sendHeader("Content-Security-Policy","frame-ancestors 'none'; base-uri 'none'; form-action 'self'");
    server.sendHeader("X-Frame-Options","DENY");
#ifdef ARDUINO
    server.sendHeader("Content-Encoding","gzip");
    server.sendBinary(200,"text/html; charset=utf-8",reinterpret_cast<const char*>(INDEX_GZIP),sizeof(INDEX_GZIP));
#else
    server.send_P(200,"text/html; charset=utf-8",INDEX_HTML);
#endif
  }});
  server.on("/console",HTTP_GET,[](){if(!allowWebRequest())return;server.sendHeader("Cache-Control","no-store");
#ifdef ARDUINO
    server.sendHeader("Content-Encoding","gzip");server.sendBinary(200,"text/html; charset=utf-8",reinterpret_cast<const char*>(CONSOLE_GZIP),sizeof(CONSOLE_GZIP));
#else
    server.send_P(200,"text/html; charset=utf-8",CONSOLE_HTML);
#endif
  });
  server.on("/api/status",HTTP_GET,[](){handleStatus(false);});
  server.on("/api/status",HTTP_POST,[](){handleStatus(true);});
  server.on("/api/inspection/arm",HTTP_POST,[](){routePost("inspection-arm");});
  server.on("/api/inspection/calibration",HTTP_POST,[](){routePost("inspection-calibration");});
  server.on("/api/scan/configure",HTTP_POST,[](){routePost("scan-configure");});
  server.on("/api/scan/start",HTTP_POST,[](){routePost("scan-start");});
  server.on("/api/scan/continue",HTTP_POST,[](){routePost("scan-continue");});
  server.on("/api/touch",HTTP_POST,[](){routePost("touch");});
  server.on("/api/drive",HTTP_POST,[](){routePost("drive");});
  server.on("/api/goto",HTTP_POST,[](){routePost("goto");});
  server.on("/api/move",HTTP_POST,[](){routePost("move");});
  server.on("/api/turn",HTTP_POST,[](){routePost("turn");});
  server.on("/api/arc",HTTP_POST,[](){routePost("arc");});
  server.on("/api/route",HTTP_POST,[](){routePost("route");});
  server.on("/api/path",HTTP_POST,[](){routePost("path");});
  server.on("/api/avoid",HTTP_POST,[](){routePost("avoid");});
  server.on("/api/stop",HTTP_POST,[](){routePost("stop");});
  server.on("/api/estop",HTTP_POST,[](){routePost("estop");});
  server.on("/api/clear",HTTP_POST,[](){routePost("clear");});
  server.on("/api/zero",HTTP_POST,[](){routePost("zero");});
  server.on("/api/imu/reconnect",HTTP_POST,[](){routePost("imu-reconnect");});
  server.on("/api/fpga/start",HTTP_POST,[](){routePost("fpga-start");});
  server.on("/api/fpga/cancel",HTTP_POST,[](){routePost("fpga-cancel");});
  server.onNotFound([](){if(allowWebRequest())server.send(404,"text/plain","Not found");});
#ifdef ARDUINO
  const bool started=server.begin();
  portENTER_CRITICAL(&webMux);httpStarted=started;portEXIT_CRITICAL(&webMux);
#else
  server.begin();
#endif
}
void setupWifi() {
  WiFi.mode(WIFI_AP);
  WiFi.setSleep(false);
  // Bounded boot-only retries. Never tear down a live AP during a task.
  apStarted=false;
  for(unsigned attempt=0;attempt<3&&!apStarted;attempt++) {
    apStarted=WiFi.softAP(AP_SSID,AP_PASSWORD);
    if(!apStarted)delay(100);
  }
  console.printf("AP: %s (%s) IP %s\n",AP_SSID,apStarted?"OK":"FAILED",WiFi.softAPIP().toString().c_str());
}
void webTask(void *) {
  setupHttp();
#ifdef ARDUINO
  // IDF runs its own bounded HTTP task. This one-time bootstrap task exits.
  vTaskDelete(nullptr);
#else
  for(;;){server.handleClient();vTaskDelay(pdMS_TO_TICKS(2));}
#endif
}
