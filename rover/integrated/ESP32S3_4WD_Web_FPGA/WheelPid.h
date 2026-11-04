#pragma once
#include <stdint.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>
#ifdef ARDUINO
#include <Preferences.h>
#endif

// Raw channel order M1..M4, not a guessed physical front/rear ordering.
struct WheelPiGain {float kp=.12f,ki=.25f,kd=0;};
constexpr float WHEEL_PID_D_TAU_S=.15f,WHEEL_PID_D_LIMIT_PCT=15.0f;
inline bool validWheelPi(const WheelPiGain (&g)[4]) {
  for(const auto &v:g)if(!isfinite(v.kp)||!isfinite(v.ki)||!isfinite(v.kd)||v.kp<0||v.kp>2||v.ki<0||v.ki>2||v.kd<0||v.kd>.2f)return false;
  return true;
}
inline bool parseWheelPi(const char *text,WheelPiGain (&out)[4]) {
  if(!text||!text[0]||strlen(text)>256)return false;
  WheelPiGain values[4];const char *p=text;
  for(unsigned i=0;i<4;i++) {
    char *end=nullptr;values[i].kp=strtof(p,&end);if(end==p||*end!=',')return false;p=end+1;
    values[i].ki=strtof(p,&end);if(end==p||*end!=',')return false;p=end+1;
    values[i].kd=strtof(p,&end);if(end==p||*end!=(i==3?'\0':';'))return false;p=i==3?end:end+1;
  }
  if(!validWheelPi(values))return false;
  memcpy(out,values,sizeof(values));return true;
}
namespace WheelPiStorage {
struct Blob {uint32_t magic=0x31504957,version=2;WheelPiGain gains[4];uint32_t checksum=0;};
struct LegacyGain {float kp=.12f,ki=.25f;};
struct LegacyBlob {uint32_t magic=0x31504957,version=1;LegacyGain gains[4];uint32_t checksum=0;};
template<class T>inline uint32_t checksum(const T &b) {
  const auto *p=reinterpret_cast<const uint8_t*>(&b);uint32_t n=2166136261u;
  for(unsigned i=0;i<sizeof(b)-sizeof(b.checksum);i++)n=(n^p[i])*16777619u;
  return n;
}
static_assert(sizeof(Blob)==60&&sizeof(LegacyBlob)==44,"Unexpected PID storage layout");
#ifndef ARDUINO
static Blob mockBlob;static bool mockPresent=false,mockWriteFail=false;
static LegacyBlob mockLegacyBlob;static bool mockLegacyPresent=false;
#endif
inline bool read(WheelPiGain (&g)[4]) {
  Blob b;LegacyBlob legacy;bool old=false;
#ifdef ARDUINO
  Preferences p;if(!p.begin("wheel-pi",true))return false;
  const size_t length=p.getBytesLength("profile");old=length==sizeof(legacy);
  const bool ok=old?p.getBytes("profile",&legacy,sizeof(legacy))==sizeof(legacy):length==sizeof(b)&&p.getBytes("profile",&b,sizeof(b))==sizeof(b);p.end();
  if(!ok)return false;
#else
  if(mockLegacyPresent){old=true;legacy=mockLegacyBlob;}else{if(!mockPresent)return false;b=mockBlob;}
#endif
  if(old){
    if(legacy.magic!=0x31504957||legacy.version!=1||legacy.checksum!=checksum(legacy))return false;
    WheelPiGain migrated[4];for(unsigned i=0;i<4;i++){migrated[i].kp=legacy.gains[i].kp;migrated[i].ki=legacy.gains[i].ki;migrated[i].kd=0;}
    if(!validWheelPi(migrated))return false;memcpy(g,migrated,sizeof(g));return true;
  }
  if(b.magic!=0x31504957||b.version!=2||b.checksum!=checksum(b)||!validWheelPi(b.gains))return false;
  memcpy(g,b.gains,sizeof(g));return true;
}
inline bool write(const WheelPiGain (&g)[4]) {
  if(!validWheelPi(g))return false;
  Blob b;memcpy(b.gains,g,sizeof(g));b.checksum=checksum(b);
#ifdef ARDUINO
  Preferences p;if(!p.begin("wheel-pi",false))return false;
  const bool ok=p.putBytes("profile",&b,sizeof(b))==sizeof(b);p.end();return ok;
#else
  if(mockWriteFail)return false;mockBlob=b;mockPresent=true;mockLegacyPresent=false;return true;
#endif
}
}
struct WheelPiProfile {
  WheelPiGain gains[4];uint32_t revision=1,persistMs=0;
  bool pending=false,saved=false,saveError=false;
};
struct WheelPiSample {uint32_t ms=0;float target=0,actual=0,duty=0;};
struct WheelPiTest {
  static constexpr uint8_t CAPACITY=32;
  uint8_t motor=0,used=0,next=0;uint32_t id=0,startedMs=0,durationMs=0;
  float speed=0;bool active=false,isolatePose=false;const char *reason="none";
  WheelPiSample samples[CAPACITY];
};
