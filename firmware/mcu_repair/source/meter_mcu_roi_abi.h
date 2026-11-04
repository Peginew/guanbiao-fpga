#ifndef METER_MCU_ROI_ABI_H
#define METER_MCU_ROI_ABI_H
/* Register OFFSETS only. CPU physical base must come from the exact HPF/BSP.
 * Volatile MMIO and platform cache/barrier/quiescence semantics are required.
 * This header neither enables an MCU clock nor supplies a memory/CDC bridge.
 */
#define MROI_ID             0x000u
#define MROI_ABI            0x004u
#define MROI_STATUS         0x008u
#define MROI_ERROR          0x00cu
#define MROI_SEQUENCE       0x010u
#define MROI_EPOCH          0x014u
#define MROI_SOURCE         0x018u
#define MROI_JOB            0x01cu
#define MROI_TARGET         0x020u
#define MROI_CONFIG         0x024u
#define MROI_X0             0x028u
#define MROI_Y0             0x02cu
#define MROI_SHAPE          0x030u
#define MROI_STRIDE         0x034u
#define MROI_RADIUS         0x038u
#define MROI_FORMAT         0x03cu
#define MROI_BYTES          0x040u
#define MROI_STATUS_VISIBLE (1u << 1)
#define MROI_STATUS_PRESENT (1u << 2)
#define MROI_STATUS_REVOKED (1u << 3)
#define MROI_STATUS_CLAIMED (1u << 4)
#define MROI_STATUS_RESULT  (1u << 5)
#define MROI_STATUS_RAMWAIT (1u << 6)
#define MROI_CLAIM_EPOCH    0x080u
#define MROI_CLAIM_SOURCE   0x084u
#define MROI_CLAIM_JOB      0x088u
#define MROI_CLAIM_COMMIT   0x08cu
#define MROI_CLAIM_MAGIC    0x434c4149u
#define MROI_RETURN_EPOCH   0x100u
#define MROI_RETURN_SOURCE  0x104u
#define MROI_RETURN_JOB     0x108u
#define MROI_RETURN_TARGET  0x10cu
#define MROI_RETURN_CONFIG  0x110u
#define MROI_RETURN_CRC32   0x114u
#define MROI_RETURN_BYTES   0x118u
#define MROI_RETURN_CODE    0x11cu
#define MROI_RETURN_COMMIT  0x120u
#define MROI_RETURN_MAGIC   0x52455331u
#define MROI_QUIET_EPOCH    0x180u
#define MROI_QUIET_SOURCE   0x184u
#define MROI_QUIET_JOB      0x188u
#define MROI_QUIET_COMMIT   0x18cu
#define MROI_QUIET_MAGIC    0x51554945u
#define MROI_DATA           0x1000u
#define MROI_DATA_LAST_WORD 0x4ffcu
#define MROI_CANONICAL_BYTES 16384u
#define MROI_ID_VALUE       0x524f4931u
#define MROI_ABI_VALUE      0x00010000u
/* CRC32 is reflected polynomial edb88320, initial ffffffff, final xor ffffffff.
 * Four bytes in an MMIO word are consumed LSB first. RES1 commits only a
 * transport/checksum result and promises the CPU has quiesced that ROI; the
 * bridge does not independently prove the reported CRC or pressure accuracy.
 */
#endif
