#pragma once
#include <stdint.h>

// Same LF-delimited protocol as the original sketch, with explicit diagnostics.
// No allocation, serial writes, GPIO operations or motor action in this class.
class RxProbe {
 public:
  char data[32] = {};
  uint8_t length=0;
  bool discard=false;
  uint32_t lastByteMs=0, bytes=0, lines=0, bad=0, timeouts=0;
  uint8_t recent[16]={}, recentHead=0, recentCount=0;
  constexpr void clearLine() { length=0;discard=false; }
  constexpr void expire(uint32_t now) {
    if (length && uint32_t(now-lastByteMs)>=250) {
      length=0;discard=true;++timeouts;
    }
  }
  constexpr bool feed(uint8_t c,uint32_t now) {
    expire(now);
    ++bytes;
    recent[recentHead]=c;
    recentHead=(recentHead+1)%16;
    if (recentCount<16) ++recentCount;
    lastByteMs=now;
    if (c=='\r') return false;
    if (c=='\n') {
      if (!discard && length) {
        data[length]=0;length=0;++lines;return true;
      }
      clearLine();return false;
    }
    if (c<32 || c>126 || length>=sizeof(data)-1) {
      if (!discard) ++bad;
      length=0;discard=true;
    } else if (!discard) data[length++]=char(c);
    return false;
  }
};
