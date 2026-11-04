#include "landmark_geometry.h"
#include <string.h>
#define Q 256L
#define ONE 65536L
typedef struct {
    int32_t a,b,tx,ty,angle;
    uint32_t sse;
    uint8_t mask,n;
} fit;
static unsigned bits(uint8_t x){unsigned n=0;for(;x;x>>=1)n+=x&1u;return n;}
static int32_t wrap(int32_t a){while(a>=180L*ONE)a-=360L*ONE;while(a< -180L*ONE)a+=360L*ONE;return a;}
static int64_t rounded_div(int64_t n,int64_t d){return n>=0?(n+d/2)/d:-((-n+d/2)/d);}
static uint32_t root32(uint32_t x){uint32_t r=0,b=1u<<30;while(b>x)b>>=2;while(b){if(x>=r+b){x-=r+b;r=(r>>1)+b;}else r>>=1;b>>=2;}return r;}
int32_t mlg_atan2_deg_q16(int32_t iy,int32_t ix){
    static const int32_t angles[20]={2949120,1740967,919879,466945,234379,117304,58666,29335,14668,7334,3667,1833,917,458,229,115,57,29,14,7};
    int64_t x=ix,y=iy;int32_t a=0;unsigned k;
    if(!x&&!y)return 0;
    if(x<0){a=y>=0?180L*ONE:-180L*ONE;x=-x;y=-y;}
    /* Left-shift by multiplication avoids signed-left-shift UB. */
    x*=1048576;y*=1048576;
    for(k=0;k<20;++k){int64_t px=x;if(y>0){x+=y>>k;y-=px>>k;a+=angles[k];}else if(y<0){x-=y>>k;y+=px>>k;a-=angles[k];}}
    return wrap(a);
}
static mlg_point_q8 project(const fit *f,mlg_point_q8 p){
    mlg_point_q8 r;r.x=(int32_t)rounded_div((int64_t)f->a*p.x-(int64_t)f->b*p.y,ONE)+f->tx;
    r.y=(int32_t)rounded_div((int64_t)f->b*p.x+(int64_t)f->a*p.y,ONE)+f->ty;return r;
}
static uint64_t dist2(mlg_point_q8 a,mlg_point_q8 b){int64_t x=(int64_t)a.x-b.x,y=(int64_t)a.y-b.y;return(uint64_t)(x*x+y*y);}
static int solve(const mlg_point_q8 x[6],const mlg_point_q8 y[6],uint8_t mask,fit *f){
    int64_t sx=0,sy=0,su=0,sv=0,d=0,na=0,nb=0;unsigned i,n=bits(mask);
    if(n<2)return 0;
    for(i=0;i<6;i++)if(mask&(1u<<i)){sx+=x[i].x;sy+=x[i].y;su+=y[i].x;sv+=y[i].y;
        d+=(int64_t)x[i].x*x[i].x+(int64_t)x[i].y*x[i].y;
        na+=(int64_t)x[i].x*y[i].x+(int64_t)x[i].y*y[i].y;
        nb+=(int64_t)x[i].x*y[i].y-(int64_t)x[i].y*y[i].x;}
    d=d*n-sx*sx-sy*sy;if(d<=0)return 0;
    na=na*n-sx*su-sy*sv;nb=nb*n-sx*sv+sy*su;
    f->a=(int32_t)rounded_div(na*ONE,d);f->b=(int32_t)rounded_div(nb*ONE,d);
    f->tx=(int32_t)rounded_div(su*ONE-(int64_t)f->a*sx+(int64_t)f->b*sy,n*ONE);
    f->ty=(int32_t)rounded_div(sv*ONE-(int64_t)f->b*sx-(int64_t)f->a*sy,n*ONE);
    f->mask=mask;f->n=(uint8_t)n;f->sse=0;
    for(i=0;i<6;i++)if(mask&(1u<<i)){uint64_t e=dist2(project(f,x[i]),y[i]);if(e>UINT32_MAX-f->sse)return 0;f->sse+=(uint32_t)e;}
    f->angle=mlg_atan2_deg_q16(f->b,f->a);return 1;
}
static uint8_t inliers(const fit*f,const mlg_point_q8 x[6],const mlg_point_q8 y[6],uint8_t known){
    uint8_t m=0;unsigned i;for(i=0;i<6;i++)if((known&(1u<<i))&&dist2(project(f,x[i]),y[i])<=640u*640u)m|=(uint8_t)(1u<<i);return m;
}
static int acceptable(fit*f,const mlg_point_q8 x[6],const mlg_point_q8 y[6],int32_t offset){
    uint64_t scale=(int64_t)f->a*f->a+(int64_t)f->b*f->b,span=0,refspan=0;unsigned i,j;
    mlg_point_q8 c={64*Q,64*Q};int32_t roll=wrap(f->angle+offset);
    if(scale<UINT64_C(3103113871)||scale>UINT64_C(5680094249))return 0;
    if(roll<=-24L*ONE||roll>=24L*ONE)return 0;
    if(dist2(project(f,c),c)>UINT64_C(5120)*5120)return 0;
    if(f->sse>f->n*512u*512u)return 0;
    for(i=0;i<6;i++)if(f->mask&(1u<<i)){
        if(dist2(project(f,x[i]),y[i])>640u*640u)return 0;
        for(j=i+1;j<6;j++)if(f->mask&(1u<<j)){
            uint64_t qd=dist2(y[i],y[j]),rd=dist2(x[i],x[j]);
            if(qd<2048u*2048u)return 0;
            if(qd>span)span=qd;
            if(rd>refspan)refspan=rd;
        }
    }
    return span>=UINT64_C(7680)*7680&&refspan>=UINT64_C(7680)*7680;
}
int mlg_consensus_q8(const mlg_point_q8 ref[6],const mlg_point_q8 query[6],uint8_t known,int32_t offset,mlg_result*out){
    fit candidates[15],f;unsigned i,j,k,nc=0,best=0;
    if(!out||!ref||!query)return MLG_ARGUMENT;
    memset(out,0,sizeof(*out));known&=63u;out->reason=MLG_INSUFFICIENT;
    if(bits(known)<3)return out->reason;
    out->reason=MLG_INCONSISTENT;
    for(i=0;i<6;i++)if(known&(1u<<i))for(j=i+1;j<6;j++)if(known&(1u<<j)){
        uint8_t m=(uint8_t)((1u<<i)|(1u<<j));int duplicate=0;
        if(dist2(ref[i],ref[j])<UINT64_C(7680)*7680||dist2(query[i],query[j])<UINT64_C(7680)*7680)continue;
        if(!solve(ref,query,m,&f))continue;
        m=inliers(&f,ref,query,known);
        for(k=0;k<2&&bits(m)>=3;k++){if(!solve(ref,query,m,&f)){m=0;break;}m=inliers(&f,ref,query,known);}
        if(bits(m)<3||!solve(ref,query,m,&f)||!acceptable(&f,ref,query,offset))continue;
        for(k=0;k<nc;k++)if(candidates[k].mask==m)duplicate=1;
        if(!duplicate)candidates[nc++]=f;
    }
    if(!nc)return out->reason;
    for(k=1;k<nc;k++){
        fit*a=&candidates[k],*b=&candidates[best];
        if(a->n>b->n||(a->n==b->n&&((uint64_t)a->sse*b->n<(uint64_t)b->sse*a->n)))best=k;
    }
    f=candidates[best];
    for(k=0;k<nc;k++)if(k!=best&&candidates[k].n>=f.n){
        int32_t da=wrap(candidates[k].angle-f.angle);uint32_t rms=root32(f.sse/f.n)+128u;
        if((da>5L*ONE||da< -5L*ONE)&&candidates[k].sse<=(uint64_t)rms*rms*candidates[k].n){out->reason=MLG_AMBIGUOUS;return out->reason;}
    }
    out->accepted=1;out->reason=MLG_OK;out->roll_deg_q16=wrap(f.angle+offset);out->inlier_mask=f.mask;out->count=f.n;out->sse_q16=f.sse;
    return MLG_OK;
}
int mlg_normalize_q8(const mlg_point_q8 roi[6],mlg_point_q8 hub,uint32_t radius,uint8_t mask,mlg_point_q8 out[6]){
    unsigned i;if(!roi||!out||radius<256u||radius>32768u)return MLG_ARGUMENT;
    for(i=0;i<6;i++){out[i].x=out[i].y=0;if(mask&(1u<<i)){
        out[i].x=64*Q+(int32_t)rounded_div(((int64_t)roi[i].x-hub.x)*48*Q,radius);
        out[i].y=64*Q+(int32_t)rounded_div(((int64_t)roi[i].y-hub.y)*48*Q,radius);
    }}return MLG_OK;
}
