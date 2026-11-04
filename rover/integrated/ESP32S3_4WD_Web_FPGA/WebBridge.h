#pragma once
#include "RoutePlan.h"
#include "PathPlan.h"
#include "FpgaUartLink.h"
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>

// Only robotLoop owns motors, Stage1 state and odometry. HTTP runs separately
// on core 0 and communicates through bounded queues and a copied snapshot.
enum class WebOp : uint8_t { Drive, Move, Turn, Arc, Clear, Zero, Arm, Go, Goto, Route, Path, AvoidPath, ImuReconnect, FpgaStart, FpgaCancel, InspectionArm, InspectionCalibration, ScanConfigure, ScanStart, ScanContinue };
struct WebCommand {
  uint32_t id=0, epoch=0, receivedMs=0, coordinateFrame=0;
  WebOp operation=WebOp::Drive;
  float a=0,b=0,c=0;
  uint16_t linkTask=0,linkPoint=0,linkConfig=4;
  uint32_t linkEpoch=0;
  char leaseToken[17]={};
  char scanText[1801]={};
  RoutePlan routePlan;
  PathPlan pathPlan;
};
struct WebResult { uint32_t id=0,epoch=0; bool ok=false; char leaseToken[17]={}; };
struct WebSnapshot {
  FpgaLinkSnapshot fpga;
  ScanPlan scan;float inspectionArrivalHeading=0;
  bool inspectionNavigation=false,inspectionArrivalPending=false,consoleMode=false;
  uint32_t startDelayMs[4]={0xffffffffu,0xffffffffu,0xffffffffu,0xffffffffu};
  bool m4StartAssist=false;
  uint32_t loopMaxGapMs=0,bootResetReason=0,consoleDropped=0,imuCrc=0,imuUnexpected=0,imuLate=0;
  bool apStarted=false;float responseTravelL=0,responseTravelR=0,responseCommand=0,responseDuty=0;
  bool headingValid=false,headingLimited=false;
  float headingTarget=0,headingActual=0,headingError=0,headingResidual=0;
  uint8_t headingCorrections=0;
  char headingPhase[24]={},headingNote[32]={};
  bool goalTracked=false,pathDistanceOnly=false;
  float pathRemaining=0,pathCross=0;
  uint8_t pathRecoveries=0,pathTrims=0;
  bool imuReady=false,imuAvailable=false,imuUsable=false,imuFaultValid=false;
  uint32_t imuRx=0,imuRequests=0,imuFaultAge=0;float imuRate=0,imuFaultRoll=0,imuFaultPitch=0;uint16_t imuVersion=0;
  uint32_t imuAge=0xffffffffu,imuFrames=0,imuBad=0,imuTimeouts=0;
  uint32_t imuLinkRestarts=0;uint8_t imuAutoRestarts=0;bool imuCanReconnect=false;
  float imuYaw=0,imuRoll=0,imuPitch=0;char imuReason[32]={};
  char mode[24]={},fault[24]={};
  char stopSource[24]={},faultSource[24]={};
  float x=0,y=0,yaw=0,left=0,right=0,speed[4]={},duty[4]={};
  uint32_t count[4]={},epoch=1,rxForward=0,rxM1=0,bytes=0,bad=0,ageMs=0;
  uint8_t stage=0,armed=0,active=0;
  bool ready=false,uart=false,ioFault=false,estop=false;
  char navStage[24]={},navReason[32]={};
  bool navActive=false,navGuarded=false;
  uint32_t poseFrame=1;bool poseZeroed=false;
  ObstacleMap obstacleMap;
  PathPoint navPoints[PathLimits::MAX_POINTS];
  uint8_t feedbackMotor=0;
  float feedbackTarget=0,feedbackDuty=0;
  uint32_t feedbackSilenceMs=0,feedbackCount=0;
  float goalX=0,goalY=0,goalError=0;
  uint8_t navPoint=0,navCount=0;
  float finalX=0,finalY=0;
  char routeStage[24]={},routeReason[32]={},routeKind=0;
  bool routeActive=false;
  uint8_t routeStep=0,routeCount=0;
  float routeRemaining=0;
};
