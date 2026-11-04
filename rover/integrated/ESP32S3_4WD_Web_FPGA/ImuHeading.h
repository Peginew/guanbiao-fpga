#pragma once
#include <stdint.h>
#include <stddef.h>
#include <math.h>
#include <string.h>

namespace ImuConfig {
// The bench-tested mounting: component face up, clockwise/right increases yaw.
constexpr int RX=2, TX=1;
constexpr float YAW_SIGN=-1.0f;
constexpr uint32_t BAUD=115200, POLL_MS=25, REQUEST_TIMEOUT_MS=120;
constexpr uint32_t FRESH_MS=180, HARD_STALE_MS=450, WARMUP_MS=1200;
constexpr uint32_t TILT_HOLD_MS=250;
constexpr float MAX_TILT_DEG=20, MAX_RELATIVE_TILT_DEG=18, EXTREME_TILT_DEG=60;
constexpr float WARMUP_SPAN_DEG=0.6f;
// Only the host legacy regression executable may disable the new behavior.
#if defined(ROBOT_HOST_LEGACY_TEST) && !defined(ARDUINO)
constexpr bool ENABLED=false;
#else
constexpr bool ENABLED=true;
#endif
}

// No Arduino dependencies; the exact same decoder is exercised by host tests.
// All outgoing packets are 0x50 reads. No register writes / zero commands.
class ImuHeading {
 public:
  uint16_t version=0;
  uint32_t frames=0,badFrames=0,timeouts=0,lastSampleMs=0,rxBytes=0,requests=0;
  uint32_t crcErrors=0,unexpectedFrames=0,lateFrames=0;
  float yaw=0,roll=0,pitch=0,rateDegS=0;
  bool compatible=false;
  static float wrap(float d) {
    while(d>180)d-=360;
    while(d<=-180)d+=360;
    return d;
  }
  static uint16_t crc(const uint8_t *p,size_t n) {
    uint16_t v=0;
    for(size_t i=0;i<n;i++) {
      v^=p[i];
      for(int b=0;b<8;b++)v=(v&1)?uint16_t((v>>1)^0x8408):uint16_t(v>>1);
    }
    return v;
  }
  bool ready(uint32_t now)const {
    return usable(now) && !tiltPending && uint32_t(now-lastSampleMs)<=ImuConfig::FRESH_MS;
  }
  // A short gap preserves the reference, but runtime must BRAKE until fresh.
  bool usable(uint32_t now)const {
    return locked && sampled && compatible && uint32_t(now-lastSampleMs)<=ImuConfig::HARD_STALE_MS;
  }
  bool available(uint32_t now)const {
    return sampled && compatible && uint32_t(now-lastSampleMs)<=ImuConfig::FRESH_MS;
  }
  float headingDeg()const {return totalDeg;}
  // Discard a stalled transport transaction and require version + stationary
  // warmup again. Preserve cumulative evidence and the last world reference.
  void restartTransport() {
    waiting=false;sentOnce=false;used=0;expectedReg=0;compatible=false;version=0;
    lose("waiting-version");
  }
  const char *reason(uint32_t now)const {
    if(ready(now))return "ready";
    if(!compatible)return version?"unsupported-version":"waiting-version";
    if(tiltPending)return "tilt-transient";
    if(usable(now))return "data-delayed";
    if(!sampled)return failure;
    if(uint32_t(now-lastSampleMs)>ImuConfig::FRESH_MS)return "no-fresh-angle";
    if(fabsf(roll)>ImuConfig::MAX_TILT_DEG||fabsf(pitch)>ImuConfig::MAX_TILT_DEG)return "mounting-tilted";
    return "keep-still";
  }
  void tick(uint32_t now,bool quiet) {
    if(tiltPending && uint32_t(now-tiltSince)>=ImuConfig::TILT_HOLD_MS)lose("mounting-tilted");
    if(sampled && uint32_t(now-lastSampleMs)>ImuConfig::HARD_STALE_MS)lose();
    if(!quiet&&!locked)warming=false;
    if(waiting && uint32_t(now-sentMs)>=ImuConfig::REQUEST_TIMEOUT_MS) {
      waiting=false;used=0;++timeouts;
    }
    if(used && uint32_t(now-lastByteMs)>=ImuConfig::REQUEST_TIMEOUT_MS)used=0;
  }
  // Caller checks UART capacity first; returned packet is always eight bytes.
  size_t request(uint32_t now,uint8_t out[8]) {
    if(waiting || (sentOnce&&uint32_t(now-sentMs)<(compatible?ImuConfig::POLL_MS:1000u)))return 0;
    expectedReg=compatible?84:80;
    const uint8_t n=compatible?6:2;
    uint8_t p[8]={0xA5,0x5A,6,0x50,expectedReg,n,0,0};
    const uint16_t c=crc(p,6);p[6]=uint8_t(c);p[7]=uint8_t(c>>8);
    memcpy(out,p,8);waiting=true;sentOnce=true;sentMs=now;used=0;++requests;return 8;
  }
  void feed(uint8_t b,uint32_t now,bool quiet,float poseDeg) {
    ++rxBytes;
    if(used && uint32_t(now-lastByteMs)>=ImuConfig::REQUEST_TIMEOUT_MS)used=0;
    lastByteMs=now;
    if(!used){if(b==0xA5)buffer[used++]=b;return;}
    if(used==1){if(b==0x5A)buffer[used++]=b;else if(b!=0xA5)used=0;return;}
    if(used==2 && (b<5 || b>sizeof(buffer)-2)){used=0;++badFrames;return;}
    buffer[used++]=b;
    if(used<3 || used<size_t(buffer[2])+2)return;
    const size_t n=used;used=0;
    if(crc(buffer,n-2)!=(uint16_t(buffer[n-2])|(uint16_t(buffer[n-1])<<8))) {++badFrames;++crcErrors;return;}
    if(!waiting || buffer[3]!=0x50 || buffer[4]!=expectedReg) {++badFrames;++unexpectedFrames;return;}
    if(uint32_t(now-sentMs)>=ImuConfig::REQUEST_TIMEOUT_MS) {++badFrames;++lateFrames;return;}
    if(expectedReg==80 && n==9) {
      waiting=false;version=uint16_t(buffer[5])|(uint16_t(buffer[6])<<8);
      // Raw 2154 plus register 84 layout was verified on this actual unit.
      // This is a compatibility profile, not identification of an unmarked PCB.
      compatible=version==2154;
      if(!compatible)lose();
      return;
    }
    if(expectedReg!=84 || n!=13 || !compatible){++badFrames;return;}
    waiting=false;
    const float a=signed16(buffer+5)*0.01f,r=signed16(buffer+7)*0.01f,p=signed16(buffer+9)*0.01f;
    if(fabsf(a)>180||fabsf(r)>180||fabsf(p)>180){++badFrames;lose("invalid-angle");return;}
    roll=r;pitch=p;
    if(fabsf(r)>ImuConfig::EXTREME_TILT_DEG||fabsf(p)>ImuConfig::EXTREME_TILT_DEG){++badFrames;lose("mounting-tilted");return;}
    const bool tilted=locked ? (fabsf(wrap(r-mountRoll))>ImuConfig::MAX_RELATIVE_TILT_DEG||fabsf(p-mountPitch)>ImuConfig::MAX_RELATIVE_TILT_DEG)
                             : (fabsf(r)>ImuConfig::MAX_TILT_DEG||fabsf(p)>ImuConfig::MAX_TILT_DEG);
    if(tilted) {
      ++badFrames;
      if(!tiltPending){tiltPending=true;tiltSince=now;}
      if(uint32_t(now-tiltSince)>=ImuConfig::TILT_HOLD_MS)lose("mounting-tilted");
      return; // Never integrate a rejected sample or refresh its data age.
    }
    tiltPending=false;
    const float delta=sampled?ImuConfig::YAW_SIGN*wrap(a-yaw):0;
    const uint32_t elapsed=uint32_t(now-lastSampleMs);
    if(sampled && fabsf(delta)>8.0f+300.0f*elapsed*0.001f){++badFrames;lose("angle-jump");return;}
    rateDegS=sampled&&elapsed?0.65f*rateDegS+0.35f*delta*1000.0f/elapsed:0;
    if(locked)totalDeg+=delta;
    yaw=a;lastSampleMs=now;sampled=true;failure="keep-still";++frames;
    if(locked)return;
    if(!quiet){warming=false;return;}
    if(!warming){warming=true;warmSince=now;warmTravel=0;}
    warmTravel+=delta;
    if(fabsf(warmTravel)>ImuConfig::WARMUP_SPAN_DEG){warming=false;return;}
    if(uint32_t(now-warmSince)>=ImuConfig::WARMUP_MS) {locked=true;totalDeg=poseDeg;mountRoll=r;mountPitch=p;warming=false;}
  }
  void anchor(float poseDeg) {if(locked)totalDeg=poseDeg;}
 private:
  bool waiting=false,sentOnce=false,sampled=false,locked=false,warming=false,tiltPending=false;
  uint8_t expectedReg=0,buffer[64]={};size_t used=0;
  uint32_t sentMs=0,lastByteMs=0,warmSince=0,tiltSince=0;
  float totalDeg=0,warmTravel=0,mountRoll=0,mountPitch=0;
  const char *failure="no-fresh-angle";
  static int16_t signed16(const uint8_t *p) {
    const uint16_t v=uint16_t(p[0])|(uint16_t(p[1])<<8);
    return v<32768?int16_t(v):int16_t(int32_t(v)-65536);
  }
  void lose(const char *why="no-fresh-angle"){locked=false;sampled=false;warming=false;tiltPending=false;rateDegS=0;failure=why;}
};
