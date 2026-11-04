#ifndef S3_R5_PATH_PLAN_H
#define S3_R5_PATH_PLAN_H
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "ObstacleMap.h"

namespace PathLimits {
constexpr uint8_t MAX_POINTS=12;
constexpr unsigned MAX_TEXT=384;
constexpr float COORD_MM=10000, LEG_MM=5000, TOTAL_MM=30000;
constexpr float MIN_SPEED=35, MAX_SPEED=300, TURN_SPEED=60;
}
struct PathPoint { float x=0,y=0; };
struct PathPlan {
  PathPoint points[PathLimits::MAX_POINTS];
  uint8_t count=0;
  float speed=40;
  bool guarded=false;
  uint32_t poseFrame=0;
  ObstacleMap obstacles;
};
inline bool pathNumber(const char *&p,float &value) {
  const char *start=p;unsigned digits=0,dots=0;
  if(*p=='+'||*p=='-')++p;
  while((*p>='0'&&*p<='9')||*p=='.') {
    if(*p=='.'){if(++dots>1)return false;}else ++digits;
    ++p;
  }
  if(!digits||p-start>16)return false;
  char text[18]={};memcpy(text,start,size_t(p-start));value=strtof(text,nullptr);
  return isfinite(value)&&fabsf(value)<=PathLimits::COORD_MM;
}
// Atomic parse: an invalid later waypoint never leaves a partial runnable plan.
inline bool parsePathPlan(const char *text,float speed,PathPlan &out) {
  if(!text||!text[0]||strlen(text)>PathLimits::MAX_TEXT||!isfinite(speed)||speed<PathLimits::MIN_SPEED||speed>PathLimits::MAX_SPEED)return false;
  PathPlan plan;plan.speed=speed;const char *p=text;float total=0;
  while(*p) {
    if(plan.count>=PathLimits::MAX_POINTS)return false;
    PathPoint point;
    if(!pathNumber(p,point.x)||*p!=',')return false;
    ++p;if(!pathNumber(p,point.y)||(*p&&*p!=';'))return false;
    if(plan.count) {
      const PathPoint &previous=plan.points[plan.count-1];
      const float distance=hypotf(point.x-previous.x,point.y-previous.y);
      if(distance>PathLimits::LEG_MM)return false;
      total+=distance;if(total>PathLimits::TOTAL_MM)return false;
    }
    plan.points[plan.count++]=point;
    if(*p==';'){++p;if(!*p)return false;}
  }
  out=plan;return true;
}
#endif
