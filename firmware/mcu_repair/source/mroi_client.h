#ifndef MROI_CLIENT_H
#define MROI_CLIENT_H
#include <stdint.h>
#include <stddef.h>

typedef struct {
    void *context;
    int (*read32)(void *, uint32_t, uint32_t *);
    int (*write32)(void *, uint32_t, uint32_t);
    void (*fence)(void *);
    uint32_t (*cycles)(void *);
    uint32_t cycle_budget;
} mroi_io;

typedef struct {
    uint32_t sequence, epoch, source, job, target, config;
    uint32_t x0, y0, shape, stride, radius, format, bytes;
    uint32_t hw_crc32,quality_flags,mean,gradient,histogram;
} mroi_descriptor;

typedef struct {
    uint32_t heartbeat, completed, aborted, no_offer, pending;
    uint32_t last_outcome, words, bytes, crc32, elapsed_cycles, return_code;
    mroi_descriptor last;
} mroi_diagnostics;

enum {
    MROI_NO_OFFER=0, MROI_COMPLETED=1, MROI_ABORTED_QUIESCENT=2,
    MROI_RETRY_SNAPSHOT=3, MROI_BAD_DESCRIPTOR=4,
    MROI_PLATFORM_ERROR=5, MROI_QUIESCENCE_PENDING=6
};

uint32_t mroi_crc_word(uint32_t crc, uint32_t word);
int mroi_process_one(const mroi_io *io, volatile mroi_diagnostics *diag);
/* An optional direct-image stage runs entirely inside the claimed lease.
 * feed receives monotonically increasing original ROI words, never a geometric
 * needle strip. finish must call permit between bounded chunks of compute;
 * it must cease on false. RES1 is sent only after this stage has stopped all
 * access and returned. cancel must stop the stage before QUIE is promised.
 */
typedef struct {
    void *context;
    int (*begin)(void *,const mroi_descriptor *);
    int (*feed)(void *,uint32_t word_index,uint32_t word);
    int (*finish)(void *,int (*permit)(void *),void *permit_context,uint32_t *return_code);
    void (*cancel)(void *);
} mroi_consumer;
int mroi_process_one_with_consumer(const mroi_io *,volatile mroi_diagnostics *,const mroi_consumer *);

/* Exact exception PC/cause/address whitelist. Zero means fatal/unrelated.
 * No instruction-length guessing, IRQ swallowing, or unconditional PC+4.
 */
uint32_t mroi_guard_recovery(uint32_t cause, uint32_t pc, uint32_t address,
                            uint32_t armed, uint32_t expected_address,
                            uint32_t access_kind, uint32_t physical_base,
                            uint32_t load_pc, uint32_t load_wait_pc,
                            uint32_t store_pc, uint32_t store_wait_pc,
                            uint32_t load_recover, uint32_t store_recover);
#endif
