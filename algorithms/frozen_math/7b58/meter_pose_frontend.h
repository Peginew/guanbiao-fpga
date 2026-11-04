#ifndef METER_POSE_FRONTEND_H
#define METER_POSE_FRONTEND_H

#include <stddef.h>
#include <stdint.h>
#if defined(_WIN32)
#define MPF_API __declspec(dllexport)
#else
#define MPF_API
#endif

#define MPF_WIDTH 128u
#define MPF_HEIGHT 128u
#define MPF_PIXELS (MPF_WIDTH*MPF_HEIGHT)
#define MPF_BANDS 12u
#define MPF_ANGLES 360u
#define MPF_SAMPLES (MPF_BANDS*MPF_ANGLES)

typedef struct {
    uint8_t source_rows[9u*MPF_WIDTH];
    uint16_t vertical_sums[MPF_WIDTH];
} mpf_normalize_workspace;

typedef struct { uint8_t sampled_row[MPF_ANGLES]; } mpf_profile_workspace;

MPF_API size_t mpf_normalize_workspace_size(void);
MPF_API size_t mpf_profile_workspace_size(void);

/* Raw128x128U8 -> normalized128x128U8. Exact same source/destination pointer
 * is supported; partial overlaps are not supported. Workspace is caller-owned.
 * replicate9x9 mean=(sum+40)/81, then satU8(3*(pixel-mean)+128).
 */
MPF_API int mpf_normalize9x9_u8(const uint8_t *source, uint8_t *normalized,
    mpf_normalize_workspace *work);

/* Q5coordinates are SIGNED integers; x0=floor(xq/32), including negatives.
 * 4neighbour constant border128, U8result=(weighted_sum+512)>>10.
 * Coordinate generation, hub/radius and outside_count are NOT implemented.
 * In particular original float64 prequantization outside_count must be
 * supplied separately to the matcher; it cannot be recovered fromQ5.
 */
MPF_API int mpf_bilinear_q5_u8(const uint8_t *normalized,
    const int16_t *xq, const int16_t *yq, uint16_t count, uint8_t *sampled);

/* Exactly12rows of360samples: d=360*u-sum(row), A=sum(abs(d));
 * RNE-even(d*11520/max(A,777600)), sat[-127,127]. S32 intermediates suffice.
 * Exact same sampled/output storage is supported, interpreted as S8 onexit.
 */
MPF_API int mpf_normalize_profile_s8(const uint8_t *sampled, int8_t *profile);

/* Fused sampler+profile normalizer uses only360B temporary samples. The
 * normalized image, x/y tables and destination profile remain caller-owned.
 */
MPF_API int mpf_profile_q5_s8(const uint8_t *normalized,
    const int16_t *xq, const int16_t *yq, int8_t *profile,
    mpf_profile_workspace *work);

#endif
