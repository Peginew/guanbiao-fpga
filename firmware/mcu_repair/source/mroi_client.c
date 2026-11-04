#include "mroi_client.h"
#include "meter_mcu_roi_abi.h"
#ifdef MROI_LIVE_EXTENSIONS
#include "meter_mcu_live_abi.h"
#endif
#include "reader_runtime.h"

static int rd(const mroi_io *io, uint32_t off, uint32_t *v) {
    return io->read32(io->context,off,v);
}
static int wr(const mroi_io *io, uint32_t off, uint32_t v) {
    return io->write32(io->context,off,v);
}
static void barrier(const mroi_io *io) {io->fence(io->context);}
static uint32_t elapsed(const mroi_io *io, uint32_t start) {
    return io->cycles ? io->cycles(io->context)-start : 0;
}

/* Reflected IEEE CRC32, polynomial0xedb88320; unfinalized state in/out.
 * byte0 of word is processed first, exactly matching the existing little-endian
 * four-byte bitwise implementation. No lifecycle or caller state is changed.
 */
static const uint32_t mroi_crc4[16]={
    0x00000000u,0x1db71064u,0x3b6e20c8u,0x26d930acu,
    0x76dc4190u,0x6b6b51f4u,0x4db26158u,0x5005713cu,
    0xedb88320u,0xf00f9344u,0xd6d6a3e8u,0xcb61b38cu,
    0x9b64c2b0u,0x86d3d2d4u,0xa00ae278u,0xbdbdf21cu
};
uint32_t mroi_crc_word(uint32_t crc,uint32_t word) {
    unsigned nibble;
    crc^=word;
    for(nibble=0;nibble<8;nibble++)
        crc=(crc>>4)^mroi_crc4[crc&15u];
    return crc;
}


static int snapshot(const mroi_io *io, mroi_descriptor *d) {
    uint32_t a,b,s,t;
    if(!rd(io,MROI_SEQUENCE,&a) || !rd(io,MROI_STATUS,&s)) return -1;
    if(!(s&MROI_STATUS_VISIBLE)) return 0;
    if(!rd(io,MROI_EPOCH,&d->epoch)||!rd(io,MROI_SOURCE,&d->source)||
       !rd(io,MROI_JOB,&d->job)||!rd(io,MROI_TARGET,&d->target)||
       !rd(io,MROI_CONFIG,&d->config)||!rd(io,MROI_X0,&d->x0)||
       !rd(io,MROI_Y0,&d->y0)||!rd(io,MROI_SHAPE,&d->shape)||
       !rd(io,MROI_STRIDE,&d->stride)||!rd(io,MROI_RADIUS,&d->radius)||
       !rd(io,MROI_FORMAT,&d->format)||!rd(io,MROI_BYTES,&d->bytes)) return -1;
#ifdef MROI_LIVE_EXTENSIONS
    {
        uint32_t magic;
        if(!rd(io,MROI_LIVE_MAGIC,&magic)||magic!=MROI_LIVE_MAGIC_VALUE||
           !rd(io,MROI_LIVE_HWCRC,&d->hw_crc32)||!rd(io,MROI_LIVE_QUALITY,&d->quality_flags)||
           !rd(io,MROI_LIVE_MEAN,&d->mean)||!rd(io,MROI_LIVE_GRADIENT,&d->gradient)||
           !rd(io,MROI_LIVE_HISTOGRAM,&d->histogram))return -1;
        if(!(d->quality_flags&MROI_LIVE_SCAN_COMPLETE))return 2;
    }
#endif
    barrier(io);
    if(!rd(io,MROI_SEQUENCE,&b)||!rd(io,MROI_STATUS,&t)) return -1;
    /* ABI1 sequence is a generation counter, not an odd/even write seqlock. */
    if(a!=b||!(t&MROI_STATUS_VISIBLE)||(t&MROI_STATUS_REVOKED)) return 2;
    d->sequence=a;
    return 1;
}

static int same_claim(const mroi_io *io,const mroi_descriptor *d,int *claimed) {
    uint32_t s,e,src,j,seq;
    barrier(io);
    if(!rd(io,MROI_STATUS,&s)||!rd(io,MROI_SEQUENCE,&seq)||
       !rd(io,MROI_EPOCH,&e)||!rd(io,MROI_SOURCE,&src)||!rd(io,MROI_JOB,&j)) return -1;
    *claimed=(s&MROI_STATUS_CLAIMED)!=0;
    if(e!=d->epoch||src!=d->source||j!=d->job||seq!=d->sequence) return 0;
    return (s&MROI_STATUS_VISIBLE)&&!(s&MROI_STATUS_REVOKED)&&*claimed;
}

static int quiet(const mroi_io *io,const mroi_descriptor *d) {
    uint32_t s,e,src,j,seq;
    /* Caller has permanently stopped DATA and RETURN accesses for this token.
     * Synchronous guarded MMIO + DCache-off + fence precede this promise.
     */
    barrier(io);
    if(!rd(io,MROI_STATUS,&s)||!rd(io,MROI_SEQUENCE,&seq)||
       !rd(io,MROI_EPOCH,&e)||!rd(io,MROI_SOURCE,&src)||!rd(io,MROI_JOB,&j)) return 0;
    if(!(s&MROI_STATUS_CLAIMED)) return 1; /* failed claim or committed RES1 */
    if(e!=d->epoch||src!=d->source||j!=d->job||seq!=d->sequence) return 0;
    if(!wr(io,MROI_QUIET_EPOCH,d->epoch)||!wr(io,MROI_QUIET_SOURCE,d->source)||
       !wr(io,MROI_QUIET_JOB,d->job)) return 0;
    barrier(io);
    if(!wr(io,MROI_QUIET_COMMIT,MROI_QUIET_MAGIC)) return 0;
    barrier(io);
    return rd(io,MROI_STATUS,&s)&&!(s&MROI_STATUS_CLAIMED);
}

typedef struct {const mroi_io *io;const mroi_descriptor *d;uint32_t start;} permit_context;
static int stage_permit(void *context) {
    permit_context *p=(permit_context *)context;int claimed;
    return (!p->io->cycle_budget||elapsed(p->io,p->start)<p->io->cycle_budget)&&
           same_claim(p->io,p->d,&claimed)==1;
}
int mroi_process_one_with_consumer(const mroi_io *io,volatile mroi_diagnostics *diag,const mroi_consumer *stage) {
    mroi_descriptor d={0};
    uint32_t id,abi,word,crc=0xffffffffu,now0=io->cycles?io->cycles(io->context):0;
    uint32_t i,return_code=0; int rc,claimed=0,stage_started=0;
    permit_context pc={io,&d,now0};
    diag->heartbeat++;diag->words=0;diag->bytes=0;diag->crc32=0;
    if(!rd(io,MROI_ID,&id)||!rd(io,MROI_ABI,&abi)||id!=MROI_ID_VALUE||abi!=MROI_ABI_VALUE)
        return diag->last_outcome=MROI_PLATFORM_ERROR;
    rc=snapshot(io,&d);
    if(rc<0) return diag->last_outcome=MROI_PLATFORM_ERROR;
    if(rc==0) {diag->no_offer++;return diag->last_outcome=MROI_NO_OFFER;}
    if(rc==2) return diag->last_outcome=MROI_RETRY_SNAPSHOT;
    diag->last=d;
    if(d.shape!=0x00800080u||d.format!=1||d.bytes!=MROI_CANONICAL_BYTES||
       d.target>65535||d.x0>=1280||d.y0>=720||(d.stride<1||d.stride>4)||
       d.x0+128u*d.stride>1280||d.y0+128u*d.stride>720||d.radius<40||d.radius>62)
        return diag->last_outcome=MROI_BAD_DESCRIPTOR;
    if(!wr(io,MROI_CLAIM_EPOCH,d.epoch)||!wr(io,MROI_CLAIM_SOURCE,d.source)||
       !wr(io,MROI_CLAIM_JOB,d.job)) goto abort;
    barrier(io);
    if(!wr(io,MROI_CLAIM_COMMIT,MROI_CLAIM_MAGIC)) goto abort;
    if(stage) {
        stage_started=1;
        if(!stage->begin(stage->context,&d))goto abort;
    }
    for(i=0;i<MROI_CANONICAL_BYTES/4u;i++) {
        if(same_claim(io,&d,&claimed)!=1) goto abort;
        if(io->cycle_budget&&elapsed(io,now0)>=io->cycle_budget) goto abort;
        /* This guarded lw may trap even after STATUS was valid (cancel race). */
        if(!rd(io,MROI_DATA+4u*i,&word)) goto abort;
        crc=mroi_crc_word(crc,word);diag->words=i+1;diag->bytes=(i+1)*4u;
        if(stage&&!stage->feed(stage->context,i,word))goto abort;
    }
    crc^=0xffffffffu;
    if(same_claim(io,&d,&claimed)!=1) goto abort;
#ifdef MROI_LIVE_EXTENSIONS
    if(crc!=d.hw_crc32) {
        /* A complete but corrupted transfer is still retired truthfully; the
         * parent compares its retained CRC too. Never label it CNN evidence. */
        if(stage_started)stage->cancel(stage->context);
        stage=0;stage_started=0;return_code=3;
    }
#endif
    if(stage&&!stage->finish(stage->context,stage_permit,&pc,&return_code))goto abort;
    if(stage&&!stage_permit(&pc))goto abort;
    if(!wr(io,MROI_RETURN_EPOCH,d.epoch)||!wr(io,MROI_RETURN_SOURCE,d.source)||
       !wr(io,MROI_RETURN_JOB,d.job)||!wr(io,MROI_RETURN_TARGET,d.target)||
       !wr(io,MROI_RETURN_CONFIG,d.config)||!wr(io,MROI_RETURN_CRC32,crc)||
       !wr(io,MROI_RETURN_BYTES,MROI_CANONICAL_BYTES)||
       !wr(io,MROI_RETURN_PSI_Q8,stage?mroi_reader_psi_word():0u)||
       !wr(io,MROI_RETURN_CODE,return_code)) goto abort;
    barrier(io);
    if(!wr(io,MROI_RETURN_COMMIT,MROI_RETURN_MAGIC)) goto abort;
    barrier(io);
    diag->crc32=crc;diag->return_code=return_code;diag->elapsed_cycles=elapsed(io,now0);diag->completed++;
    return diag->last_outcome=MROI_COMPLETED;
abort:
    if(stage_started)stage->cancel(stage->context);
    diag->elapsed_cycles=elapsed(io,now0);diag->aborted++;
    if(quiet(io,&d)) return diag->last_outcome=MROI_ABORTED_QUIESCENT;
    diag->pending++;
    /* Never spin/read the ROI or mark CPU-reset-quiescent after a failed QUIE. */
    return diag->last_outcome=MROI_QUIESCENCE_PENDING;
}
int mroi_process_one(const mroi_io *io,volatile mroi_diagnostics *diag) {
    return mroi_process_one_with_consumer(io,diag,0);
}

uint32_t mroi_guard_recovery(uint32_t cause,uint32_t pc,uint32_t address,
                           uint32_t armed,uint32_t expected_address,
                           uint32_t kind,uint32_t base,
                           uint32_t load_pc,uint32_t load_wait_pc,
                           uint32_t store_pc,uint32_t store_wait_pc,
                           uint32_t load_recover,uint32_t store_recover) {
    uint32_t off=address-base;
    uint32_t exception_code=cause&0x00000fffu;
    int allowed=0;
    /* PH1P35 installed NMSIS CSR_MCAUSE_Type: exception code is low12;
     * MPP/MPIL/MPIE are saved context, not part of that code. Never recover
     * an IRQ, vector-table failure, or reserved encoding by masking it. */
    if(cause&0xc700f000u)return 0;
    if(armed!=1||address!=expected_address||address<base||(address&3u)||off>0x4ffcu) return 0;
    if(kind==1) allowed=(off<=0x44u)||(off>=MROI_DATA&&off<=MROI_DATA_LAST_WORD);
#ifdef MROI_LIVE_EXTENSIONS
    if(kind==1&&off>=MROI_LIVE_HWCRC&&off<=MROI_FEATURES)allowed=1;
#endif
    else if(kind==2) allowed=(off>=0x80u&&off<=0x8cu)||
                            (off>=0x100u&&off<=MROI_RETURN_PSI_Q8)||(off>=0x180u&&off<=0x18cu);
    if(!allowed) return 0;
    if(kind==1&&exception_code==5u&&(pc==load_pc||pc==load_wait_pc)) return load_recover;
    if(kind==2&&exception_code==7u&&(pc==store_pc||pc==store_wait_pc)) return store_recover;
    return 0;
}
