// Native 128-square capture policy. Changes where to analyse, never grants READ.
// Old available stride3/4 windows remain bit-exact. Small targets use stride2;
// edge windows translate inside the real image. No padding/fake pixels added.
module meter_roi_window_policy(
 input wire [10:0] box_x0,box_x1,input wire [9:0] box_y0,box_y1,diameter,
 input wire partial_seen,
 output wire [10:0] crop_x,span,output wire [9:0] crop_y,
 output wire [2:0] stride,output wire [6:0] radius,
 output wire available,analysis_only
);
 assign stride=diameter<=236?3'd2:diameter<=372?3'd3:3'd4;
 assign span={1'b0,stride,7'd0};
 wire signed [12:0] raw_x4=($signed({2'd0,box_x0})+$signed({2'd0,box_x1})-$signed({2'd0,span}))>>>3;
 wire signed [12:0] raw_x=raw_x4<<<2;
 wire signed [12:0] raw_y=($signed({3'd0,box_y0})+$signed({3'd0,box_y1})-$signed({2'd0,span}))>>>1;
 wire [10:0] xmax=11'd1280-span,ymax=11'd720-span;
 assign crop_x=raw_x<0?11'd0:raw_x>$signed({2'd0,xmax})?xmax:raw_x[10:0];
 assign crop_y=raw_y<0?10'd0:raw_y>$signed({2'd0,ymax})?ymax[9:0]:raw_y[9:0];
 // Eleven-bit pre-add prevents D1020..1023 wrapping to zero.
 wire [10:0] rgeom=stride==2?({1'b0,diameter}+11'd2)>>2:
                            stride==3?({1'b0,diameter}+11'd3)/11'd6:
                                      ({1'b0,diameter}+11'd4)>>3;
 assign radius=rgeom>62?7'd62:rgeom[6:0];
 assign available=diameter>=160&&stride>=1&&stride<=4&&radius>=40&&radius<=62&&
                  crop_x[1:0]==0&&{1'b0,crop_x}+span<=1280&&{2'd0,crop_y}+span<=720;
 wire image_contains=box_x0<=box_x1&&box_y0<=box_y1&&box_x1<=1280&&box_y1<=720;
 wire crop_contains=box_x0>=crop_x&&box_y0>=crop_y&&{1'b0,box_x1}<={1'b0,crop_x}+span&&
                    {2'd0,box_y1}<={2'd0,crop_y}+span;
 assign analysis_only=diameter>499||partial_seen||!image_contains||!crop_contains;
endmodule
