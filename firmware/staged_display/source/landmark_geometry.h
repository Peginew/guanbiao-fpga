#ifndef METER_LANDMARK_GEOMETRY_H
#define METER_LANDMARK_GEOMETRY_H
#include <stdint.h>
/* Six identities in frozen outer5/outer10/outer15/basket/soccer/stripe order.
 * Signed Q8 points are positions, not integer pixels. Angle is signed Q16deg.
 * No frame/pressure/visibility labels are inspected by these functions. */
typedef struct { int32_t x, y; } mlg_point_q8;
enum { MLG_OK=0, MLG_INSUFFICIENT=1, MLG_INCONSISTENT=2, MLG_AMBIGUOUS=3, MLG_ARGUMENT=4 };
typedef struct {
    int32_t roll_deg_q16;
    uint32_t sse_q16;
    uint8_t accepted, reason, inlier_mask, count;
} mlg_result;
/* Reference and query are already normalized to center64/radius48. */
int mlg_consensus_q8(const mlg_point_q8 ref[6], const mlg_point_q8 query[6],
    uint8_t known_mask, int32_t reference_roll_deg_q16, mlg_result *out);
/* Converts actual predicted ROI coordinates around the same predicted hub.
 * Radius is the actual locator radius in ROI pixels, Q8; never assume64. */
int mlg_normalize_q8(const mlg_point_q8 roi[6], mlg_point_q8 hub,
    uint32_t radius_q8, uint8_t mask, mlg_point_q8 normalized[6]);
int32_t mlg_atan2_deg_q16(int32_t y, int32_t x);
#endif
