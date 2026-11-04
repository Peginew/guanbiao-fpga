#ifndef S3_GOAL_DRIVE_H
#define S3_GOAL_DRIVE_H
#include <stdint.h>
#include <math.h>
#include "StraightStability.h"
namespace GoalControl {
// Driving uses a held Schmitt trigger; a single delayed/noisy sample must not
// consume a stopped alignment. Large discrepancies still brake immediately.
constexpr float ALIGN_TRIGGER_DEG=10, ALIGN_RELEASE_DEG=8, ALIGN_BRAKE_DEG=20;
constexpr float ABORT_DEG=75, TURN_TOL_DEG=3;
constexpr uint8_t MAX_RECOVERIES=3, MAX_TRIMS=2;
constexpr uint32_t ALIGN_CONFIRM_MS=200;
constexpr uint32_t SETTLE_MS=500, SETTLE_TIMEOUT_MS=3000, ALIGN_TIMEOUT_MS=20000, PROGRESS_MS=4000;
inline float clamp(float n,float a,float b){return n<a?a:n>b?b:n;}
inline float wrap(float n){while(n>180)n-=360;while(n<=-180)n+=360;return n;}
struct Guidance {float distance=0,cross=0,along=0,bearing=0;};
inline Guidance guidance(float sx,float sy,float gx,float gy,float x,float y,float speed) {
  Guidance g;const float dx=gx-sx,dy=gy-sy,length=hypotf(dx,dy);
  g.distance=hypotf(gx-x,gy-y);
  if(length<.001f){g.bearing=atan2f(gy-y,gx-x)*57.2957795f;return g;}
  const float ux=dx/length,uy=dy/length;
  g.along=(x-sx)*ux+(y-sy)*uy;g.cross=ux*(y-sy)-uy*(x-sx);
  const float lookahead=clamp(160+speed*.35f,160,300);
  const float aim=clamp(g.along+lookahead,0,length);
  const float ax=g.distance<lookahead?gx:sx+aim*ux,ay=g.distance<lookahead?gy:sy+aim*uy;
  g.bearing=atan2f(ay-y,ax-x)*57.2957795f;return g;
}
inline float brakeLead(float errorDirection,float measuredRate,float ageSeconds) {
  return clamp(fmaxf(0,errorDirection*measuredRate)*(.12f+ageSeconds),.45f,4);
}
inline void steer(float base,float error,float rate,float &left,float &right) {
  const float e=fmaxf(0,fabsf(error)-.5f)*(error<0?-1:1);
  const float damp=fabsf(rate)<.8f?0:rate;
  // Retain turning authority without driving the inner wheel below a
  // useful requested speed. Breakaway support is handled per motor.
  const float limit=fminf(60,fmaxf(0,fabsf(base)-25));
  const float delta=clamp(2.45356f*(2.2f*e-.35f*damp),-limit,limit);
  left=base-delta;right=base+delta;
  const float peak=fmaxf(fabsf(left),fabsf(right));if(peak>350){left*=350/peak;right*=350/peak;}
}
}
struct GoalDriveState {
  StraightStability::Steering steering;
  enum Phase : uint8_t { Driving, WaitAlign, Turning, SettleAlign, Finish, DistanceDriving, DistanceSettle, Done } phase=Driving;
  float sx=0,sy=0,gx=0,gy=0,length=0,tolerance=15,launchX=0,launchY=0;
  float bestDistance=0,cross=0,remaining=0,error=0,alignTarget=0,turnStart=0,progressHeading=0,previousTrimError=0;
  float finalHeading=0,distanceBudget=0,distanceStartL=0,distanceStartR=0,distanceHeading=0;
  int8_t direction=1,turnDirection=0,headingTriggerSign=0;
  uint8_t recoveries=0,trims=0;
  bool valid=false,holdFinalHeading=false,finalAlign=false,distanceOnly=false;
  bool headingPending=false,recoveryCheck=false;
  uint32_t phaseMs=0,progressMs=0,alignMs=0,headingProgressMs=0,headingTriggerMs=0;
  uint32_t startCount[4]={};
};
#endif
