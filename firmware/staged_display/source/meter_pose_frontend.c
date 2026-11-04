#include "meter_pose_frontend.h"

size_t mpf_normalize_workspace_size(void) { return sizeof(mpf_normalize_workspace); }
size_t mpf_profile_workspace_size(void) { return sizeof(mpf_profile_workspace); }

static unsigned clamp_image(int p)
{
    return p<0 ? 0u : p>=128 ? 127u : (unsigned)p;
}

int mpf_normalize9x9_u8(const uint8_t *source, uint8_t *normalized,
    mpf_normalize_workspace *work)
{
    unsigned x,y,k,head=0;
    if (!source || !normalized || !work) return -1;
    for (x=0; x<MPF_WIDTH; ++x) work->vertical_sums[x]=0;
    for (k=0; k<9; ++k) {
        unsigned sy=clamp_image((int)k-4);
        for (x=0; x<MPF_WIDTH; ++x) {
            uint8_t v=source[sy*MPF_WIDTH+x];
            work->source_rows[k*MPF_WIDTH+x]=v;
            work->vertical_sums[x]=(uint16_t)(work->vertical_sums[x]+v);
        }
    }
    for (y=0; y<MPF_HEIGHT; ++y) {
        uint32_t sum=0;
        int j;
        for (j=-4; j<=4; ++j) sum+=work->vertical_sums[clamp_image(j)];
        for (x=0; x<MPF_WIDTH; ++x) {
            int32_t mean=(int32_t)((sum+40u)/81u);
            int32_t v=3*((int32_t)source[y*MPF_WIDTH+x]-mean)+128;
            normalized[y*MPF_WIDTH+x]=(uint8_t)(v<0 ? 0 : v>255 ? 255 : v);
            if (x+1u<MPF_WIDTH) {
                sum-=work->vertical_sums[clamp_image((int)x-4)];
                sum+=work->vertical_sums[clamp_image((int)x+5)];
            }
        }
        if (y+1u<MPF_HEIGHT) {
            unsigned sy=clamp_image((int)y+5);
            for (x=0; x<MPF_WIDTH; ++x) {
                uint8_t incoming=source[sy*MPF_WIDTH+x];
                uint8_t previous=work->source_rows[head*MPF_WIDTH+x];
                work->vertical_sums[x]=(uint16_t)((uint32_t)work->vertical_sums[x]-previous+incoming);
                work->source_rows[head*MPF_WIDTH+x]=incoming;
            }
            head=(head+1u)%9u;
        }
    }
    return 0;
}

static int32_t floor_q5(int16_t q)
{
    int32_t v=q;
    /* C99 division truncates toward0, while Python//32 floors. */
    return v>=0 ? v/32 : -((-v+31)/32);
}

static uint32_t fetch(const uint8_t *image, int32_t x, int32_t y)
{
    if (x<0 || x>=128 || y<0 || y>=128) return 128u;
    return image[(unsigned)y*MPF_WIDTH+(unsigned)x];
}

int mpf_bilinear_q5_u8(const uint8_t *normalized, const int16_t *xq,
    const int16_t *yq, uint16_t count, uint8_t *sampled)
{
    uint16_t i;
    if (!normalized || !xq || !yq || !sampled) return -1;
    for (i=0; i<count; ++i) {
        int32_t x=floor_q5(xq[i]), y=floor_q5(yq[i]);
        uint32_t fx=(uint32_t)((int32_t)xq[i]-x*32);
        uint32_t fy=(uint32_t)((int32_t)yq[i]-y*32);
        uint32_t a=fetch(normalized,x,y), b=fetch(normalized,x+1,y);
        uint32_t c=fetch(normalized,x,y+1), d=fetch(normalized,x+1,y+1);
        uint32_t ab=a*(32u-fx)+b*fx;
        uint32_t cd=c*(32u-fx)+d*fx;
        uint32_t total=ab*(32u-fy)+cd*fy;
        sampled[i]=(uint8_t)((total+512u)>>10);
    }
    return 0;
}

static int32_t round_ratio_even(int32_t numerator, uint32_t denominator)
{
    uint32_t a=(uint32_t)(numerator<0 ? -numerator : numerator);
    uint32_t q=a/denominator, r=a%denominator;
    uint32_t twice=r*2u;
    if (twice>denominator || (twice==denominator && (q&1u))) ++q;
    return numerator<0 ? -(int32_t)q : (int32_t)q;
}

static void normalize_row(const uint8_t *sampled, int8_t *profile)
{
    unsigned i;
    int32_t sum=0;
    uint32_t abs_sum=0,denominator;
    for (i=0; i<MPF_ANGLES; ++i) sum+=sampled[i];
    for (i=0; i<MPF_ANGLES; ++i) {
        int32_t d=(int32_t)sampled[i]*360-sum;
        abs_sum+=(uint32_t)(d<0 ? -d : d);
    }
    denominator=abs_sum>777600u ? abs_sum : 777600u;
    for (i=0; i<MPF_ANGLES; ++i) {
        int32_t d=(int32_t)sampled[i]*360-sum;
        /* |d*11520| <=1057536000 < INT32_MAX. */
        int32_t q=round_ratio_even(d*11520,denominator);
        profile[i]=(int8_t)(q < -127 ? -127 : q>127 ? 127 : q);
    }
}

int mpf_normalize_profile_s8(const uint8_t *sampled, int8_t *profile)
{
    unsigned row;
    if (!sampled || !profile) return -1;
    for (row=0; row<MPF_BANDS; ++row)
        normalize_row(sampled+row*MPF_ANGLES,profile+row*MPF_ANGLES);
    return 0;
}

int mpf_profile_q5_s8(const uint8_t *normalized, const int16_t *xq,
    const int16_t *yq, int8_t *profile, mpf_profile_workspace *work)
{
    unsigned row;
    if (!normalized || !xq || !yq || !profile || !work) return -1;
    for (row=0; row<MPF_BANDS; ++row) {
        mpf_bilinear_q5_u8(normalized,xq+row*MPF_ANGLES,yq+row*MPF_ANGLES,
            MPF_ANGLES,work->sampled_row);
        normalize_row(work->sampled_row,profile+row*MPF_ANGLES);
    }
    return 0;
}
