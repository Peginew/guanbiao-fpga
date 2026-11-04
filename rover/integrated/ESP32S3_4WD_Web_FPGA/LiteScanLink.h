#pragma once
#include "WireCodecV4.h"
#include "InspectionExecutor.h"
#include <cstring>
struct FpgaLinkSnapshot {
 bool online=false,negotiated=false,visionFresh=false,located=false,locked=false,readable=false,healthy=false,candidateRead=false,formalReadingValid=false,benchOnly=true,refValid=false;
 bool canStart=false,stationaryReport=false,motionLocked=true,localArmed=false,calibrationConfirmed=false;
 std::uint32_t localSession=0,peerSession=0,linkNonce=0,ageMs=0xffffffffu,visionAgeMs=0xffffffffu,txFrames=0,rxFrames=0,rxBytes=0,crcErrors=0,formatErrors=0,staleFrames=0,disconnects=0,motionRejected=0,partialTimeouts=0;
 std::uint16_t taskId=0,pointId=0,configId=4;std::uint32_t observationEpoch=1,poseFrame=1,actionId=0;
 std::uint8_t taskState=0,ackCode=0,pipelineState=0,quality=0,refMode=0,workflowStage=0,actionStatus=3,actionPhase=0,reason=0;
 std::uint32_t sourceFrame=0,cameraSource=0,observationSource=0,readSourceFrame=0,sourceFloor=0,windowId=0;
 std::uint16_t centerX=0,centerY=0,diameter=0,boxHeight=0,rawBarQ16=0,refHundredths=0,readAgeMs=0xffff,observationFlags=0;
 std::int16_t boxLeft=0,boxTop=0,boxRight=0,boxBottom=0;std::int32_t yawRelMdeg=0,deltaYawMdeg=0,deltaTranslationMm=0;
 std::uint16_t cumAngleCdeg=0,cumTranslationMm=0,stationaryMs=0,imuAgeMs=0xffff;std::uint32_t actions=0,taskElapsedMs=0,bindingToken=0,taskKey=0;bool readyStep=false,readyRead=false;
};


class FpgaUartLink {
 public:enum TaskState:std::uint8_t {Idle,AwaitStart,Observing,Completed,AwaitCancel,Cancelled,Failed};
 private:
 static gb4::Reason reason(InspectionExecutor::Reason r){using R=InspectionExecutor::Reason;switch(r){case R::NONE:return gb4::Reason::NONE;case R::USER_CANCEL:return gb4::Reason::USER_CANCEL;case R::LINK_STALE:return gb4::Reason::LINK_STALE;case R::IMU_STALE:return gb4::Reason::IMU_STALE;case R::CONTEXT_REVOKED:return gb4::Reason::CONTEXT_REVOKED;case R::ACTION_TIMEOUT:return gb4::Reason::ACTION_TIMEOUT;case R::ACTION_STALLED:return gb4::Reason::ACTION_STALLED;case R::ACTION_LIMIT:return gb4::Reason::ACTION_LIMIT;case R::ACTION_CONFLICT:return gb4::Reason::ACTION_CONFLICT;case R::TOTAL_BUDGET:return gb4::Reason::TOTAL_BUDGET;case R::TARGET_FOUND:return gb4::Reason::TARGET_FOUND;case R::OUTPUT_FAULT:return gb4::Reason::OUTPUT_FAULT;case R::IMU_FAULT:return gb4::Reason::IMU_FAULT;case R::PROTOCOL:return gb4::Reason::PROTOCOL_MISMATCH;}return gb4::Reason::PROTOCOL_MISMATCH;}
 static gb4::FeedbackStatus phase(InspectionExecutor::Status p){using S=InspectionExecutor::Status;switch(p){case S::IDLE:case S::DONE:return gb4::FeedbackStatus::DONE;case S::ACCEPTED:return gb4::FeedbackStatus::ACCEPTED;case S::RUNNING:return gb4::FeedbackStatus::RUNNING;case S::SETTLING:return gb4::FeedbackStatus::SETTLING;case S::STOPPED_EARLY:return gb4::FeedbackStatus::STOPPED_EARLY;case S::REJECTED:return gb4::FeedbackStatus::REJECTED;case S::FAULT:return gb4::FeedbackStatus::FAILED;}return gb4::FeedbackStatus::FAILED;}
 InspectionExecutor&e_;InspectionExecutor::Sensors s_;FpgaLinkSnapshot st_;
 std::uint8_t rx_[32]={},lastRequest_[10]={};unsigned used_=0;
 std::uint32_t byteAt_=0,attemptAt_=0,helloAt_=0,controlAt_=0,cameraAt_=0,stateAt_=0,lastServiceAt_=0,parkAt_=0,startAt_=0,commandAt_=0;
 std::uint32_t pose_=1,plan_=1,taskKey_=0,allocator_=0,requestEpoch_=0,lastTrigger_=0,lastRead_=0;
 std::uint32_t readAt_=0,prepareAt_=0,imageAt_=0,actionAt_=0;bool readKnown_=false,preparing_=false,imageWaiting_=false;
 std::uint32_t scopePlan_=0,scopePoint_=0,scopePose_=0,pointAt_=0,firstTaskAt_=0;bool scopeKnown_=false,taskClockKnown_=false;
 unsigned pointActions_=0,maxSteps_=4;float cumulativeAngle_=0,lastHeading_=0;std::uint32_t lastSample_=0;bool countScanMotion_=false;
 std::int16_t direction_=10000;gb4::TaskMode mode_=gb4::TaskMode::FORMAL_REVIEW;
 bool reconnect_=true,helloSent_=false,echoPending_=false,echoSent_=false,controlKnown_=false,cameraKnown_=false,cameraAlive_=false,seqKnown_=false;
 bool stateSent_=false,parkConfirmed_=false,commandPending_=false,commandSent_=false,failurePending_=false,requestKnown_=false,triggerKnown_=false,lastReadKnown_=false;
 bool floorKnown_=false,locatorKnown_=false;std::uint32_t floor_=0,locator_=0,locatorAt_=0;std::uint16_t locatorFlags_=0,locatorAge_=0xffff;
 std::uint16_t txSeq_=0,rxSeq_=0,startSeq_[3]={};unsigned tries_=0,prepared_=99;
 gb4::Msg command_=gb4::Msg::START;
 struct Ack {std::uint16_t seq;std::uint8_t type,code,action;std::uint32_t key,epoch;};Ack ack_[4];unsigned ar_=0,aw_=0,an_=0;
 bool taskActive()const{return st_.taskState==AwaitStart||st_.taskState==Observing||st_.taskState==AwaitCancel;}
 static std::uint16_t sat(std::uint32_t n){return std::uint16_t(n>65535?65535:n);}
 bool localContext()const{return scopeKnown_&&scopePose_==s_.poseFrame&&s_.poseValid&&e_.context().poseFrame==scopePose_;}
 std::uint32_t parkAge(std::uint32_t n)const{return parkConfirmed_?n-parkAt_:0;}
 bool budget(std::uint32_t n)const{return scopeKnown_&&n-pointAt_<600000&&taskClockKnown_&&n-firstTaskAt_<300000&&cumulativeAngle_<=360.f;}
 bool readyBase(std::uint32_t n)const{return st_.taskState==AwaitStart||st_.taskState==Observing?e_.active()&&e_.armed()&&e_.calibrated()&&localContext()&&budget(n)&&executionLinkFresh(n)&&!e_.actionActive()&&InspectionExecutor::rawQuiet(s_)&&parkConfirmed_&&parkAge(n)>=6000:false;}
 bool readyStep(std::uint32_t n)const{return readyBase(n)&&pointActions_<maxSteps_&&cumulativeAngle_+10.f<=360.f;}
 bool readyRead(std::uint32_t n)const{return readyBase(n);}
 void clearVisual(){floorKnown_=readKnown_=preparing_=imageWaiting_=locatorKnown_=false;st_.located=st_.locked=st_.readable=false;st_.observationFlags=0;st_.observationSource=0;}
 // Completed READ is durable until explicit context replacement/revocation.
 // Live visual permission is independently cleared by normal IDLE observations.
 void clearResult(){st_.candidateRead=false;st_.readSourceFrame=0;st_.rawBarQ16=0;st_.readAgeMs=0xffff;}
 void fail(gb4::Reason r){e_.fail(InspectionExecutor::Reason::PROTOCOL);st_.taskState=Failed;st_.workflowStage=9;st_.reason=std::uint8_t(r);commandPending_=false;clearVisual();clearResult();failurePending_=st_.negotiated&&taskKey_!=0;stateSent_=false;}
 void lose(){if(st_.negotiated)++st_.disconnects;if(taskActive())fail(gb4::Reason::LINK_STALE);else e_.cancel();st_.negotiated=false;st_.peerSession=st_.linkNonce=st_.bindingToken=0;reconnect_=true;controlKnown_=cameraKnown_=seqKnown_=false;commandPending_=failurePending_=false;clearVisual();clearResult();}
 InspectionExecutor::Context context(std::uint32_t ep)const{auto c=e_.context();c.epoch=ep;return c;}
 void header(std::uint8_t*b,gb4::Msg t,bool active){using namespace FpgaWire;std::memset(b,0,32);b[3]=std::uint8_t(t);put16(b+4,++txSeq_);put32(b+8,st_.bindingToken);put32(b+12,active?taskKey_:0);put32(b+16,e_.motionEpoch());b[6]=active?std::uint8_t(e_.feedback().id):0;}
 void queueAck(const std::uint8_t*b,gb4::AckStatus code){if(an_==4){fail(gb4::Reason::PROTOCOL_MISMATCH);return;}ack_[aw_]={FpgaWire::u16(b+4),b[3],std::uint8_t(code),b[6],FpgaWire::u32(b+12),e_.motionEpoch()};aw_=(aw_+1)%4;++an_;}
 void beginReadPrepare(std::uint32_t n){if(!preparing_&&!readKnown_){preparing_=true;prepareAt_=n;}}
 void receive(const std::uint8_t*b,std::uint32_t now){
  using namespace FpgaWire;const auto type=gb4::Msg(b[3]);const auto*p=b+20;
  if(!contract(b)){++st_.formatErrors;if(valid(b)&&type==gb4::Msg::STEP_REQUEST&&u32(b+8)==st_.bindingToken&&u32(b+12)==taskKey_&&requestKnown_&&b[6]==e_.request().id)fail(gb4::Reason::ACTION_CONFLICT);return;}
  if(type==gb4::Msg::HELLO){
   if(u32(p)!=FPGA_BUILD){++st_.formatErrors;return;}
   const auto token=u32(b+8),peer=u32(b+12);
   if(!token&&!peer){if(st_.negotiated||echoSent_)lose();return;}
   if(!token||peer!=st_.localSession){++st_.staleFrames;return;}
   if(st_.negotiated&&token!=st_.bindingToken){lose();return;}
   st_.bindingToken=st_.linkNonce=st_.peerSession=token;st_.negotiated=true;echoPending_=true;return;
  }
  if(!st_.negotiated||!echoSent_||u32(b+8)!=st_.bindingToken){++st_.staleFrames;return;}
  const auto key=u32(b+12),epoch=u32(b+16);const bool forward=!seqKnown_||ahead16(u16(b+4),rxSeq_);const bool stop=type==gb4::Msg::STOP_ACTION||type==gb4::Msg::CANCEL;
  if(!forward&&!stop){++st_.staleFrames;return;}
  const bool idle=key==0&&(!taskActive()||st_.taskState==AwaitStart);
  if(!idle&&(!taskActive()||key!=taskKey_)){++st_.staleFrames;return;}
  const bool duplicate=type==gb4::Msg::STEP_REQUEST&&requestKnown_&&b[6]==e_.request().id;
  if(!stop&&!duplicate&&epoch!=e_.motionEpoch()){++st_.staleFrames;return;}
  if(forward){seqKnown_=true;rxSeq_=u16(b+4);++st_.rxFrames;}
  if(type==gb4::Msg::OBSERVATION){
   if(!forward)return;controlKnown_=true;controlAt_=now;st_.workflowStage=p[8];st_.reason=p[9];const auto flags=u16(p+6);const auto source=u32(p);const auto age=sat(std::uint32_t(u16(p+4))+4);
   if(!idle&&(p[8]==6||p[8]==7||(flags&256)))beginReadPrepare(now);
   if(flags&1024){if(flags&~1027u){++st_.formatErrors;return;}cameraAlive_=bool(flags&1);if(cameraAlive_&&(!cameraKnown_||ahead32(source,st_.cameraSource))){cameraKnown_=true;cameraAt_=now;st_.cameraSource=source;}return;}
   if(idle){clearVisual();return;}
   if(flags&512){fail(gb4::Reason::OBSERVATION_ERROR);return;}
   st_.healthy=bool(flags&2);st_.observationFlags=flags;
   if(p[8]==6||p[8]==7||(flags&256))beginReadPrepare(now);
   if(flags&128){
    if((flags&(4|8|16|32|256|1024))||u16(p+4)!=0xffff||p[8]!=6){fail(gb4::Reason::PROTOCOL_MISMATCH);return;}
    if(!readyRead(now)){fail(gb4::Reason::MOTION_DISALLOWED);return;}
    if(!readKnown_){readKnown_=true;readAt_=now;}if(!floorKnown_||ahead32(source,floor_)){floor_=source;floorKnown_=true;st_.sourceFloor=source;}preparing_=false;imageWaiting_=false;return;
   }
   const bool loc=(flags&32)?(age<=1100&&(flags&35)==35&&!(flags&(4|8))):(flags&4)?(age<=200&&(flags&23)==23):false;
   if(loc&&(!locatorKnown_||ahead32(source,locator_))){locatorKnown_=true;locator_=source;locatorAge_=age;locatorFlags_=flags;locatorAt_=now;st_.observationSource=st_.sourceFrame=source;st_.located=bool(flags&4);st_.locked=st_.located;imageAt_=now;}
   return;
  }
  if(type==gb4::Msg::ACK){st_.ackCode=p[3];if(key!=taskKey_)return;if(p[2]==3&&st_.taskState==AwaitStart){bool ours=false;for(unsigned i=0;i<tries_;i++)ours=ours||u16(p)==startSeq_[i];if(ours){if(p[3]<=1){st_.taskState=Observing;commandPending_=false;stateSent_=false;imageWaiting_=false;}else fail(gb4::Reason::MOTION_DISALLOWED);}}else if(p[2]==4&&st_.taskState==AwaitCancel){st_.taskState=Cancelled;commandPending_=false;}return;}
  if(idle||key!=taskKey_||st_.taskState!=Observing){++st_.staleFrames;return;}
  if(type==gb4::Msg::STEP_REQUEST){
   if(duplicate){const bool exact=epoch==requestEpoch_&&std::memcmp(lastRequest_,p,10)==0;queueAck(b,exact?gb4::AckStatus::DUPLICATE:gb4::AckStatus::REJECTED);if(!exact)fail(gb4::Reason::ACTION_CONFLICT);stateSent_=false;return;}
   const auto source=u32(p);if(!readyStep(now)||i16(p+6)!=direction_||(triggerKnown_&&!ahead32(source,lastTrigger_))||b[6]!=(e_.request().id+1)){queueAck(b,gb4::AckStatus::REJECTED);fail(gb4::Reason::MOTION_DISALLOWED);return;}
   InspectionExecutor::Request r{b[6],source,epoch,i16(p+6),15000,5000};const auto a=e_.accept(context(epoch),r,s_,now);
   if(a!=InspectionExecutor::Ack::OK){queueAck(b,gb4::AckStatus::REJECTED);fail(gb4::Reason::ACTION_LIMIT);return;}
   ++pointActions_;lastTrigger_=source;triggerKnown_=true;requestKnown_=true;requestEpoch_=epoch;std::memcpy(lastRequest_,p,10);actionAt_=now;countScanMotion_=true;clearVisual();parkConfirmed_=false;stateSent_=false;queueAck(b,gb4::AckStatus::ACCEPTED);return;
  }
  if(type==gb4::Msg::STOP_ACTION){
   // STOP is stop-only for this exact task. A lost STEP must not invent its ID.
   if(b[6]!=e_.request().id||(epoch!=requestEpoch_&&epoch!=e_.motionEpoch())){queueAck(b,gb4::AckStatus::BAD_CONTEXT);return;}
   if(e_.actionActive())e_.stopAction(context(e_.motionEpoch()),b[6]);
   queueAck(b,gb4::AckStatus::ACCEPTED);stateSent_=false;return;
  }
  if(type==gb4::Msg::CANCEL){e_.cancel();st_.taskState=Cancelled;commandPending_=false;clearVisual();clearResult();queueAck(b,gb4::AckStatus::CANCELLED);stateSent_=false;return;}
  if(type==gb4::Msg::FAILURE){fail(gb4::Reason(p[4]));return;}
  if(type==gb4::Msg::RESULT){const auto source=u32(p);const bool ok=readyRead(now)&&floorKnown_&&readKnown_&&now-readAt_<gb4::cfg::READ_TIMEOUT_MS&&std::uint32_t(u16(p+6))+4<=200&&ahead32(source,floor_)&&(!lastReadKnown_||ahead32(source,lastRead_));if(!ok){fail(gb4::Reason::FRAME_STALE);return;}st_.candidateRead=true;st_.readSourceFrame=source;st_.rawBarQ16=u16(p+4);st_.readAgeMs=u16(p+6)+4;st_.taskState=Completed;st_.workflowStage=8;lastRead_=source;lastReadKnown_=true;e_.finishTask();queueAck(b,gb4::AckStatus::ACCEPTED);stateSent_=false;return;}
 }
 public:
 explicit FpgaUartLink(InspectionExecutor&e):e_(e){}
 bool needsSession()const{return reconnect_;}bool online(std::uint32_t n)const{return st_.negotiated&&echoSent_&&controlKnown_&&n-controlAt_<=250;}
 bool stateUsable(std::uint32_t n)const{return online(n);}bool executionLinkFresh(std::uint32_t n)const{return online(n)&&cameraKnown_&&cameraAlive_&&n-cameraAt_<=500;}
 void actuatorStateChanged(){stateSent_=false;clearVisual();if(e_.actionActive())parkConfirmed_=false;}
 void transportFailure(){lose();}
 void beginAttempt(std::uint32_t session,std::uint32_t now){e_.cancel();st_=FpgaLinkSnapshot{};st_.configId=4;st_.localSession=session?session:1;taskKey_=allocator_=0;reconnect_=false;helloSent_=echoPending_=echoSent_=controlKnown_=cameraKnown_=cameraAlive_=seqKnown_=stateSent_=commandPending_=commandSent_=failurePending_=requestKnown_=triggerKnown_=lastReadKnown_=parkConfirmed_=false;tries_=0;prepared_=99;used_=an_=ar_=aw_=0;txSeq_=rxSeq_=0;attemptAt_=now;clearVisual();}
 void beginPointScope(std::uint32_t plan,std::uint32_t point,std::uint32_t pose,std::uint32_t now){if(scopeKnown_&&scopePlan_==plan&&scopePoint_==point&&scopePose_==pose)return;if(taskActive())fail(gb4::Reason::CONTEXT_REVOKED);scopeKnown_=true;scopePlan_=plan;scopePoint_=point;scopePose_=pose;pointAt_=now;taskClockKnown_=false;pointActions_=0;cumulativeAngle_=0;lastHeading_=s_.headingDeg;lastSample_=s_.imuSample;countScanMotion_=false;}
 void configurePlan(std::uint32_t plan,unsigned steps,std::int16_t step,gb4::TaskMode m,std::uint32_t=300000){if(taskActive())return;plan_=plan;maxSteps_=steps;direction_=step;mode_=m;}
 void vehicleState(const InspectionExecutor::Sensors&s,std::uint32_t,std::uint32_t now){lastServiceAt_=now;s_=s;s_.linkFresh=executionLinkFresh(now);pose_=s.poseFrame;const auto before=e_.motionEpoch();e_.tick(s_,now);if(before!=e_.motionEpoch())actuatorStateChanged();if(!InspectionExecutor::rawQuiet(s_)||e_.actionActive())parkConfirmed_=false;else if(e_.stationaryAge(now)>=300&&!parkConfirmed_){parkConfirmed_=true;parkAt_=now;}
  if(scopeKnown_&&countScanMotion_&&!s_.navOwner&&!e_.aligning()&&s_.imuSample!=lastSample_){cumulativeAngle_+=std::fabs(s_.headingDeg-lastHeading_);lastHeading_=s_.headingDeg;lastSample_=s_.imuSample;}else if(s_.imuSample!=lastSample_){lastHeading_=s_.headingDeg;lastSample_=s_.imuSample;}
  if(taskActive()&&st_.taskState!=AwaitCancel&&!e_.active())fail(reason(e_.feedback().reason));expire(now);
 }
 void expire(std::uint32_t n){if(used_&&n-byteAt_>=30){used_=0;++st_.partialTimeouts;}if(st_.negotiated&&n-(controlKnown_?controlAt_:attemptAt_)>500){lose();return;}if(!taskActive()||st_.taskState==AwaitCancel)return;if(!online(n)){fail(gb4::Reason::STATE_STALE);return;}if(!localContext()||!budget(n)){fail(gb4::Reason::TOTAL_BUDGET);return;}if(st_.taskState==AwaitStart&&n-startAt_>=1000){fail(gb4::Reason::ACTION_TIMEOUT);return;}if(e_.driving()&&e_.motionEpoch()==requestEpoch_&&n-actionAt_>=1000){fail(gb4::Reason::ACTION_STALLED);return;}if(preparing_&&!readKnown_&&n-prepareAt_>=1000){fail(gb4::Reason::SOURCE_FENCE_TIMEOUT);return;}if(readKnown_&&n-readAt_>=gb4::cfg::READ_TIMEOUT_MS){fail(gb4::Reason::READ_TIMEOUT);return;}if(st_.taskState==Observing&&readyRead(n)&&!preparing_&&!readKnown_){if(!imageWaiting_){imageWaiting_=true;imageAt_=n;}else if(n-imageAt_>=3500){fail(gb4::Reason::OBSERVATION_ERROR);return;}}}
 void feed(std::uint8_t b,std::uint32_t n){if(used_&&n-byteAt_>=30){used_=0;++st_.partialTimeouts;}byteAt_=n;++st_.rxBytes;if(!used_){if(b==0xa5)rx_[used_++]=b;return;}if(used_==1){if(b==0x5a)rx_[used_++]=b;else used_=b==0xa5?1:0;return;}rx_[used_++]=b;if(used_<32)return;used_=0;if(FpgaWire::u16(rx_+30)!=FpgaWire::crc(rx_+2,28)){++st_.crcErrors;return;}receive(rx_,n);}
 bool startTask(std::uint16_t task,std::uint16_t point,std::uint16_t cfg,std::uint32_t epoch,std::uint32_t n,gb4::TaskMode mode=gb4::TaskMode::FORMAL_REVIEW){if(!executionLinkFresh(n)||!parkConfirmed_||parkAge(n)<6000||taskActive()||!task||!point||cfg!=4||!plan_||!maxSteps_||maxSteps_>36||(direction_!=10000&&direction_!=-10000)||mode!=mode_||allocator_==0xffffffffu)return false;beginPointScope(plan_,point,pose_,n);if(!taskClockKnown_){taskClockKnown_=true;firstTaskAt_=n;}if(!budget(n))return false;const auto remaining=300000u-(n-firstTaskAt_);InspectionExecutor::Context c{st_.localSession,st_.bindingToken,st_.bindingToken,epoch,pose_,task,point,4};if(!e_.begin(c,maxSteps_>pointActions_?maxSteps_-pointActions_:1,s_,n,remaining))return false;taskKey_=++allocator_;st_.taskKey=taskKey_;st_.taskId=task;st_.pointId=point;st_.taskState=AwaitStart;st_.workflowStage=1;startAt_=n;command_=gb4::Msg::START;commandPending_=true;commandSent_=false;tries_=0;prepared_=99;requestKnown_=triggerKnown_=false;stateSent_=false;clearVisual();clearResult();return true;}
 bool cancelTask(std::uint16_t task,std::uint16_t point,std::uint16_t cfg,std::uint32_t,std::uint32_t){if(task!=st_.taskId||point!=st_.pointId||cfg!=4)return false;if(!taskActive()){if(st_.taskState!=Completed)return false;e_.cancel();st_.taskState=Cancelled;clearVisual();clearResult();stateSent_=false;return true;}e_.cancel();st_.taskState=AwaitCancel;command_=gb4::Msg::CANCEL;commandPending_=true;commandSent_=false;tries_=0;clearVisual();clearResult();return true;}
 bool nextTx(std::uint32_t n,std::uint8_t*out){using namespace FpgaWire;expire(n);if(reconnect_)return false;const bool due=commandPending_&&command_==gb4::Msg::START&&(!commandSent_||n-commandAt_>=200)&&tries_<3,pre=due&&prepared_!=tries_;
  if(!st_.negotiated||echoPending_){if(helloSent_&&!echoPending_&&n-helloAt_<250)return false;header(out,gb4::Msg::HELLO,false);put32(out+12,st_.localSession);put32(out+16,gb4::kConfigSignature);auto*p=out+20;put32(p,ESP_BUILD);put16(p+4,127);p[6]=32;p[7]=4;helloAt_=n;helloSent_=true;if(echoPending_){echoPending_=false;echoSent_=true;stateSent_=false;attemptAt_=n;}}
  else if(an_){const auto a=ack_[ar_];ar_=(ar_+1)%4;--an_;header(out,gb4::Msg::ACK,false);put32(out+12,a.key);put32(out+16,a.epoch);out[6]=a.action;auto*p=out+20;put16(p,a.seq);p[2]=a.type;p[3]=a.code;}
  else if(failurePending_){header(out,gb4::Msg::FAILURE,true);put32(out+20,st_.observationSource);out[24]=st_.reason;failurePending_=false;}
  else if(pre||!stateSent_||n-stateAt_>=100){const bool active=!pre&&st_.taskState==Observing;header(out,gb4::Msg::STATE,active);auto*p=out+20;put16(p,sat(s_.imuAgeMs));put16(p+2,sat(parkAge(n)));p[4]=std::uint8_t(phase(e_.feedback().status))|(std::uint8_t(reason(e_.feedback().reason))<<3);p[5]=(s_.imuReady?1:0)|((s_.poseValid&&s_.poseFrame)?2:0)|((InspectionExecutor::rawQuiet(s_)&&e_.stationaryAge(n)>=300)?4:0)|(e_.armed()?8:0)|(e_.calibrated()?16:0)|((s_.fault||s_.estop||!s_.hardware)?32:0)|(readyStep(n)?64:0)|(readyRead(n)?128:0);stateAt_=n;stateSent_=true;if(pre)prepared_=tries_;}
  else if(commandPending_&&(!commandSent_||n-commandAt_>=200)){if(tries_>=3){fail(gb4::Reason::ACTION_TIMEOUT);return false;}header(out,command_,true);auto*p=out+20;if(command_==gb4::Msg::START){out[6]=0;put16(p,std::uint16_t(direction_));p[2]=std::uint8_t(mode_);startSeq_[tries_]=u16(out+4);}else p[0]=1;++tries_;commandAt_=n;commandSent_=true;}
  else return false;seal(out);++st_.txFrames;return true;
 }
 FpgaLinkSnapshot snapshot(std::uint32_t n)const{auto s=st_;const auto f=e_.feedback();s.online=online(n);s.ageMs=controlKnown_?n-controlAt_:0xffffffffu;s.visionAgeMs=locatorKnown_?n-locatorAt_:0xffffffffu;s.visionFresh=locatorKnown_&&std::uint32_t(locatorAge_)+s.visionAgeMs<=200;s.localArmed=e_.armed();s.calibrationConfirmed=e_.calibrated();s.motionLocked=!s.localArmed;s.readyStep=readyStep(n);s.readyRead=readyRead(n);s.stationaryMs=sat(parkAge(n));s.stationaryReport=InspectionExecutor::rawQuiet(s_)&&e_.stationaryAge(n)>=300;s.canStart=executionLinkFresh(n)&&s.stationaryReport&&parkConfirmed_&&parkAge(n)>=6000&&e_.armed()&&e_.calibrated()&&s_.poseValid&&!taskActive();s.observationEpoch=e_.motionEpoch();s.poseFrame=pose_;s.bindingToken=st_.bindingToken;s.taskKey=taskKey_;s.actionId=f.id;s.actionStatus=std::uint8_t(phase(f.status));s.yawRelMdeg=f.yawRel;s.deltaYawMdeg=f.deltaYaw;s.imuAgeMs=f.imuAgeMs;s.actions=pointActions_;s.cumAngleCdeg=sat(std::uint32_t(cumulativeAngle_*100));s.taskElapsedMs=taskClockKnown_?n-firstTaskAt_:0;s.formalReadingValid=false;return s;}
};
