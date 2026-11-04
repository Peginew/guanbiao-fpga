#pragma once
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
// Only the robot loop writes/flushes this bounded queue. Serial backpressure
// must never delay IMU service or odometry snapshot publication.
class BufferedConsole {
  char data[4096]={};size_t head=0,count=0;
 public:
  uint32_t dropped=0;
  void print(const char *s){const size_t n=strlen(s);if(n>sizeof(data)-count){++dropped;return;}for(size_t i=0;i<n;i++)data[(head+count++)%sizeof(data)]=s[i];}
  void println(const char *s=""){print(s);print("\n");}
  void printf(const char *format,...){char s[640];va_list a;va_start(a,format);const int n=vsnprintf(s,sizeof(s),format,a);va_end(a);if(n<0||size_t(n)>=sizeof(s)){++dropped;return;}print(s);}
  void flush(){const int room=Serial.availableForWrite();if(room<=0||!count)return;size_t n=count;if(n>32)n=32;if(n>size_t(room))n=size_t(room);char out[33];for(size_t i=0;i<n;i++)out[i]=data[(head+i)%sizeof(data)];out[n]=0;Serial.print(out);head=(head+n)%sizeof(data);count-=n;}
};
