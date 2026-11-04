#include "reader_numeric.h"
#include "mroi_c4.h"
#include "meter_pose_frontend.h"
#include "reader_tables.h"
#include "reader_ring_templates.h"
#include "polar_weights_q8.h"
#include "polar_quant_config.h"
#include "reader_calibration_domain.h"

static int32_t rne_ratio(int32_t x,uint32_t denominator) {
    uint32_t a=x<0?0u-(uint32_t)x:(uint32_t)x,q=a/denominator,r=a%denominator;
    q+=(r*2u>denominator)||(r*2u==denominator&&(q&1u));
    return x<0?-(int32_t)q:(int32_t)q;
}
static int16_t rne_coordinate(double x) {
    int32_t q=(int32_t)x;double d=x-q;
    if(d>.5||(d==.5&&(q&1)))q++;
    else if(d<-.5||(d==-.5&&(q&1)))q--;
    return (int16_t)q;
}
static int16_t rne_coordinate_f32(float x) {
    int32_t q=(int32_t)x;float d=x-(float)q;
    if(d>.5f||(d==.5f&&(q&1)))q++;
    else if(d<-.5f||(d==-.5f&&(q&1)))q--;
    return (int16_t)q;
}
static int8_t clip8(int32_t x) {return (int8_t)(x<-128?-128:x>127?127:x);}
static int16_t coordinate_q50_to_q5(int64_t n) {
    uint64_t a=n<0?(uint64_t)-n:(uint64_t)n,q=a>>45,r=a&((UINT64_C(1)<<45)-1);
    q+=(r>(UINT64_C(1)<<44))||(r==(UINT64_C(1)<<44)&&(q&1u));
    return (int16_t)(n<0?-(int32_t)q:(int32_t)q);
}
static int permits(int(*fn)(void*),void*p) {return !fn||fn(p);}
static void flash_copy_aligned_words(uint8_t *out,const void *source,unsigned bytes) {
    uintptr_t p=(uintptr_t)source,base=p&~(uintptr_t)3;uint32_t word=0;unsigned i;
    for(i=0;i<bytes;i++,p++) {
        uintptr_t next=p&~(uintptr_t)3;
        if(!i||next!=base){base=next;word=*(const volatile uint32_t *)base;}
        out[i]=(uint8_t)(word>>((p&3u)*8));
    }
}

int reader_polar(const uint8_t *gray,int32_t hx_q8,int32_t hy_q8,unsigned radius,
    reader_needle *out,int(*permit)(void*),void*context) {
    uint16_t *bands=(uint16_t *)(void *)(mroi_arena+16384);
    int8_t *input=mroi_arena+16384+8192,*first=mroi_arena,*dw=mroi_arena+4096;
    int8_t *mixed=mroi_arena+8192,*logits=mroi_arena+10000;
    unsigned k,j,a,c,o,best=0;int top=-1,far=0;uint32_t invalid=0;
    int16_t *xq=(int16_t *)(void *)(mroi_arena+12000),*yq=xq+360;
    uint8_t *sample=(uint8_t *)(void *)(mroi_arena+14000);
    float hx=hx_q8/256.f,hy=hy_q8/256.f;
    for(k=0;k<8;k++) {
        for(a=0;a<360;a++)bands[k*360+a]=0;
        for(j=0;j<3;j++) {
            float r=(reader_polar_fractions[k]+((float)j-1.f)*.02f)*(float)radius;
            if(!permits(permit,context))return 0;
            for(a=0;a<360;a++) {
                float x=hx+r*reader_cos_f32[a],y=hy+r*reader_sin_f32[a];
                invalid+=(x<0||x>127||y<0||y>127);
                xq[a]=rne_coordinate_f32(x*32.f);yq[a]=rne_coordinate_f32(y*32.f);
            }
            mpf_bilinear_q5_u8(gray,xq,yq,360,sample);
            for(a=0;a<360;a++)bands[k*360+a]=(uint16_t)(bands[k*360+a]+sample[a]);
        }
    }
    for(k=0;k<8;k++)for(a=0;a<360;a++) {
        int32_t v=bands[k*360+a],l=bands[k*360+(a+356)%360],r=bands[k*360+(a+4)%360];
        input[k*360+a]=clip8(rne_ratio(v-384,6));
        input[(k+8)*360+a]=clip8(rne_ratio(l+r-2*v,6));
    }
    /* Input complete: the raw image A is dead. Circular channel-major CNN. */
    for(o=0;o<8;o++)for(a=0;a<360;a++) {
        int32_t sum=polar_b0[o];
        for(c=0;c<16;c++)for(j=0;j<7;j++)sum+=(int32_t)input[c*360+(a+j+357)%360]*polar_w0[(o*16+c)*7+j];
        first[o*360+a]=mroi_requant(sum,POLAR_SHIFT0,1);
        if(!a&&!permits(permit,context))return 0;
    }
    for(c=0;c<8;c++)for(a=0;a<360;a++) {
        int32_t sum=polar_b1[c];for(j=0;j<7;j++)sum+=(int32_t)first[c*360+(a+j+357)%360]*polar_w1[c*7+j];
        dw[c*360+a]=mroi_requant(sum,POLAR_SHIFT1,1);
    }
    for(o=0;o<4;o++)for(a=0;a<360;a++) {
        int32_t sum=polar_b2[o];for(c=0;c<8;c++)sum+=(int32_t)dw[c*360+a]*polar_w2[o*8+c];
        mixed[o*360+a]=mroi_requant(sum,POLAR_SHIFT2,1);
    }
    for(a=0;a<360;a++) {
        int32_t sum=polar_b3[0];for(c=0;c<4;c++)sum+=(int32_t)mixed[c*360+a]*polar_w3[c];
        logits[a]=mroi_requant(sum,POLAR_SHIFT3,0);
        {int v=reader_sigmoid_q15[(int)logits[a]+128];if(v>top){top=v;best=a;}}
    }
    {
        uint32_t total=0;int32_t moment=0;int i;
        for(i=-2;i<=2;i++){unsigned ai=(best+360+i)%360;uint32_t w=reader_sigmoid_q15[(int)logits[ai]+128];total+=w;moment+=i*(int32_t)w;}
        int32_t shift=0;
        if(total) {
            int64_t n=(int64_t)moment*65536;uint64_t mag=n<0?(uint64_t)-n:(uint64_t)n;
            uint32_t q=(uint32_t)(mag/total),r=(uint32_t)(mag%total);
            q+=(r*2u>total)||(r*2u==total&&(q&1u));shift=n<0?-(int32_t)q:(int32_t)q;
        }
        out->angle_q16=(int32_t)(best*65536u)+shift;
        if(out->angle_q16<0)out->angle_q16+=360*65536;
        if(out->angle_q16>=360*65536)out->angle_q16-=360*65536;
    }
    for(a=0;a<360;a++) {unsigned d=a>best?a-best:best-a;int v=reader_sigmoid_q15[(int)logits[a]+128];if(d>180)d=360-d;if(d>10&&v>far)far=v;}
    out->peak_q15=(uint16_t)top;out->margin_q15=(uint16_t)(top-far);
    out->outside=(uint16_t)invalid;out->valid=(uint8_t)(out->peak_q15>=9831&&out->margin_q15>=656&&invalid<=432);
    return permits(permit,context);
}

int reader_ring(uint8_t *gray,int32_t hx_q8,int32_t hy_q8,unsigned radius,
    mp_result *out,int(*permit)(void*),void*context) {
    uint8_t *work=(uint8_t *)(void *)(mroi_arena+16384);
    int8_t *profile=(int8_t *)(void *)work;
    mp_context *matcher=(mp_context *)(void *)(work+4320);
    uint8_t *asset=work+5440;mp_template local[2];
    unsigned dx,dy,s,k,a,id=0;
    int32_t dcx=hx_q8-16256,dcy=hy_q8-16256;
    int center_allowed=(int64_t)dcx*dcx+(int64_t)dcy*dcy<=196*65536;
    mp_prepare(matcher,(uint8_t)center_allowed);
    if(!center_allowed)return mp_finish(matcher,out)==MP_OK;
    mpf_normalize9x9_u8(gray,gray,(mpf_normalize_workspace *)(void *)work);
    /* AlignedLW copies from physical XIP Flash. Templates live in the dead
     * CNN B buffer for this stage:4320profile+1104context+9898template bytes.
     * This does not assume byte/halfword MMIO support in the QSPI window. */
    flash_copy_aligned_words((uint8_t *)(void *)local,reader_templates,sizeof(local));
    for(k=0;k<2;k++) {
        unsigned size=local[k].count*2u;
        flash_copy_aligned_words(asset,local[k].indices,size);local[k].indices=(const uint16_t *)(void *)asset;asset+=size;
        flash_copy_aligned_words(asset,local[k].values,local[k].count);local[k].values=(const int8_t *)(void *)asset;asset+=local[k].count;
        /* All frozen selected counts are even, keeping thisS16 array aligned. */
        flash_copy_aligned_words(asset,local[k].local_shift,49u*2u);local[k].local_shift=(const int16_t *)(void *)asset;asset+=98;
    }
    for(dx=0;dx<3;dx++)for(dy=0;dy<3;dy++)for(s=0;s<3;s++,id++) {
        uint16_t outside=0;
        int32_t cx=hx_q8+((int32_t)dx-1)*384,cy=hy_q8+((int32_t)dy-1)*384;
        uint32_t scale=s==0?97:s==1?100:103;
        if(!permits(permit,context))return 0;
        for(k=0;k<12;k++) {
            /* fractions=(110+12*k)/275, radius-scale=97/100,1,103/100.
             * Q20 radial rounding precedes Q30 trig multiply. Pixel Q50 is
             * bounded<2^59 and Q5 uses signed-magnitude RNE. */
            uint64_t rn=(uint64_t)radius*scale*(110u+12u*k)*(UINT64_C(1)<<20);
            uint64_t radial=rn/27500u,rem=rn%27500u;
            radial+=(rem*2u>27500u)||(rem*2u==27500u&&(radial&1u));
            for(a=0;a<360;a++) {
                int64_t x=(int64_t)cx*(INT64_C(1)<<42)+(int64_t)radial*reader_cos_q30[a];
                int64_t y=(int64_t)cy*(INT64_C(1)<<42)+(int64_t)radial*reader_sin_q30[a];
                int16_t xq,yq;
                outside+=(x<0||x>(INT64_C(127)<<50)||y<0||y>(INT64_C(127)<<50));
                xq=coordinate_q50_to_q5(x);yq=coordinate_q50_to_q5(y);
                mpf_bilinear_q5_u8(gray,&xq,&yq,1,work+k*360+a);
            }
        }
        mpf_normalize_profile_s8(work,profile);
        if(mp_push(matcher,profile,outside,(uint8_t)id,local,2)<0)return 0;
    }
    return mp_finish(matcher,out)==MP_OK;
}

int reader_calibrate_psi_q8_domain(int32_t image_angle_q16,int32_t roll_q16,int domain,uint16_t *psi_q8) {
    /* Frozen TRAIN-only PSI fit and its original interpolation domain. No
     * clamping/pressure-driven choice, no stale0..0.51bar TEST conversion. */
    double angle=((double)image_angle_q16-roll_q16)/65536.;
    double psi;
    while(angle<226.53468560074674-180.)angle+=360.;
    while(angle>=226.53468560074674+180.)angle-=360.;
    if(domain==READER_CAL_DOMAIN_OLD) {
        if(angle<164.9189063841552||angle>288.1874999590581)return 0;
    } else if(domain==READER_CAL_DOMAIN_TRAIN_CORRECTED) {
        /* SignedTRAINdomain only; integerQ16 inwardceil/floor, noGfit. */
        int32_t corrected_q16=(int32_t)(angle*65536.);
        if(corrected_q16<READER_TRAIN_DOMAIN_MIN_Q16||corrected_q16>READER_TRAIN_DOMAIN_MAX_Q16)return 0;
    } else return 0;
    psi=.07384237755296061*angle-9.35728614979227;
    if(psi<2.5||psi>12.)return 0;
    *psi_q8=(uint16_t)rne_coordinate(psi*256.);return 1;
}
int reader_calibrate_psi_q8(int32_t image_angle_q16,int32_t roll_q16,uint16_t *psi_q8) {
    return reader_calibrate_psi_q8_domain(image_angle_q16,roll_q16,READER_CAL_DOMAIN_TRAIN_CORRECTED,psi_q8);
}
