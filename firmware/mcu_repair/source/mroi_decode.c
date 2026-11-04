#include "mroi_c4.h"
#include "reader_tables.h"
void mroi_decode_map(const int8_t *map,mroi_point *out) {
    unsigned i,best=0,x,y,xx,yy;int top=-1,far=0;
    uint32_t total=0,sx=0,sy=0;
    for(i=0;i<4096;i++){int z=reader_sigmoid_q15[(int)map[i]+128];if(z>top){top=z;best=i;}}
    x=best%64;y=best/64;
    for(i=0;i<4096;i++) {
        int dx=(int)(i%64)-(int)x,dy=(int)(i/64)-(int)y;
        int z=reader_sigmoid_q15[(int)map[i]+128];
        if(dx*dx+dy*dy>25&&z>far)far=z;
    }
    for(yy=y?y-1:0;yy<=y+1&&yy<64;yy++)for(xx=x?x-1:0;xx<=x+1&&xx<64;xx++) {
        uint32_t w=reader_sigmoid_q15[(int)map[yy*64+xx]+128];
        total+=w;sx+=xx*w;sy+=yy*w;
    }
    /* Maximum sx*512 < 9*32767*63*512 overflowsU32. First compute Q8 heat
     * then double: numerator uses64-bit and is explicitly bounded. */
    {
        uint64_t nx=(uint64_t)sx*512u,ny=(uint64_t)sy*512u;
        uint32_t qx=total?(uint32_t)(nx/total):0,qy=total?(uint32_t)(ny/total):0;
        uint32_t rx=total?(uint32_t)(nx%total):0,ry=total?(uint32_t)(ny%total):0;
        qx+=(rx*2u>total)||(rx*2u==total&&(qx&1u));
        qy+=(ry*2u>total)||(ry*2u==total&&(qy&1u));
        out->x_q8=(int32_t)qx;out->y_q8=(int32_t)qy;
    }
    out->peak_q15=(uint16_t)top;
    out->margin_q15=(uint16_t)(top-far);
    out->valid=(uint8_t)(out->peak_q15>=9831u&&out->margin_q15>=656u);
}
