#ifndef S3_R5_ROUTE_SPEED_H
#define S3_R5_ROUTE_SPEED_H
#include <math.h>

namespace RouteSpeed {
constexpr float MAX_CRUISE=300.0f, MAX_TURN=60.0f;
constexpr float BRAKE_ACCEL=200.0f, REACTION_SECONDS=0.15f;
// Solve d = v*t + v*v/(2*a). Reserve reaction distance before braking.
inline float brakingSpeed(float remaining) {
  const float at=BRAKE_ACCEL*REACTION_SECONDS;
  return sqrtf(at*at+2*BRAKE_ACCEL*fmaxf(0,remaining))-at;
}
inline float turnLimit(float requested){return fminf(requested,MAX_TURN);}
inline void straight(float requested,float error,float &left,float &right) {
  // On faster route legs, reduce cruise speed as heading error grows.
  // Leave the uploaded, proven <=120mm/s controller unchanged.
  float base=requested;
  if(fabsf(base)>120) {
    const float amount=fminf(1,fmaxf(0,(fabsf(error)-2)/6));
    base*=1-0.65f*amount;
  }
  const float magnitude=fmaxf(0,fabsf(error)-0.75f);
  const float signedError=error<0?-magnitude:magnitude;
  const float limit=fabsf(base)*0.30f;
  const float correction=fminf(limit,fmaxf(-limit,signedError*1.4f));
  left=base-correction;right=base+correction;
  // Scale both wheels together, retaining the requested curvature.
  const float peak=fmaxf(fabsf(left),fabsf(right));
  if(peak>350){left*=350/peak;right*=350/peak;}
}
}
#endif
