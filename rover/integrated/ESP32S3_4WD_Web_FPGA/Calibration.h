#pragma once
// Field calibration R1, same floor/load, target speed 40mm/s.
// Preliminary only: remeasure after flashing; this is not a precision certificate.
namespace FieldCalibration {
constexpr char VERSION[] = "S3-4WD-CAL-R1-20261019";
constexpr float DISTANCE_SCALE = 0.70f; // 100->70mm and 300->210mm (3 runs)
constexpr float MEAN_TURN_ACTUAL_DEG = 40.333333f; // 4 positive + 5 negative trial magnitudes
constexpr float TURN_COMMAND_DEG = 90.0f;
// Old effective track180, account for the SAME distance-scale correction here.
// Without DISTANCE_SCALE here, turn compensation would be applied twice.
constexpr float EFFECTIVE_TRACK_MM = 180.0f * DISTANCE_SCALE * TURN_COMMAND_DEG / MEAN_TURN_ACTUAL_DEG;
static_assert(DISTANCE_SCALE > 0 && DISTANCE_SCALE <= 2, "invalid distance scale");
static_assert(EFFECTIVE_TRACK_MM > 0, "invalid effective track");
}
