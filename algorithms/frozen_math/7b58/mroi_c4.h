#ifndef MROI_C4_H
#define MROI_C4_H
#include <stdint.h>
#ifndef MROI_NN_LAYER_TYPE_DEFINED
#define MROI_NN_LAYER_TYPE_DEFINED
typedef struct { const int8_t *w; const int32_t *b; uint8_t ci,co,k,stride,dw,relu; int8_t shift; } mroi_nn_layer;
#endif
/* A+B share storage with the later raw/normalized ROI and polar/ring stages.
 * No stage is reentrant. Raw ROI ownership remains with the AHB bridge. */
extern int8_t mroi_arena[32768];
void mroi_c4_start(const mroi_nn_layer *model);
void mroi_c4_feed(unsigned word_index,uint32_t word);
int mroi_c4_compute(int (*permit)(void *),void *context);
const int8_t *mroi_c4_map(unsigned head);
int8_t mroi_requant(int32_t value,int shift,int relu);
typedef struct { int32_t x_q8,y_q8; uint16_t peak_q15,margin_q15; uint8_t valid; } mroi_point;
void mroi_decode_map(const int8_t *map,mroi_point *out);
#endif
