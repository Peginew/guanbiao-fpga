#ifndef METER_POSE_MATCHER_H
#define METER_POSE_MATCHER_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
#define MP_API __declspec(dllexport)
#else
#define MP_API
#endif

#define MP_BANDS 12u
#define MP_ANGLES 360u
#define MP_PROFILE_SIZE (MP_BANDS * MP_ANGLES)
#define MP_SHIFTS 49u
#define MP_ERROR_BINS 256u
#define MP_NO_WINNER 255u

enum mp_reason { MP_SUPPORTED=0, MP_CENTER_REJECTED=1,
                 MP_NO_VALID_PROFILE=2, MP_AMBIGUOUS=3 };
enum mp_return { MP_OK=0, MP_SKIPPED_OUTSIDE=1, MP_SKIPPED_CENTER=2,
                 MP_BAD_ARGUMENT=-1 };

/* Borrowed arrays must remain alive until all pushes have completed.
 * indices are flattened 12x360 locations; values and local_shift originate
 * from frozen TRAIN templates. local_shift[i] is Python round(delta-offset)
 * for canonical delta=-24+i, not a C rounding of an offset.
 */
typedef struct {
    const uint16_t *indices;
    const int8_t *values;
    const int16_t *local_shift;
    uint16_t count;
} mp_template;

typedef struct {
    uint32_t sum;
    uint16_t keep;
    uint8_t profile_id;
    uint8_t template_id;
    uint8_t present;
} mp_match;

/* Caller may place this approximately1KiB context in reusable scratch.
 * Query profile and TRAIN templates are external, not copied into context.
 */
typedef struct {
    mp_match best[MP_SHIFTS];
    uint16_t histogram[MP_ERROR_BINS];
    uint16_t accepted_profiles;
    uint8_t center_allowed;
} mp_context;

typedef struct {
    uint32_t best_sum;
    uint32_t far_sum;
    uint32_t margin_cross_numerator;
    uint32_t margin_cross_denominator;
    uint16_t best_keep;
    uint16_t far_keep;
    int16_t delta_deg;
    int16_t far_delta_deg;
    uint8_t profile_id;
    uint8_t template_id;
    uint8_t accepted;
    uint8_t score_pass;
    uint8_t margin_pass;
    uint8_t search_interior_pass;
    uint8_t reason;
} mp_result;

MP_API size_t mp_context_size(void);
MP_API size_t mp_template_size(void);
MP_API size_t mp_result_size(void);
MP_API int mp_template_init(mp_template *out, const uint16_t *indices,
    const int8_t *values, uint16_t count, const int16_t *local_shift);
/* center_allowed is the frontend's SAME hub distance<=14 predicate. It is
 * not user permission to bypass the center test. Matcher has no hub floats.
 */
MP_API void mp_prepare(mp_context *ctx, uint8_t center_allowed);
/* Push in original dx/dy/scale iteration order, templates in original order.
 * outside_count is from4320 polar source coordinates. >216 means>0.05.
 * All exact score ties preserve the first profile/template encountered.
 */
MP_API int mp_push(mp_context *ctx, const int8_t *profile, uint16_t outside_count,
    uint8_t profile_id, const mp_template *templates, uint8_t template_count);
MP_API int mp_finish(const mp_context *ctx, mp_result *out);
MP_API int mp_get_shift(const mp_context *ctx, uint8_t shift_index, mp_match *out);
/* Exposed exact-rational decisions for host boundary tests. */
MP_API int mp_score_ge_064(uint32_t sum, uint16_t keep);
MP_API int mp_margin_ge_0018(uint32_t best_sum, uint16_t best_keep,
    uint32_t far_sum, uint16_t far_keep);

#endif
