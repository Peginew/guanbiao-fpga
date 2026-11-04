#pragma once
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include "GuanbiaoProtocolV4.h"

// ESP owns the map and sweep. No FPGA frame can add a point or enlarge it.
class ScanPlan {
 public:
  static constexpr unsigned MAX_POINTS=gb4::cfg::MAX_MONITOR_POINTS;
  enum Mode:std::uint8_t { Formal=0, DiagnosticCandidates=1 };
  enum Stage:std::uint8_t { Empty,Ready,Approach,Align,Inspect,Result,Failed,Done,Stopped };
  struct Point {std::uint16_t id=0;float x=0,y=0,bearing=0,halfAngle=20;};
  struct Reading {bool candidate=false,formal=false;std::uint16_t rawQ16=0;std::uint32_t source=0,session=0,nonce=0,pose=0,epoch=0;};
 private:
  Point points_[MAX_POINTS];Reading readings_[MAX_POINTS];unsigned count_=0,index_=0;
  Stage stage_=Empty;Mode mode_=Formal;std::uint32_t planId_=0;bool continuous_=false;
 public:
  static float wrap(float a){while(a>180)a-=360;while(a<=-180)a+=360;return a;}
  static bool valid(const Point&p){return p.id&&std::isfinite(p.x)&&std::isfinite(p.y)&&std::fabs(p.x)<=10000&&std::fabs(p.y)<=10000&&std::isfinite(p.bearing)&&p.bearing>=-180&&p.bearing<=180&&std::isfinite(p.halfAngle)&&p.halfAngle>=5&&p.halfAngle<=45;}
  bool running()const{return stage_==Approach||stage_==Align||stage_==Inspect;}
  unsigned count()const{return count_;} unsigned index()const{return index_;}
  Stage stage()const{return stage_;}Mode mode()const{return mode_;}
  std::uint32_t id()const{return planId_;}bool continuous()const{return continuous_;}
  const Point&point(unsigned i)const{return points_[i<MAX_POINTS?i:0];}
  const Point&current()const{return point(index_);}
  const Reading&reading(unsigned i)const{return readings_[i<MAX_POINTS?i:0];}
  // A sector is quantized inward to 10-degree steps; it never exceeds its map boundary.
  unsigned maxSteps()const{return unsigned(std::floor(2.f*current().halfAngle/10.f));}
  float firstBearing()const{return wrap(current().bearing-current().halfAngle);}
  bool set(const Point*p,unsigned n){if(running()||!n||n>MAX_POINTS)return false;for(unsigned i=0;i<n;i++){if(!valid(p[i]))return false;for(unsigned j=0;j<i;j++)if(p[i].id==p[j].id)return false;}for(unsigned i=0;i<n;i++){points_[i]=p[i];readings_[i]=Reading{};}count_=n;index_=0;stage_=Ready;if(!++planId_)++planId_;return true;}
  // id,x,y,world-bearing-deg,half-angle-deg;...  No JSON heap/parser in robotLoop.
  bool parse(const char*text){if(!text||std::strlen(text)>1800)return false;Point p[MAX_POINTS];unsigned n=0;const char*s=text;while(*s){if(n==MAX_POINTS)return false;float v[5];for(unsigned j=0;j<5;j++){char*e=nullptr;v[j]=std::strtof(s,&e);if(e==s||!std::isfinite(v[j]))return false;s=e;if(j<4){if(*s++!=',')return false;}}if(v[0]<1||v[0]>65535||v[0]!=std::floor(v[0]))return false;p[n++]={std::uint16_t(v[0]),v[1],v[2],v[3],v[4]};if(*s){if(*s++!=';'||!*s)return false;}}return set(p,n);}
  bool begin(Mode m,bool continuous){if(running()||!count_||(m!=Formal&&m!=DiagnosticCandidates))return false;mode_=m;continuous_=continuous;index_=0;for(auto&r:readings_)r=Reading{};stage_=Approach;return true;}
  void aligned(){if(stage_==Approach||stage_==Align)stage_=Inspect;}
  void aligning(){if(stage_==Approach)stage_=Align;}
  void stop(){stage_=Stopped;continuous_=false;}
  void fail(){stage_=Failed;continuous_=false;}
  // Caller must prove actual READ, new source, parked and full session/task context.
  // REF/LAST do not have an API here. Candidate mode is an explicit local opt-in.
  bool record(const Reading&r){if(stage_!=Inspect||!r.candidate||!r.session||!r.nonce||!r.pose)return false;readings_[index_]=r;stage_=Result;return true;}
  bool mayAdvance()const{return stage_==Result&&continuous_&&(readings_[index_].formal||(mode_==DiagnosticCandidates&&readings_[index_].candidate));}
  bool advance(){if(!mayAdvance())return false;if(index_+1>=count_){stage_=Done;return true;}++index_;stage_=Approach;return true;}
  bool manualContinue(){if((stage_!=Failed&&stage_!=Result&&stage_!=Stopped)||index_+1>=count_)return false;++index_;continuous_=false;stage_=Approach;return true;}
};
