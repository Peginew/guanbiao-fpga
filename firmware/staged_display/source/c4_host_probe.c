#include "mroi_c4.h"
#include "hub_weights_q8.h"
#include "landmark_weights_q8.h"
#include <string.h>
int c4_probe_hub(const uint8_t *roi,int8_t *out,mroi_point *points) {
    unsigned i,k; mroi_c4_start(hub_layers);
    for(i=0;i<4096;i++){uint32_t w=0;for(k=0;k<4;k++)w|=(uint32_t)roi[4*i+k]<<(8*k);mroi_c4_feed(i,w);}
    if(!mroi_c4_compute(0,0))return 0;
    for(k=0;k<2;k++){const int8_t*map=mroi_c4_map(k);memcpy(out+4096*k,map,4096);mroi_decode_map(map,&points[k]);}
    return 1;
}
int c4_probe_landmark(const uint8_t *roi,int8_t *out,mroi_point *points) {
    unsigned i,k;mroi_c4_start(landmark_layers);
    for(i=0;i<4096;i++){uint32_t w=0;for(k=0;k<4;k++)w|=(uint32_t)roi[4*i+k]<<(8*k);mroi_c4_feed(i,w);}
    if(!mroi_c4_compute(0,0))return 0;
    for(k=0;k<6;k++){const int8_t*map=mroi_c4_map(k);memcpy(out+4096*k,map,4096);mroi_decode_map(map,&points[k]);}
    return 1;
}
