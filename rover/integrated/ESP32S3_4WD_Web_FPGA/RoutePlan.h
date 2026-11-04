#pragma once
#include <stdint.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

namespace RouteLimits {
constexpr uint8_t MAX_STEPS=16;
constexpr unsigned MAX_TEXT=320;
constexpr float MAX_MOVE_MM=10000, MAX_TOTAL_MM=30000;
constexpr float MIN_SPEED=35, MAX_SPEED=300;
constexpr uint32_t MAX_NOMINAL_MS=1200000;
constexpr uint32_t SETTLE_MS=350, SETTLE_TIMEOUT_MS=3000, FG_TIMEOUT_MS=1500;
// Route endpoints are tighter than the legacy 2.5mm primitive tolerance.
// In particular, a 1-degree turn is only 2.45mm per side with the R1 fit.
constexpr float MOVE_TOL_MM=1.0f, TURN_TOL_MM=0.35f;
#if defined(ROBOT_HOST_LEGACY_TEST) && !defined(ARDUINO)
constexpr float HEADING_TOL_DEG=0.75f, MAX_ALIGN_DEG=15.0f;
constexpr uint8_t MAX_HEADING_CORRECTIONS=3;
#else
constexpr float HEADING_TOL_DEG=2.0f, MAX_ALIGN_DEG=75.0f;
constexpr uint8_t MAX_HEADING_CORRECTIONS=1;
#endif
}
struct RouteStep { char kind='M'; float value=0; };
struct RoutePlan {
  RouteStep steps[RouteLimits::MAX_STEPS];
  uint8_t count=0;
  float speed=40;
  uint32_t nominalMs=0;
};
// Strict, bounded wire format. Parse and validate the ENTIRE route before any
// output is enabled. Units: M=mm, T=degrees (+left), W=milliseconds.
inline bool parseRoutePlan(const char *text,float speed,float trackMm,RoutePlan &out) {
  RoutePlan plan;
  if(!text||!text[0]||strlen(text)>RouteLimits::MAX_TEXT||!isfinite(speed)||
     speed<RouteLimits::MIN_SPEED||speed>RouteLimits::MAX_SPEED||
     !isfinite(trackMm)||trackMm<=0)return false;
  plan.speed=speed;
  const char *p=text;float total=0,nominal=0;
  while(*p) {
    if(plan.count>=RouteLimits::MAX_STEPS)return false;
    const char kind=*p++;
    if((kind!='M'&&kind!='T'&&kind!='W')||*p++!=':')return false;
    // Disallow whitespace, hex floats and exponent syntax in the wire format.
    const char *start=p;unsigned digits=0,dots=0;
    if(*p=='-'||*p=='+')++p;
    while((*p>='0'&&*p<='9')||*p=='.') {
      if(*p=='.'){if(++dots>1)return false;}else ++digits;
      ++p;
    }
    if(!digits||p-start>16||(*p&&*p!=';'))return false;
    char number[18]={};memcpy(number,start,size_t(p-start));
    const float value=strtof(number,nullptr),magnitude=fabsf(value);
    if(!isfinite(value))return false;
    if(kind=='M') {
      if(magnitude<10||magnitude>RouteLimits::MAX_MOVE_MM)return false;
      total+=magnitude;nominal+=magnitude/speed*1000;
    } else if(kind=='T') {
      if(magnitude<1||magnitude>360)return false;
      nominal+=trackMm*0.5f*magnitude*0.017453292519943295f/fminf(speed,60.0f)*1000;
    } else {
      if(value<100||value>30000)return false;
      nominal+=value;
    }
    plan.steps[plan.count].kind=kind;plan.steps[plan.count++].value=value;
    if(total>RouteLimits::MAX_TOTAL_MM||nominal>RouteLimits::MAX_NOMINAL_MS)return false;
    if(*p==';'){++p;if(!*p)return false;}
  }
  plan.nominalMs=uint32_t(ceilf(nominal));out=plan;return plan.count>0;
}
enum class RouteStage : uint8_t { Idle, Running, Settling, Waiting, Completed, Cancelled, Failed };
struct RouteState {
  RoutePlan plan;
  RouteStage stage=RouteStage::Idle;
  uint8_t index=0;
  uint32_t startedMs=0,stageSinceMs=0,deadlineMs=0,poseFrame=0;
  float headingRad=0,plannedX=0,plannedY=0;
  bool aligning=false,alignmentBeforeStep=false;
  uint8_t headingCorrections=0;
  const char *reason="none";
};
