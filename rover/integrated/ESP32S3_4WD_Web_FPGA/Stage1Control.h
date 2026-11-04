#pragma once
#include <stdint.h>

// Local authorization selects the target; FPGA packets cannot widen it.
class Stage1Control {
 public:
  enum State { Monitor, Armed, Running };
  enum Trigger { M1Packet, ForwardPacket, UsbGo };
  static constexpr uint32_t kArmMs = 10000;
  static constexpr uint32_t kPulseMs = 500;
  static constexpr uint8_t kAll = 15;
  State state = Monitor;
  uint8_t armedMask = 0, activeMask = 0;
  uint32_t started = 0;
  bool estop = false;

  static constexpr bool validMask(uint8_t mask) {
    return mask == 1 || mask == 2 || mask == 4 || mask == 8 || mask == kAll;
  }
  constexpr bool arm(uint8_t mask, uint32_t now) {
    if (estop || state == Running || !validMask(mask)) return false;
    state = Armed; armedMask = mask; activeMask = 0; started = now;
    return true;
  }
  constexpr bool trigger(Trigger source, uint32_t now) {
    if (state != Armed || estop) return false;
    if (uint32_t(now - started) >= kArmMs) { stop(); return false; }
    const bool match = (source == M1Packet && armedMask == 1) ||
                       (source == ForwardPacket && armedMask == kAll) ||
                       (source == UsbGo && armedMask != kAll);
    if (!match) return false;
    activeMask = armedMask; armedMask = 0;
    state = Running; started = now;
    return true;
  }
  // Returns true only for a running pulse whose outputs must be stopped.
  constexpr bool tick(uint32_t now) {
    if (state == Running && uint32_t(now - started) >= kPulseMs) {
      stop(); return true;
    }
    if (state == Armed && uint32_t(now - started) >= kArmMs) stop();
    return false;
  }
  constexpr void stop() { state = Monitor; armedMask = 0; activeMask = 0; }
  constexpr void emergencyStop() { stop(); estop = true; }
  constexpr void clear() { stop(); estop = false; }
};
