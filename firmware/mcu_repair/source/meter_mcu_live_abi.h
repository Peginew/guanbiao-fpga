#ifndef METER_MCU_LIVE_ABI_H
#define METER_MCU_LIVE_ABI_H
/* ABI1 extension specific to the live parent. Generic ABI1 itself is unchanged. */
#define MROI_LIVE_HWCRC 0x048u
#define MROI_LIVE_QUALITY 0x04cu
#define MROI_LIVE_MEAN 0x050u
#define MROI_LIVE_GRADIENT 0x054u
#define MROI_LIVE_HISTOGRAM 0x058u
#define MROI_LIVE_MAGIC 0x05cu
#define MROI_LIVE_MAGIC_VALUE 0x4c565231u
#define MROI_LIVE_SCAN_COMPLETE 1u
#define MROI_LIVE_QUALITY_GOOD 2u
#endif
