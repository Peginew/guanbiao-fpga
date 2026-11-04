#pragma once
#include <stdint.h>

namespace CarConfig {
// GPIO numbers, not header positions. Raw channel order: M1, M2, M3, M4.
// Keep raw GPIO/polarities and Stage1 ARM n + GO identifiers unchanged.
// Field feedback: forward/reverse correct but yaw inverted. Candidate mapping:
// logical left = original M2/M4; logical right = original M1/M3.
constexpr bool SWAP_CHASSIS_SIDES = true;
// R18: two driven wheels, channels M1/M2 only. View from behind toward caster.
// Preserve previous logical mapping: left=M2, right=M1. Swap these if needed.
constexpr uint8_t LEFT_MOTOR=1, RIGHT_MOTOR=0;
constexpr bool motorEnabled(uint8_t i){return i<2;}
static_assert(LEFT_MOTOR<2&&RIGHT_MOTOR<2&&LEFT_MOTOR!=RIGHT_MOTOR,"M1/M2 side mapping invalid");
constexpr uint8_t PWM[4] = {4, 5, 6, 7};
constexpr uint8_t DIR[4] = {8, 9, 10, 11};
constexpr uint8_t BRK[4] = {12, 13, 14, 15};
constexpr uint8_t FG[4] = {16, 17, 18, 21};
// Inherited assumptions: verify each wheel with ARM n + GO, wheels lifted.
// If a wheel drives backwards, stop/power down and change its bool only.
constexpr bool FORWARD_HIGH[4] = {true, false, true, false};
// Legacy UART constants only. R18 does not initialize UART1 or UART2.
constexpr uint8_t FPGA_RX = 40, RESERVED_TX = 39;
constexpr bool serialPinsFree() {
  const uint8_t serialPins[4]={1,2,RESERVED_TX,FPGA_RX};
  for(unsigned j=0;j<4;j++)for(unsigned i=0;i<4;i++)
    if(serialPins[j]==PWM[i]||serialPins[j]==DIR[i]||serialPins[j]==BRK[i]||serialPins[j]==FG[i])return false;
  return true;
}
static_assert(serialPinsFree(),"UART pins overlap a motor pin");
static_assert(FPGA_RX!=1&&FPGA_RX!=2&&RESERVED_TX!=1&&RESERVED_TX!=2,"FPGA and IMU UART pins overlap");
constexpr uint32_t PWM_HZ = 25000;
constexpr uint8_t PWM_BITS = 10;
constexpr uint16_t PWM_MAX = (1u << PWM_BITS) - 1u;
constexpr uint8_t TEST_DUTY_PERCENT = 20;
static_assert(TEST_DUTY_PERCENT > 0 && TEST_DUTY_PERCENT <= 20,
              "Stage 1 test duty must be in 1..20 percent");
}
