#ifndef MROI_COLD_START_H
#define MROI_COLD_START_H
#include "mroi_client.h"
/* Explicit live ABI extension: same address/magic as signed host startup. */
#define MROI_COLD_ARM_OFFSET 0x060u
#define MROI_COLD_ARM_MAGIC 0x41524d31u
#define MROI_COLD_WARMUP_CYCLES 5000000u /* exact50MHz core:100ms */
enum {MROI_BOOT_OK=1,MROI_BOOT_IO_ERROR=2,MROI_BOOT_BAD_ID=3,
      MROI_BOOT_BAD_ABI=4,MROI_BOOT_BAD_LIVE_ID=5,
      MROI_BOOT_ALREADY_ARMED=6,MROI_BOOT_ARM_VERIFY=7,MROI_BOOT_MISSING_PSI_FEATURE=8};
int mroi_cold_start(const mroi_io *io,volatile uint32_t diag[4]);
#endif
