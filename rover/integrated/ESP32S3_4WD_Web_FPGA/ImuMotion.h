#pragma once
#include <stdint.h>
#include <math.h>

struct ImuMotionState {
  enum Kind : uint8_t { WheelArc, Straight, Turn } kind=WheelArc;
  bool settling=false,headingOnly=false;
  float targetDeg=0,startDeg=0,progressHeading=0;
  uint32_t settleMs=0,progressMs=0;
  uint8_t corrections=0;
  float previousTrimError=0;
  int8_t turnDirection=0; // fixed for the entire requested turn, including trim
};
struct HeadingFeedback {
  bool valid=false,limited=false;
  float target=0,actual=0,error=0,residual=0;
  uint8_t corrections=0;
  const char *phase="idle",*note="none";
};
namespace ImuMotion {
// Settle hysteresis avoids chasing tiny errors with repeated reversals.
constexpr float TURN_TOL_DEG=3.0f, BRAKE_ENTRY_DEG=0.45f;
constexpr float STRAIGHT_DEADBAND_DEG=0.75f, HEADING_STOP_DEG=30.0f;
constexpr float CORRECTION_MAX_SPEED=30.0f;
constexpr uint8_t MAX_CORRECTIONS=2;
constexpr uint32_t SETTLE_MS=500, SETTLE_TIMEOUT_MS=2500, NO_YAW_PROGRESS_MS=2500;
inline float clamp(float v,float lo,float hi){return v<lo?lo:v>hi?hi:v;}
inline void straight(float base,float errorDeg,float &l,float &r) {
  // Correction sign is independent of forward/reverse travel. Never reverse
  // a wheel just to hold heading during a straight leg.
  const float limit=fabsf(base)*0.30f;
  const float magnitude=fmaxf(0,fabsf(errorDeg)-STRAIGHT_DEADBAND_DEG);
  const float filteredError=errorDeg<0?-magnitude:magnitude;
  const float correction=clamp(filteredError*1.4f,-limit,limit);
  l=base-correction;r=base+correction;
}
inline void turn(float errorDeg,float speed,float &l,float &r) {
  // Lower the requested near-end speed; actual minimum stable gearbox speed
  // still needs field measurement. No pulse-drive or repeated on/off dithering.
  const float v=clamp(fabsf(errorDeg)*3.0f,fminf(speed,30.0f),speed);
  l=errorDeg>0?-v:v;r=-l;
}
}
