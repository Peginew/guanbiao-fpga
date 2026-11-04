#pragma once
#include <stdint.h>
namespace MotorStartAssist {
// Provisional M4-only startup support, not a measured static-friction fit.
constexpr uint8_t MOTOR_INDEX=3;
constexpr uint32_t WINDOW_MS=400;
constexpr float FLOOR_DUTY=28.0f,MAX_FLOOR_DUTY=34.0f;
constexpr float FLOOR_RISE_PER_MS=.02f,DUTY_RISE_PER_SECOND=140.0f;
inline bool eligible(uint8_t i,bool firstPulse,uint32_t elapsed){
  return i==MOTOR_INDEX&&!firstPulse&&elapsed<WINDOW_MS;
}
inline float floor(uint32_t elapsed){
  const float value=FLOOR_DUTY+elapsed*FLOOR_RISE_PER_MS;
  return value<MAX_FLOOR_DUTY?value:MAX_FLOOR_DUTY;
}
}
