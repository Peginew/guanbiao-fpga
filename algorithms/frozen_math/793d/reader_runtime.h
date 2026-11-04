#ifndef METER_READER_RUNTIME_H
#define METER_READER_RUNTIME_H
#include "mroi_client.h"
#include "mroi_c4.h"
#include "reader_numeric.h"
#include "landmark_geometry.h"
#define MROI_FEATURES 0x064u
#define MROI_FEATURE_PSI_Q8_V1 1u
#define MROI_RETURN_PSI_Q8 0x124u
#define MROI_PSI_VALID 0x80000000u
typedef struct {
    uint32_t active,phase,words,completed,cancelled;
    uint32_t epoch,source,job,radius,return_code,psi_word;
    mroi_point hub,landmark[6];
    reader_needle needle;
    mp_result ring;
    mlg_result print;
    uint32_t neural_valid,reference_valid,reference_kind,read_valid;
    int32_t selected_roll_q16;
    uint32_t stage_cycles[5];
} mroi_reader_diagnostics;
extern volatile mroi_reader_diagnostics mroi_reader_diag;
extern const mroi_consumer mroi_reader_stage;
void mroi_reader_bind(const mroi_io *io);
uint32_t mroi_reader_psi_word(void);
#ifdef MROI_HOST_TEST
int mroi_reader_host_infer(const uint8_t *roi,unsigned radius,mroi_reader_diagnostics *out);
uint32_t mroi_reader_diagnostic_size(void);
#endif
#endif
