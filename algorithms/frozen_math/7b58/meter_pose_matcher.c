#include "meter_pose_matcher.h"
#include <string.h>

size_t mp_context_size(void) { return sizeof(mp_context); }
size_t mp_template_size(void) { return sizeof(mp_template); }
size_t mp_result_size(void) { return sizeof(mp_result); }

int mp_template_init(mp_template *out, const uint16_t *indices,
    const int8_t *values, uint16_t count, const int16_t *local_shift)
{
    uint16_t i;
    if (!out || !indices || !values || !local_shift || !count || count>MP_PROFILE_SIZE)
        return MP_BAD_ARGUMENT;
    for (i=0; i<count; ++i)
        if (indices[i]>=MP_PROFILE_SIZE) return MP_BAD_ARGUMENT;
    out->indices=indices; out->values=values;
    out->local_shift=local_shift; out->count=count;
    return MP_OK;
}

void mp_prepare(mp_context *ctx, uint8_t center_allowed)
{
    if (!ctx) return;
    memset(ctx,0,sizeof(*ctx));
    ctx->center_allowed=(uint8_t)(center_allowed!=0);
}

/* At most floor(0.8*4320)=3456 terms, each absolute error<=255.
 * A sum*keep product is <=255*3456^2=3045703680, fits uint32_t.
 * Strict comparison retains original first-winner semantics on exact ties.
 */
static int lower_mean(uint32_t sum, uint16_t keep, const mp_match *old)
{
    return !old->present || sum*(uint32_t)old->keep < old->sum*(uint32_t)keep;
}

int mp_push(mp_context *ctx, const int8_t *profile, uint16_t outside_count,
    uint8_t profile_id, const mp_template *templates, uint8_t template_count)
{
    uint8_t ti,si;
    if (!ctx || !profile || !templates || !template_count ||
        outside_count>MP_PROFILE_SIZE || profile_id==MP_NO_WINNER)
        return MP_BAD_ARGUMENT;
    if (!ctx->center_allowed) return MP_SKIPPED_CENTER;
    if (outside_count>216u) return MP_SKIPPED_OUTSIDE;
    for (ti=0; ti<template_count; ++ti) {
        const mp_template *t=&templates[ti];
        uint16_t keep;
        if (!t->indices || !t->values || !t->local_shift ||
            !t->count || t->count>MP_PROFILE_SIZE) return MP_BAD_ARGUMENT;
        keep=(uint16_t)(((uint32_t)t->count*4u)/5u);
        if (!keep) keep=1;
        for (si=0; si<MP_SHIFTS; ++si) {
            uint16_t j,remaining=keep;
            uint32_t sum=0;
            int shift=t->local_shift[si] % (int)MP_ANGLES;
            unsigned bin;
            if (shift<0) shift+=(int)MP_ANGLES;
            memset(ctx->histogram,0,sizeof(ctx->histogram));
            for (j=0; j<t->count; ++j) {
                unsigned index=t->indices[j];
                unsigned angular=index % MP_ANGLES;
                unsigned query_angular=angular+(unsigned)shift;
                int diff;
                if (query_angular>=MP_ANGLES) query_angular-=MP_ANGLES;
                /* np.roll(q,-local,axis=1)[row,angle] == q[row,angle+local]. */
                diff=(int)profile[index-angular+query_angular]-(int)t->values[j];
                if (diff<0) diff=-diff;
                ++ctx->histogram[(unsigned)diff];
            }
            /* Exact sum of the lowest keep terms, including a partial bin. */
            for (bin=0; bin<MP_ERROR_BINS && remaining; ++bin) {
                uint16_t take=ctx->histogram[bin];
                if (take>remaining) take=remaining;
                sum+=(uint32_t)bin*take;
                remaining=(uint16_t)(remaining-take);
            }
            if (lower_mean(sum,keep,&ctx->best[si])) {
                mp_match *b=&ctx->best[si];
                b->sum=sum; b->keep=keep; b->present=1;
                b->profile_id=profile_id; b->template_id=ti;
            }
        }
    }
    ++ctx->accepted_profiles;
    return MP_OK;
}

int mp_score_ge_064(uint32_t sum, uint16_t keep)
{
    /* 1 - mean_error/128 >= 0.64  <=>  25*sum <= 1152*keep. */
    if (!keep) return 0;
    return (uint64_t)25u*sum <= (uint64_t)1152u*keep;
}

int mp_margin_ge_0018(uint32_t best_sum, uint16_t best_keep,
    uint32_t far_sum, uint16_t far_keep)
{
    uint64_t far_cross,best_cross;
    if (!best_keep || !far_keep) return 0;
    far_cross=(uint64_t)far_sum*best_keep;
    best_cross=(uint64_t)best_sum*far_keep;
    if (far_cross<best_cross) return 0;
    /* (mean_far-mean_best)/128 >= .018; no fixed-score rounding. */
    return (uint64_t)125u*(far_cross-best_cross) >=
           (uint64_t)288u*best_keep*far_keep;
}

int mp_finish(const mp_context *ctx, mp_result *out)
{
    int best=-1,far=-1,i;
    const mp_match *b,*f;
    if (!ctx || !out) return MP_BAD_ARGUMENT;
    memset(out,0,sizeof(*out));
    out->profile_id=MP_NO_WINNER; out->template_id=MP_NO_WINNER;
    if (!ctx->center_allowed) { out->reason=MP_CENTER_REJECTED; return MP_OK; }
    for (i=0; i<(int)MP_SHIFTS; ++i) {
        const mp_match *m=&ctx->best[i];
        if (m->present && (best<0 || lower_mean(m->sum,m->keep,&ctx->best[best]))) best=i;
    }
    if (best<0) { out->reason=MP_NO_VALID_PROFILE; return MP_OK; }
    for (i=0; i<(int)MP_SHIFTS; ++i) {
        const mp_match *m=&ctx->best[i];
        int distance=i-best;
        if (distance<0) distance=-distance;
        if (distance>5 && m->present &&
            (far<0 || lower_mean(m->sum,m->keep,&ctx->best[far]))) far=i;
    }
    if (far<0) { out->reason=MP_NO_VALID_PROFILE; return MP_OK; }
    b=&ctx->best[best]; f=&ctx->best[far];
    out->best_sum=b->sum; out->best_keep=b->keep;
    out->far_sum=f->sum; out->far_keep=f->keep;
    out->margin_cross_numerator=f->sum*(uint32_t)b->keep-b->sum*(uint32_t)f->keep;
    out->margin_cross_denominator=(uint32_t)b->keep*f->keep;
    out->delta_deg=(int16_t)(best-24); out->far_delta_deg=(int16_t)(far-24);
    out->profile_id=b->profile_id; out->template_id=b->template_id;
    out->score_pass=(uint8_t)mp_score_ge_064(b->sum,b->keep);
    out->margin_pass=(uint8_t)mp_margin_ge_0018(b->sum,b->keep,f->sum,f->keep);
    out->search_interior_pass=(uint8_t)(best>0 && best<48);
    out->accepted=(uint8_t)(out->score_pass && out->margin_pass && out->search_interior_pass);
    out->reason=out->accepted ? MP_SUPPORTED : MP_AMBIGUOUS;
    return MP_OK;
}

int mp_get_shift(const mp_context *ctx, uint8_t shift_index, mp_match *out)
{
    if (!ctx || !out || shift_index>=MP_SHIFTS) return MP_BAD_ARGUMENT;
    *out=ctx->best[shift_index];
    return MP_OK;
}
