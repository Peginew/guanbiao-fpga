#pragma once
#include <stdint.h>
// Defined in a header so Arduino's generated function declarations see the type.
struct LineBuffer {
  char data[32] = {};
  uint8_t length = 0;
  bool discard = false;
  uint32_t lastByteMs = 0;
  void clear() { length = 0; discard = false; }
};
