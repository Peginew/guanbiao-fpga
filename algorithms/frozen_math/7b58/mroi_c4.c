/* C4 scalar operator body adapted from frozen fea819 kernel. Layer order,
 * S32 accumulation and RNE-even remain; models and output-head count vary. */
#include "mroi_c4.h"
int8_t mroi_arena[32768] __attribute__((aligned(4)));
#define a (mroi_arena)
#define arena_b (mroi_arena+16384)
static uint8_t rows[5][128];
static const mroi_nn_layer *layers;
/* RNE-even signed32 power2 rescale. No signed overflow or negative right shift.
 * Actual trained MAC/bias ranges are checked by the exact int64 PC reference.
 */
int8_t mroi_requant(int32_t value,int shift,int relu) {
    uint32_t mag=value<0?0u-(uint32_t)value:(uint32_t)value;
    int32_t q;
    if(shift>0) {
        unsigned sh=(unsigned)shift;
        uint32_t base=mag>>sh,rem=mag&((1u<<sh)-1),half=1u<<(sh-1);
        base+=(rem>half)||((rem==half)&&(base&1u));
        q=value<0?-(int32_t)base:(int32_t)base;
    } else if(shift<0) {
        unsigned sh=(unsigned)-shift;
        if(mag>(127u>>sh))q=value<0?-128:127;
        else q=value<0?-(int32_t)(mag<<sh):(int32_t)(mag<<sh);
    } else q=value;
    if(q>127)q=127;
    if(q<(relu?0:-128))q=relu?0:-128;
    return(int8_t)q;
}
static int check(int (*permit)(void *),void *p,uint32_t layer,uint32_t row) {
    (void)layer;(void)row;return !permit||permit(p);
}
static int8_t rq(int32_t value,const mroi_nn_layer *l) {return mroi_requant(value,l->shift,l->relu);}
/* Four output accumulators share each source-byte fetch. Bounds are
 * clipped once per pixel, rather than tested in every channel/MAC. */
static void first_row(unsigned oy) {
    const mroi_nn_layer *l=&layers[0];unsigned ox,ky,kx;
    unsigned y0=2*oy<2?2-2*oy:0,y1=2*oy+2>=128?130-2*oy:5;
    const uint8_t *rowbase[5];
    for(ky=y0;ky<y1;ky++)rowbase[ky]=rows[(2*oy+ky-2)%5];
    for(ox=0;ox<64;ox++) {
        unsigned x0=2*ox<2?2-2*ox:0,x1=2*ox+2>=128?130-2*ox:5;
        int32_t z0=l->b[0],z1=l->b[1],z2=l->b[2],z3=l->b[3];
        for(ky=y0;ky<y1;ky++) {
            const uint8_t *v=&rowbase[ky][2*ox+x0-2];
            const int8_t *w=&l->w[ky*5+x0];
            for(kx=x0;kx<x1;kx++,v++,w++) {
                int32_t q=(int32_t)*v-128;
                z0+=q*w[0];z1+=q*w[25];z2+=q*w[50];z3+=q*w[75];
            }
        }
        a[(oy*64+ox)*4+0]=rq(z0,l);a[(oy*64+ox)*4+1]=rq(z1,l);
        a[(oy*64+ox)*4+2]=rq(z2,l);a[(oy*64+ox)*4+3]=rq(z3,l);
    }
}
/* HWC four-channel groups: spatial address and bounds are shared.
 * Each accumulator preserves its ky/kx order and S32 range contract. */
static void depth_groups(const int8_t *src,unsigned iw,unsigned ci,
                         unsigned y,unsigned x,unsigned stride,
                         const mroi_nn_layer *l,int8_t tmp[8]) {
    unsigned yy=y*stride,xx=x*stride;
    unsigned y0=yy<2?2-yy:0,y1=yy+2>=iw?iw+2-yy:5;
    unsigned x0=xx<2?2-xx:0,x1=xx+2>=iw?iw+2-xx:5;
    unsigned c,ky,kx;
    for(c=0;c<ci;c+=4) {
        int32_t z0=l->b[c],z1=l->b[c+1],z2=l->b[c+2],z3=l->b[c+3];
        for(ky=y0;ky<y1;ky++) {
            const int8_t *v=&src[((yy+ky-2)*iw+xx+x0-2)*ci+c];
            const int8_t *w=&l->w[c*25+ky*5+x0];
            for(kx=x0;kx<x1;kx++,v+=ci,w++) {
                z0+=(int32_t)v[0]*w[0];z1+=(int32_t)v[1]*w[25];
                z2+=(int32_t)v[2]*w[50];z3+=(int32_t)v[3]*w[75];
            }
        }
        tmp[c]=rq(z0,l);tmp[c+1]=rq(z1,l);
        tmp[c+2]=rq(z2,l);tmp[c+3]=rq(z3,l);
    }
}
static int pair(const int8_t *src,int8_t *dst,unsigned iw,unsigned ci,unsigned co,
                unsigned index,int (*permit)(void *),void *p) {
    const mroi_nn_layer *dw=&layers[index],*pw=&layers[index+1];
    unsigned ow=(iw+dw->stride-1)/dw->stride,y,x,o;
    for(y=0;y<ow;y++) {
        if(!check(permit,p,index,y))return 0;
        for(x=0;x<ow;x++) {
            int8_t tmp[8];
            depth_groups(src,iw,ci,y,x,dw->stride,dw,tmp);
            for(o=0;o<co;o++) {
                const int8_t *w=&pw->w[o*ci];
                int32_t acc=pw->b[o]+(int32_t)tmp[0]*w[0]+(int32_t)tmp[1]*w[1]+
                            (int32_t)tmp[2]*w[2]+(int32_t)tmp[3]*w[3];
                if(ci==8)acc+=(int32_t)tmp[4]*w[4]+(int32_t)tmp[5]*w[5]+
                             (int32_t)tmp[6]*w[6]+(int32_t)tmp[7]*w[7];
                dst[(y*ow+x)*co+o]=rq(acc,pw);
            }
        }
    }
    return 1;
}
static int context(int (*permit)(void *),void *p) {
    const mroi_nn_layer *l=&layers[9];unsigned y,x,c;
    for(y=0;y<8;y++) {
        if(!check(permit,p,9,y))return 0;
        for(x=0;x<8;x++) {
            int8_t tmp[8];depth_groups(a,8,8,y,x,1,l,tmp);
            for(c=0;c<8;c++)a[8192+(y*8+x)*8+c]=tmp[c];
        }
    }
    return 1;
}

void mroi_c4_start(const mroi_nn_layer *model) {layers=model;}
void mroi_c4_feed(unsigned index,uint32_t word) {
    unsigned row=index/32,col=(index%32)*4,k;
    for(k=0;k<4;k++)rows[row%5][col+k]=(uint8_t)(word>>(8*k));
    if(col==124&&row>=2&&!(row&1u))first_row((row-2)/2);
}
int mroi_c4_compute(int(*permit)(void*),void*p) {
    if(!check(permit,p,0,63))return 0;
    first_row(63);
    return pair(a,arena_b,64,4,4,1,permit,p)&&pair(arena_b,a,64,4,8,3,permit,p)&&
      pair(a,a+8192,32,8,8,5,permit,p)&&pair(a+8192,a,16,8,8,7,permit,p)&&context(permit,p);
}
const int8_t *mroi_c4_map(unsigned output) {
    const mroi_nn_layer *f=&layers[10],*h=&layers[11];unsigned y,x,c,i;
    if(output>=h->co)return 0;
    for(y=0;y<64;y++)for(x=0;x<64;x++) {
        const int8_t *lo=&a[8192+((y/8)*8+x/8)*8],*hi=&arena_b[(y*64+x)*4];
        int8_t t[4];int32_t acc;
        for(c=0;c<4;c++) {
            acc=f->b[c];
            for(i=0;i<4;i++)acc+=(int32_t)hi[i]*f->w[c*12+i];
            for(i=0;i<8;i++)acc+=(int32_t)lo[i]*f->w[c*12+4+i];
            t[c]=rq(acc,f);
        }
        acc=h->b[output];for(c=0;c<4;c++)acc+=(int32_t)t[c]*h->w[output*4+c];
        a[y*64+x]=rq(acc,h);
    }
    return a;
}
