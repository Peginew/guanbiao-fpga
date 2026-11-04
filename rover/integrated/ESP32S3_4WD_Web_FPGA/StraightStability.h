#pragma once
#include <math.h>
#include <stdint.h>
namespace StraightStability {
constexpr float ACCEL_MM_S2=220.0f;
constexpr float STEER_SLEW_MM_S2=60.0f;
constexpr float RATE_FILTER_SECONDS=.18f;
constexpr float DUTY_RISE_PER_SECOND=80.0f,DUTY_FALL_PER_SECOND=120.0f;
inline float bound(float x,float lo,float hi){return x<lo?lo:x>hi?hi:x;}
struct Steering {bool active=false;uint32_t lastMs=0;float rate=0,delta=0;};
inline float smooth(Steering &s,float desired,float rate,uint32_t now,float limit){
  const uint32_t elapsed=now-s.lastMs;
  if(!s.active||elapsed>200){s=Steering{};s.active=true;s.lastMs=now;return 0;}
  const float dt=float(elapsed)*.001f;s.lastMs=now;
  s.rate+=dt/(RATE_FILTER_SECONDS+dt)*(rate-s.rate);
  s.delta=bound(desired,s.delta-STEER_SLEW_MM_S2*dt,s.delta+STEER_SLEW_MM_S2*dt);
  s.delta=bound(s.delta,-limit,limit);return s.delta;
}
inline float duty(float previous,float desired,float dt){
  return bound(desired,fmaxf(0,previous-DUTY_FALL_PER_SECOND*dt),fminf(100,previous+DUTY_RISE_PER_SECOND*dt));
}
inline bool acceptIntegral(float error,float demanded,float applied){
  return !((error>0&&applied<demanded-.01f)||(error<0&&applied>demanded+.01f));
}
}
