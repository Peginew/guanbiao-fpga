#pragma once
#include <cmath>
#include <cstdint>
#include "ScanPlan.h"

// A real IMU/FG finite turn. Global pose and IMU zero are never modified.
class InspectionExecutor {
 public:
  enum class Reason:std::uint8_t {NONE=0,USER_CANCEL=1,LINK_STALE=2,IMU_STALE=3,CONTEXT_REVOKED=4,ACTION_TIMEOUT=5,ACTION_STALLED=6,ACTION_LIMIT=7,ACTION_CONFLICT=8,TOTAL_BUDGET=9,TARGET_FOUND=10,OUTPUT_FAULT=11,IMU_FAULT=12,PROTOCOL=13};
  enum class Status:std::uint8_t {IDLE=0,ACCEPTED=1,RUNNING=2,SETTLING=3,DONE=4,STOPPED_EARLY=5,REJECTED=6,FAULT=7};
  enum class Ack:std::uint8_t {OK=0,DUPLICATE=1,BAD_CONTEXT=2,STALE=3,BUSY=4,UNARMED=5,NOT_READY=6,RANGE=7,PROTOCOL=8};
  struct Sensors {bool hardware=false,fault=false,estop=false,imuReady=false,poseValid=false,braked=false,linkFresh=false,navOwner=false;std::uint32_t poseFrame=0,imuAgeMs=0xffffffffu,imuSample=0,fgQuietMs=0;float headingDeg=0,rateDegS=0,leftSpeed=0,rightSpeed=0,leftTravel=0,rightTravel=0;};
  struct Context {std::uint32_t localSession=0,peerSession=0,nonce=0,epoch=0,poseFrame=0;std::uint16_t task=0,point=0,config=4;bool operator==(const Context&o)const{return localSession==o.localSession&&peerSession==o.peerSession&&nonce==o.nonce&&poseFrame==o.poseFrame&&task==o.task&&point==o.point&&config==o.config;}};
  struct Request {std::uint32_t id=0,triggerSource=0,issueEpoch=0;std::int32_t amount=0;std::uint16_t rate=0,timeoutMs=0;bool sameAction(const Request&o)const{return id==o.id&&triggerSource==o.triggerSource&&issueEpoch==o.issueEpoch&&amount==o.amount&&rate==o.rate&&timeoutMs==o.timeoutMs;}};
  struct Output {float linearMmS=0,turnDegS=0;bool brake=true;};
  struct Feedback {std::uint32_t id=0;Status status=Status::IDLE;Reason reason=Reason::NONE;std::int32_t deltaYaw=0,yawRel=0,deltaTranslation=0;std::uint16_t stationaryMs=0,imuAgeMs=0xffff;};
 private:
  bool armed_=false,calibrated_=false,active_=false,executing_=false,settling_=false,known_=false,driveStarted_=false,early_=false,quiet_=false,align_=false;
  Context ctx_;Request req_;Output out_;Feedback fb_;std::uint32_t epoch_=1,taskAt_=0,actionAt_=0,quietAt_=0,progressAt_=0,actions_=0,ttl_=300000;
  float origin_=0,start_=0,progress_=0,lastHeading_=0,cumAngle_=0;std::uint32_t lastSample_=0;unsigned maxSteps_=0,trims_=0;int direction_=1;
  static float clamp(float v,float a,float b){return v<a?a:v>b?b:v;}
  static bool finite(const Sensors&s){return std::isfinite(s.headingDeg)&&std::isfinite(s.rateDegS)&&std::isfinite(s.leftSpeed)&&std::isfinite(s.rightSpeed)&&std::isfinite(s.leftTravel)&&std::isfinite(s.rightTravel);}
  static std::uint16_t sat(std::uint32_t n){return std::uint16_t(n>65535?65535:n);}
  static std::int32_t milli(float n){return std::int32_t(std::lround(clamp(n*1000,-2147483000.f,2147483000.f)));}
  void brake(){out_=Output{};}
  void update(const Sensors&s,std::uint32_t now){fb_.id=req_.id;fb_.stationaryMs=stationaryAge(now);fb_.imuAgeMs=sat(s.imuAgeMs);fb_.deltaYaw=finite(s)?milli(s.headingDeg-start_):0;fb_.yawRel=finite(s)?milli(s.headingDeg-origin_):0;}
  bool sensorOK(const Sensors&s)const{return finite(s)&&s.hardware&&!s.fault&&!s.estop&&!s.navOwner&&s.imuReady&&s.imuAgeMs<=180&&s.poseValid&&s.poseFrame==ctx_.poseFrame&&s.linkFresh;}
  void settling(bool early){brake();executing_=false;settling_=true;early_=early;quiet_=false;fb_.status=Status::SETTLING;fb_.reason=early?Reason::TARGET_FOUND:Reason::NONE;}
 public:
  bool armed()const{return armed_;}bool calibrated()const{return calibrated_;}bool active()const{return active_;}bool actionActive()const{return executing_||settling_;}bool driving()const{return executing_;}bool aligning()const{return align_;}
  const Context&context()const{return ctx_;}const Request&request()const{return req_;}const Output&output()const{return out_;}const Feedback&feedback()const{return fb_;}
  std::uint32_t motionEpoch()const{return epoch_;}std::uint32_t actions()const{return actions_;}std::uint32_t taskElapsed(std::uint32_t n)const{return active_||known_?n-taskAt_:0;}float originHeading()const{return origin_;}
  static bool rawQuiet(const Sensors&s){return finite(s)&&s.hardware&&!s.fault&&!s.estop&&!s.navOwner&&s.imuReady&&s.imuAgeMs<=180&&s.braked&&s.fgQuietMs>=150&&std::fabs(s.leftSpeed)<2&&std::fabs(s.rightSpeed)<2&&std::fabs(s.rateDegS)<=2;}
  void observeQuiet(const Sensors&s,std::uint32_t now){if(!rawQuiet(s)){quiet_=false;return;}if(!quiet_){quiet_=true;quietAt_=now;}}
  std::uint16_t stationaryAge(std::uint32_t n)const{return quiet_?sat(n-quietAt_):0;}
  void revokeArm(){armed_=false;brake();}
  bool confirmCalibration(bool v,const Sensors&s){if(active_||!rawQuiet(s))return false;calibrated_=v;if(!v)armed_=false;return true;}
  bool armLocal(bool v,const Sensors&s){if(!v){cancel();return true;}if(active_||!calibrated_||!rawQuiet(s)||!s.poseValid||!s.poseFrame||!s.linkFresh)return false;armed_=true;return true;}
  void fail(Reason r){brake();active_=executing_=settling_=false;armed_=false;quiet_=false;fb_.status=Status::FAULT;fb_.reason=r;}
  void cancel(Reason r=Reason::USER_CANCEL){fail(r);}
  bool begin(const Context&c,unsigned maxSteps,const Sensors&s,std::uint32_t now,std::uint32_t ttl=300000){
    if(active_||!armed_||!calibrated_||!c.localSession||!c.peerSession||!c.nonce||!c.task||!c.point||!c.poseFrame||c.config!=4||!maxSteps||maxSteps>36||!ttl||ttl>300000||!rawQuiet(s)||!s.linkFresh||s.poseFrame!=c.poseFrame||stationaryAge(now)<300)return false;
    ctx_=c;epoch_=c.epoch;active_=true;known_=executing_=settling_=driveStarted_=early_=align_=false;req_=Request{};fb_=Feedback{};brake();taskAt_=now;ttl_=ttl;maxSteps_=maxSteps;actions_=0;origin_=start_=lastHeading_=s.headingDeg;cumAngle_=0;lastSample_=s.imuSample;return true;
  }
  bool beginAlignment(const Context&c,float deltaDeg,const Sensors&s,std::uint32_t now){
    if(!std::isfinite(deltaDeg)||std::fabs(deltaDeg)>180||!begin(c,1,s,now,30000))return false;
    align_=true;req_={1,0,c.epoch,milli(deltaDeg),12000,28000};known_=true;start_=progress_=s.headingDeg;actionAt_=progressAt_=now;direction_=deltaDeg>=0?1:-1;trims_=0;fb_.id=1;
    if(std::fabs(deltaDeg)<=.3f)settling(false);else{executing_=true;fb_.status=Status::ACCEPTED;}return true;
  }
  Ack accept(const Context&c,const Request&r,const Sensors&s,std::uint32_t now){
    if(!active_||align_||!(c==ctx_))return Ack::BAD_CONTEXT;
    if(known_&&r.id==req_.id){if(req_.sameAction(r))return Ack::DUPLICATE;fail(Reason::ACTION_CONFLICT);return Ack::PROTOCOL;}
    if(!r.id||(known_&&std::uint32_t(r.id-req_.id)>=0x80000000u))return Ack::STALE;
    if(actionActive())return Ack::BUSY;if(c.epoch!=epoch_||r.issueEpoch!=epoch_)return Ack::STALE;
    if(!armed_||!calibrated_)return Ack::UNARMED;if(!sensorOK(s)||!rawQuiet(s)||stationaryAge(now)<300)return Ack::NOT_READY;
    if(actions_>=maxSteps_||std::abs(r.amount)!=10000||!r.rate||r.rate>15000||r.timeoutMs<1000||r.timeoutMs>5000)return Ack::RANGE;
    req_=r;known_=executing_=true;settling_=early_=driveStarted_=false;start_=progress_=s.headingDeg;actionAt_=progressAt_=now;trims_=0;direction_=r.amount>0?1:-1;++actions_;fb_.status=Status::ACCEPTED;fb_.reason=Reason::NONE;update(s,now);return Ack::OK;
  }
  Ack stopAction(const Context&c,std::uint32_t id){if(!active_||!(c==ctx_)||!known_||id!=req_.id)return Ack::BAD_CONTEXT;if(!actionActive())return Ack::DUPLICATE;if(!settling_)settling(true);return Ack::OK;}
  void notifyDriveStarted(){if(active_&&executing_&&!driveStarted_){driveStarted_=true;++epoch_;fb_.status=Status::RUNNING;}}
  // Normal completion keeps explicit local arm for an authorised queued point.
  // STOP/fault/link loss always cancels and revokes arm instead.
  void finishTask(){brake();active_=executing_=settling_=align_=false;}
  void tick(const Sensors&s,std::uint32_t now){
    observeQuiet(s,now);brake();if(!active_){update(s,now);return;}
    if(!sensorOK(s)){fail(!s.linkFresh?Reason::LINK_STALE:(!s.imuReady||s.imuAgeMs>180)?Reason::IMU_STALE:Reason::CONTEXT_REVOKED);update(s,now);return;}
    if(!armed_||!calibrated_||now-taskAt_>=ttl_){fail(Reason::TOTAL_BUDGET);update(s,now);return;}
    if(lastSample_!=s.imuSample){cumAngle_+=std::fabs(s.headingDeg-lastHeading_);lastHeading_=s.headingDeg;lastSample_=s.imuSample;}
    if(cumAngle_>360.f||(!align_&&std::fabs(s.headingDeg-origin_)>float(maxSteps_)*10.f+1.f)){fail(Reason::TOTAL_BUDGET);update(s,now);return;}
    if(!actionActive()){if(!rawQuiet(s))fail(Reason::CONTEXT_REVOKED);update(s,now);return;}
    if(now-actionAt_>=req_.timeoutMs){fail(Reason::ACTION_TIMEOUT);update(s,now);return;}
    const float error=float(req_.amount)-milli(s.headingDeg-start_);
    if(settling_){if(stationaryAge(now)>=300){if(early_||std::fabs(error)<=300){settling_=false;if(driveStarted_)++epoch_;fb_.status=early_?Status::STOPPED_EARLY:Status::DONE;}else if(trims_<2){++trims_;settling_=false;executing_=true;direction_=error>0?1:-1;progress_=s.headingDeg;progressAt_=now;}else fail(Reason::ACTION_LIMIT);}update(s,now);return;}
    if(std::fabs(error)<=300||(direction_>0?error<0:error>0)){settling(false);update(s,now);return;}
    if(std::fabs(s.headingDeg-progress_)>=.05f){progress_=s.headingDeg;progressAt_=now;}else if(now-progressAt_>=1000){fail(Reason::ACTION_STALLED);update(s,now);return;}
    if(std::fabs(s.headingDeg-start_)*1000>float(std::abs(req_.amount))+2000){fail(Reason::ACTION_LIMIT);update(s,now);return;}
    const float limit=req_.rate*.001f;out_.brake=false;out_.turnDegS=(error>0?1.f:-1.f)*clamp(std::fabs(error)*.003f,std::fmin(.5f,limit),limit);if(driveStarted_)fb_.status=Status::RUNNING;update(s,now);
  }
};
