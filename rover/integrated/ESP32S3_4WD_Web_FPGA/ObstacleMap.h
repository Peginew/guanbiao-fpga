#pragma once
#include <stdint.h>

#include <math.h>
#include <string.h>
#include <stdlib.h>

// A manual map in the pose frame. Rectangles use conservative AABB
// inflation; walls are finite capsules (segment + half thickness + clearance).
struct MapObstacle { char kind='R';float x1=0,y1=0,x2=0,y2=0,width=0; };
struct ObstacleMap {
  static constexpr uint8_t MAX_COUNT=12;
  static constexpr unsigned MAX_TEXT=704;
  MapObstacle items[MAX_COUNT];uint8_t count=0;
  float radius=150,margin=150;
};
namespace ObstacleGeometry {
constexpr float MAP_EPS_MM=1.0f,COORD=10000;
inline float squareValue(float x){return x*x;}
inline bool number(float x){return isfinite(x);}
inline bool valid(const ObstacleMap &m) {
  if(!m.count||m.count>ObstacleMap::MAX_COUNT||!number(m.radius)||!number(m.margin)||m.radius<80||m.radius>1000||m.margin<50||m.margin>1000)return false;
  for(uint8_t i=0;i<m.count;i++){
    const auto &o=m.items[i];
    if(!number(o.x1)||!number(o.y1)||!number(o.x2)||!number(o.y2)||!number(o.width)||fabsf(o.x1)>COORD||fabsf(o.y1)>COORD||fabsf(o.x2)>COORD||fabsf(o.y2)>COORD)return false;
    if(o.kind=='R'){if(o.x2-o.x1<50||o.y2-o.y1<50||o.width!=0)return false;}
    else if(o.kind=='W'){if(hypotf(o.x2-o.x1,o.y2-o.y1)<50||o.width<20||o.width>2000)return false;}
    else return false;
  }
  return true;
}
inline float pointSegment2(float px,float py,float ax,float ay,float bx,float by) {
  const float dx=bx-ax,dy=by-ay,n=dx*dx+dy*dy;
  const float t=n>0?fminf(1,fmaxf(0,((px-ax)*dx+(py-ay)*dy)/n)):0;
  return squareValue(px-ax-t*dx)+squareValue(py-ay-t*dy);
}
inline bool slab(float a,float d,float low,float high,float &lo,float &hi) {
  if(fabsf(d)<.00001f)return a>=low&&a<=high;
  float x=(low-a)/d,y=(high-a)/d;if(x>y){float z=x;x=y;y=z;}
  lo=fmaxf(lo,x);hi=fminf(hi,y);return lo<=hi;
}
inline bool rectHit(float ax,float ay,float bx,float by,float x1,float y1,float x2,float y2) {
  float lo=0,hi=1;
  return slab(ax,bx-ax,x1,x2,lo,hi)&&slab(ay,by-ay,y1,y2,lo,hi);
}
inline float cross(float ax,float ay,float bx,float by){return ax*by-ay*bx;}
inline bool segmentsCross(float ax,float ay,float bx,float by,float cx,float cy,float dx,float dy) {
  const float rx=bx-ax,ry=by-ay,sx=dx-cx,sy=dy-cy,den=cross(rx,ry,sx,sy);
  if(fabsf(den)<.00001f)return false; // parallel/collinear handled by endpoint distances
  const float t=cross(cx-ax,cy-ay,sx,sy)/den,u=cross(cx-ax,cy-ay,rx,ry)/den;
  return t>=0&&t<=1&&u>=0&&u<=1;
}
inline float segmentDistance2(float ax,float ay,float bx,float by,float cx,float cy,float dx,float dy) {
  if(segmentsCross(ax,ay,bx,by,cx,cy,dx,dy))return 0;
  return fminf(fminf(pointSegment2(ax,ay,cx,cy,dx,dy),pointSegment2(bx,by,cx,cy,dx,dy)),
               fminf(pointSegment2(cx,cy,ax,ay,bx,by),pointSegment2(dx,dy,ax,ay,bx,by)));
}
inline bool segmentBlocked(const ObstacleMap &m,float ax,float ay,float bx,float by) {
  if(!number(ax)||!number(ay)||!number(bx)||!number(by))return true;
  const float pad=m.radius+m.margin+MAP_EPS_MM;
  for(uint8_t i=0;i<m.count;i++){
    const auto &o=m.items[i];
    if(o.kind=='R'){
      if(rectHit(ax,ay,bx,by,o.x1-pad,o.y1-pad,o.x2+pad,o.y2+pad))return true;
    } else if(segmentDistance2(ax,ay,bx,by,o.x1,o.y1,o.x2,o.y2)<=squareValue(pad+o.width*.5f))return true;
  }
  return false;
}
inline bool pointBlocked(const ObstacleMap &m,float x,float y){return segmentBlocked(m,x,y,x,y);}
inline bool token(const char *&p,float &out) {
  const char *start=p;unsigned digits=0,dots=0;
  if(*p=='+'||*p=='-')++p;
  while((*p>='0'&&*p<='9')||*p=='.'){if(*p=='.'){if(++dots>1)return false;}else ++digits;++p;}
  if(!digits||p-start>16)return false;
  char s[18]={};memcpy(s,start,size_t(p-start));out=strtof(s,nullptr);
  return isfinite(out)&&fabsf(out)<=COORD;
}
// radius,margin|R,x1,y1,x2,y2;W,x1,y1,x2,y2,width
inline bool parse(const char *text,ObstacleMap &out) {
  if(!text||!text[0]||strlen(text)>ObstacleMap::MAX_TEXT)return false;
  ObstacleMap m;const char *p=text;
  if(!token(p,m.radius)||*p++!=','||!token(p,m.margin)||*p++!='|')return false;
  while(*p){
    if(m.count>=ObstacleMap::MAX_COUNT)return false;
    auto &o=m.items[m.count];o.kind=*p++;
    if((o.kind!='R'&&o.kind!='W')||*p++!=',')return false;
    if(!token(p,o.x1)||*p++!=','||!token(p,o.y1)||*p++!=','||!token(p,o.x2)||*p++!=','||!token(p,o.y2))return false;
    if(o.kind=='W'&&(*p++!=','||!token(p,o.width)))return false;
    ++m.count;if(!*p)break;if(*p++!=';'||!*p)return false;
  }
  if(!valid(m))return false;out=m;return true;
}
}
