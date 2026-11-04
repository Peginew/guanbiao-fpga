// Known-gauge DEVELOPMENT readability veto, not a physical pose/focus estimator.
// Keep the weak localization threshold separate from this stricter reading gate.
// This module grants neither calibrated READ nor permission to move the rover.
module visual_readability_gate #(parameter CNN_ENABLE=0)(
 input wire identity_accepted,geometry_candidate,pixel_quality_ok,number_valid,
 input wire [7:0] printed_count,
 input wire [9:0] diameter,
 input wire signed [4:0] printed_roll,
 input wire [15:0] needle_score,
 input wire [5:0] needle_count,
 input wire cnn_valid,cnn_positive,
 output wire frontal_template_compatible,scale_window_ok,roll_window_ok,thin_detail_supported,
 output wire image_readability_candidate
);
 wire [10:0] hits_extended={5'd0,needle_count};
 wire [10:0] minimum_score=(hits_extended<<4)+(hits_extended<<3);
 assign frontal_template_compatible=printed_count>=160&&printed_count<=192;
 // CNN mode uses actual pointer evidence below, not native-diameter proxy.
 // Geometry-only legacy mode preserves its original scale test.
 assign scale_window_ok=CNN_ENABLE?1'b1:(diameter>=320&&diameter<=496);
 assign roll_window_ok=printed_roll>=-5'sd6&&printed_roll<=5'sd6;
 wire neural_detail=CNN_ENABLE&&cnn_valid&&cnn_positive;
 assign thin_detail_supported=CNN_ENABLE?neural_detail:(needle_count>=12&&needle_count<=32&&needle_score>={5'd0,minimum_score});
 assign image_readability_candidate=identity_accepted&&geometry_candidate&&pixel_quality_ok&&number_valid&&
   frontal_template_compatible&&scale_window_ok&&roll_window_ok&&thin_detail_supported;
endmodule
