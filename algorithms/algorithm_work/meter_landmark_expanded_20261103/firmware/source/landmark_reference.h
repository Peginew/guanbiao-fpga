#ifndef METER_LANDMARK_REFERENCE_H
#define METER_LANDMARK_REFERENCE_H
#include "landmark_geometry.h"
static const mlg_point_q8 mlg_reference_q8[6] = {
    {7913, 15370}, /* outer_psi_5_text_centroid */
    {14798, 7886}, /* outer_psi_10_text_centroid */
    {24028, 11728}, /* outer_psi_15_text_centroid */
    {16195, 13824}, /* upper_basketball_logo_centroid */
    {17043, 19112}, /* middle_soccer_logo_centroid */
    {17343, 21607}, /* lower_striped_ball_print_centroid */
};
#define MLG_REFERENCE_ROLL_Q16 (-156202)
#endif
