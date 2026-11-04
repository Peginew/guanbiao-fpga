#ifndef READER_NUMERIC_H
#define READER_NUMERIC_H
#include <stdint.h>
#include "meter_pose_matcher.h"
/* Gray remains borrowed/owned until all sequential stages finish. Numeric
 * functions reuse the dead C4 A/B arena; no extra16KiB ROI is allocated. */
typedef struct { int32_t angle_q16; uint16_t peak_q15,margin_q15,outside; uint8_t valid; } reader_needle;
int reader_polar(const uint8_t *gray,int32_t hx_q8,int32_t hy_q8,unsigned radius,
    reader_needle *out,int (*permit)(void *),void *context);
int reader_ring(uint8_t *gray,int32_t hx_q8,int32_t hy_q8,unsigned radius,
    mp_result *out,int (*permit)(void *),void *context);
int reader_calibrate_psi_q8(int32_t image_angle_q16,int32_t roll_q16,uint16_t *psi_q8);
enum { READER_CAL_DOMAIN_OLD=0, READER_CAL_DOMAIN_TRAIN_CORRECTED=1 };
int reader_calibrate_psi_q8_domain(int32_t image_angle_q16,int32_t roll_q16,int domain,uint16_t *psi_q8);
#endif
