#ifndef MROI_PLATFORM_BINDING_H
#define MROI_PLATFORM_BINDING_H
#include <stdint.h>
/* Definitions may only be emitted from the exact reviewed HPF/platform receipt.
 * Undefined externs intentionally allow object-only work without inventing BASE.
 */
extern const uint32_t mroi_physical_base;
extern const uint32_t mroi_core_clock_hz;
#define MROI_PHYSICAL_BASE mroi_physical_base
#define MROI_CORE_CLOCK_HZ mroi_core_clock_hz
#endif
