#include "reader_runtime.h"
#include "meter_mcu_roi_abi.h"
#include "hub_weights_q8.h"
#include "landmark_weights_q8.h"
#include "landmark_reference.h"
#include <string.h>

volatile mroi_reader_diagnostics mroi_reader_diag;
static const mroi_io *reader_io;
static uint32_t progress_feature;
static uint32_t stamp(void) {return reader_io&&reader_io->cycles?reader_io->cycles(reader_io->context):0;}
static int allowed(int(*permit)(void*),void*p) {return !permit||permit(p);}
void mroi_reader_bind(const mroi_io *io) {reader_io=io;}
uint32_t mroi_reader_psi_word(void) {return mroi_reader_diag.psi_word;}
static int fetch_roi(int use_cnn,int(*permit)(void*),void*p) {
    unsigned i,k;uint32_t w;
    for(i=0;i<4096;i++) {
        if(!allowed(permit,p)||!reader_io||!reader_io->read32(reader_io->context,MROI_DATA+4*i,&w))return 0;
        if(use_cnn)mroi_c4_feed(i,w);
        else for(k=0;k<4;k++)mroi_arena[4*i+k]=(int8_t)(uint8_t)(w>>(8*k));
    }
    return 1;
}
/* The original initial4096-word CRC check completes before finish is entered.
 * A stage write carries only geometry evidence. Hardware tags it with the
 * still-claimed descriptor and holds it until the display-domain acknowledgement.
 * Neither this helper nor its AHB acknowledgement commits RES1 or permits PSI.
 */
static int publish_geometry(uint32_t code,int(*permit)(void*),void*p) {
    if(!progress_feature)return 1;
    if(!allowed(permit,p)||!reader_io||!reader_io->write32||
       !reader_io->write32(reader_io->context,MROI_RETURN_CODE,code))return 0;
    reader_io->fence(reader_io->context);
    return allowed(permit,p);
}
static int begin(void *unused,const mroi_descriptor *d) {
    uint32_t features=0;
    (void)unused;
    progress_feature=reader_io&&reader_io->read32&&
        reader_io->read32(reader_io->context,MROI_FEATURES,&features)&&
        (features&MROI_FEATURE_STAGE_PROGRESS_V1)&&reader_io->write32&&reader_io->fence;
    mroi_reader_diag.active=1;mroi_reader_diag.phase=1;mroi_reader_diag.words=0;
    mroi_reader_diag.epoch=d->epoch;mroi_reader_diag.source=d->source;mroi_reader_diag.job=d->job;
    mroi_reader_diag.radius=d->radius;mroi_reader_diag.return_code=1;mroi_reader_diag.psi_word=0;
    mroi_reader_diag.neural_valid=mroi_reader_diag.reference_valid=mroi_reader_diag.read_valid=0;
    mroi_reader_diag.reference_kind=0;mroi_c4_start(hub_layers);return 1;
}
static int feed(void*unused,uint32_t index,uint32_t word) {
    (void)unused;if(!mroi_reader_diag.active||index!=mroi_reader_diag.words||index>=4096)return 0;
    mroi_c4_feed(index,word);mroi_reader_diag.words++;return 1;
}
static int finish(void*unused,int(*permit)(void*),void*p,uint32_t*code) {
    mroi_point hub,lm[6];reader_needle needle;mp_result ring;mlg_result print;
    mlg_point_q8 points[6],normal[6],center;uint8_t mask=0;uint16_t psi=0;
    unsigned i;uint32_t t;int neural,reference;int32_t roll=0;
    (void)unused;
    if(!mroi_reader_diag.active||mroi_reader_diag.words!=4096)return 0;
    t=stamp();
    if(!mroi_c4_compute(permit,p))return 0;
    mroi_decode_map(mroi_c4_map(0),&hub);mroi_reader_diag.hub=hub;
    mroi_reader_diag.stage_cycles[0]=stamp()-t;
    *code=hub.valid?(0x40000000u|(16u<<22)|((uint32_t)((hub.x_q8+8)/16)<<11)|(uint32_t)((hub.y_q8+8)/16)):1u;
    if(hub.valid&&!publish_geometry(*code,permit,p))return 0;
    /* Analyze regardless of PSI/reference success. Read permission is separate
     * from producing six-point, hub and needle evidence for diagnostics. */
    t=stamp();mroi_reader_diag.phase=2;mroi_c4_start(landmark_layers);
    if(!fetch_roi(1,permit,p)||!mroi_c4_compute(permit,p))return 0;
    for(i=0;i<6;i++) {
        if(!allowed(permit,p))return 0;
        mroi_decode_map(mroi_c4_map(i),&lm[i]);
        lm[i].valid=(uint8_t)(lm[i].peak_q15>=LANDMARK_PEAK_Q15&&lm[i].margin_q15>=LANDMARK_MARGIN_Q15);
        mroi_reader_diag.landmark[i]=lm[i];points[i].x=lm[i].x_q8;points[i].y=lm[i].y_q8;
        if(lm[i].valid)mask|=(uint8_t)(1u<<i);
    }
    mroi_reader_diag.stage_cycles[1]=stamp()-t;
    t=stamp();mroi_reader_diag.phase=3;
    if(!fetch_roi(0,permit,p)||!reader_polar((uint8_t *)(void *)mroi_arena,hub.x_q8,hub.y_q8,mroi_reader_diag.radius,&needle,permit,p))return 0;
    mroi_reader_diag.needle=needle;mroi_reader_diag.stage_cycles[2]=stamp()-t;
    {
        int32_t dx=hub.x_q8-16256,dy=hub.y_q8-16256;
        neural=hub.valid&&needle.valid&&(int64_t)dx*dx+(int64_t)dy*dy<=400*65536;
    }
    mroi_reader_diag.neural_valid=(uint32_t)neural;
    if(neural) {
        unsigned deg=(unsigned)((needle.angle_q16+32768)/65536)%360;
        *code=0x80000000u|(deg<<22)|((uint32_t)((hub.x_q8+8)/16)<<11)|(uint32_t)((hub.y_q8+8)/16);
        if(!publish_geometry(*code,permit,p))return 0;
    }
    /* The same accepted old ring wins exactly by policy. Landmark absence
     * never deletes a valid same-observation old reference. */
    t=stamp();mroi_reader_diag.phase=4;
    if(!fetch_roi(0,permit,p)||!reader_ring((uint8_t *)(void *)mroi_arena,hub.x_q8,hub.y_q8,mroi_reader_diag.radius,&ring,permit,p))return 0;
    mroi_reader_diag.ring=ring;mroi_reader_diag.stage_cycles[3]=stamp()-t;
    center.x=hub.x_q8;center.y=hub.y_q8;
    if(mlg_normalize_q8(points,center,mroi_reader_diag.radius*256u,mask,normal))return 0;
    mlg_consensus_q8(mlg_reference_q8,normal,mask,MLG_REFERENCE_ROLL_Q16,&print);
    mroi_reader_diag.print=print;
    reference=ring.accepted||print.accepted;
    if(ring.accepted){roll=(int32_t)ring.delta_deg*65536;mroi_reader_diag.reference_kind=1;}
    else if(print.accepted){roll=print.roll_deg_q16;mroi_reader_diag.reference_kind=2;}
    mroi_reader_diag.reference_valid=(uint32_t)reference;mroi_reader_diag.selected_roll_q16=roll;
    if(neural&&reference&&reader_calibrate_psi_q8(needle.angle_q16,roll,&psi)) {
        mroi_reader_diag.psi_word=MROI_PSI_VALID|psi;mroi_reader_diag.read_valid=1;
    }
    if(!allowed(permit,p))return 0;
    mroi_reader_diag.return_code=*code;mroi_reader_diag.phase=5;mroi_reader_diag.active=0;mroi_reader_diag.completed++;
    return 1;
}
static void cancel(void*unused) {(void)unused;mroi_reader_diag.active=0;mroi_reader_diag.psi_word=0;mroi_reader_diag.read_valid=0;mroi_reader_diag.phase=6;mroi_reader_diag.cancelled++;}
const mroi_consumer mroi_reader_stage={0,begin,feed,finish,cancel};
#ifdef MROI_HOST_TEST
static int host_read(void*context,uint32_t offset,uint32_t*word) {
    const uint8_t *roi=context;unsigned k;*word=0;
    if(offset<MROI_DATA||offset>MROI_DATA_LAST_WORD||(offset&3u))return 0;
    for(k=0;k<4;k++)*word|=(uint32_t)roi[offset-MROI_DATA+k]<<(8*k);
    return 1;
}
uint32_t mroi_reader_diagnostic_size(void){return sizeof(mroi_reader_diagnostics);}
int mroi_reader_host_infer(const uint8_t *roi,unsigned radius,mroi_reader_diagnostics*out) {
    mroi_io io={(void*)roi,host_read,0,0,0,0};mroi_descriptor d={0};uint32_t code;unsigned i,k;
    mroi_reader_bind(&io);d.radius=radius;begin(0,&d);
    for(i=0;i<4096;i++){uint32_t w=0;for(k=0;k<4;k++)w|=(uint32_t)roi[i*4+k]<<(8*k);if(!feed(0,i,w))return 0;}
    if(!finish(0,0,0,&code))return 0;
    memcpy(out,(const void*)&mroi_reader_diag,sizeof(*out));return 1;
}
#endif
