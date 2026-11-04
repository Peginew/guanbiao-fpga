#include "mroi_client.h"
#include "platform_binding.h"
#ifdef MROI_DIRECT_CNN
#include "reader_runtime.h"
#endif

volatile mroi_diagnostics mroi_diag;
volatile uint32_t mroi_guard_state[3]; /* armed,expected_addr,read1/write2 */
volatile uint32_t mroi_exception_mepc; /* actual CSR MEPC; saved frame retained */
volatile uint32_t mroi_fault[6];       /* recovered,cause,pc,mtval,fatal,pending */
/* Persistent complete-job records. report_sequence is this software report's
 * seqlock (odd=in-progress), distinct from ABI descriptor generation. */
typedef struct {
    uint32_t report_sequence, heartbeat, completed, aborted, last_outcome;
    uint32_t crc32, bytes, elapsed_cycles,return_code;
    mroi_descriptor descriptor;
} mroi_live_report;
volatile mroi_live_report mroi_live;
static void publish_live(int outcome) {
    mroi_live.report_sequence++;
    __asm__ volatile("fence rw,rw":::"memory");
    mroi_live.heartbeat=mroi_diag.heartbeat;
    mroi_live.completed=mroi_diag.completed;
    mroi_live.aborted=mroi_diag.aborted;
    mroi_live.last_outcome=(uint32_t)outcome;
    mroi_live.crc32=mroi_diag.crc32;
    mroi_live.bytes=mroi_diag.bytes;
    mroi_live.elapsed_cycles=mroi_diag.elapsed_cycles;
    mroi_live.return_code=mroi_diag.return_code;
    mroi_live.descriptor=mroi_diag.last;
    __asm__ volatile("fence rw,rw":::"memory");
    mroi_live.report_sequence++;
}
extern int mroi_guard_load(uint32_t,uint32_t *);
extern int mroi_guard_store(uint32_t,uint32_t);
extern char mroi_guard_load_pc[],mroi_guard_load_wait_pc[];
extern char mroi_guard_store_pc[],mroi_guard_store_wait_pc[];
extern char mroi_guard_load_recover[],mroi_guard_store_recover[];

static uint32_t cycles(void *unused) {
    uint32_t value;(void)unused;
    __asm__ volatile("csrr %0,mcycle":"=r"(value));return value;
}
static void fence(void *unused) {(void)unused;__asm__ volatile("fence iorw,iorw":::"memory");}
static int read_word(void *unused,uint32_t off,uint32_t *value) {
    (void)unused;return mroi_guard_load(MROI_PHYSICAL_BASE+off,value);
}
static int write_word(void *unused,uint32_t off,uint32_t value) {
    (void)unused;return mroi_guard_store(MROI_PHYSICAL_BASE+off,value);
}
static __attribute__((noreturn)) void stop_unexpected(void) {
    __asm__ volatile("csrw mie,zero; csrci mstatus,8":::"memory");
    for(;;)__asm__ volatile("wfi");
}

/* SDK nuclei_intexc.S SAVE_CSR_CONTEXT stores MEPC at12*4(sp), and its
 * RESTORE_CSR_CONTEXT reloads from that slot. Updating CSR_MEPC alone is wrong.
 * Exact SDK SHA/source is bound in the build receipt; this is not a generic ABI.
 */
uint32_t core_exception_handler(unsigned long cause,unsigned long sp,unsigned long fp) {
    volatile uint32_t *saved=(volatile uint32_t *)(uintptr_t)sp;
    uint32_t address,pc=saved[12],recover;(void)fp;
    __asm__ volatile("csrr %0,mtval":"=r"(address));
    __asm__ volatile("csrr %0,mepc":"=r"(mroi_exception_mepc));
    mroi_fault[1]=(uint32_t)cause;mroi_fault[2]=pc;mroi_fault[3]=address;
    recover=mroi_guard_recovery((uint32_t)cause,pc,address,mroi_guard_state[0],
             mroi_guard_state[1],mroi_guard_state[2],MROI_PHYSICAL_BASE,
             (uint32_t)(uintptr_t)mroi_guard_load_pc,(uint32_t)(uintptr_t)mroi_guard_load_wait_pc,
             (uint32_t)(uintptr_t)mroi_guard_store_pc,(uint32_t)(uintptr_t)mroi_guard_store_wait_pc,
             (uint32_t)(uintptr_t)mroi_guard_load_recover,(uint32_t)(uintptr_t)mroi_guard_store_recover);
    if(recover) {mroi_fault[0]++;saved[12]=recover;return 0;}
    mroi_fault[4]=1;stop_unexpected();
}

/* Minimal no-UART/no-external-IO hooks. SDK startup still establishes SP/GP,
 * cache-off state, counters and exception entry. Do not call logger/peripheral
 * init from the full board demo. No libc/static constructors are used.
 */
int atexit(void (*unused)(void)) {(void)unused;return 0;}
void __libc_init_array(void) {}
void __libc_fini_array(void) {}
void AlChip_Ph1p35Init(void) {}
void components_init(void) {}
void ECLIC_Isr_Nonvect(void) {mroi_fault[4]=2;stop_unexpected();}

#include "mroi_cold_start.c"
volatile uint32_t mroi_cold_boot_diag[4];

int main(void) {
    const mroi_io io={0,read_word,write_word,fence,cycles,0};
    mroi_reader_bind(&io);
    /* Global interrupts intentionally stay masked, no UART/LED/GPIO setup. */
    __asm__ volatile("csrw mie,zero; csrci mstatus,8":::"memory");
    if(mroi_cold_start(&io,mroi_cold_boot_diag)!=MROI_BOOT_OK) {
        mroi_fault[4]=0xcb00u|mroi_cold_boot_diag[1];
        stop_unexpected();
    }
    for(;;) {
#ifdef MROI_DIRECT_CNN
        int outcome=mroi_process_one_with_consumer(&io,&mroi_diag,&mroi_reader_stage);
#else
        int outcome=mroi_process_one(&io,&mroi_diag);
#endif
        /* RES1 already certifies no more DATA/RETURN access for this token.
         * A live parent retires it with its own CDC result acknowledgement;
         * no fixture-specific044 readback and no subsequent old-ROI reads. */
        if(outcome==MROI_COMPLETED || outcome==MROI_ABORTED_QUIESCENT)
            publish_live(outcome);

        if(outcome==MROI_QUIESCENCE_PENDING||outcome==MROI_PLATFORM_ERROR) {
            mroi_fault[5]=1;
            /* A timeout/fault is not evidence of CPU-reset-quiescence. */
            for(;;)mroi_diag.heartbeat++;
        }
    }
}
