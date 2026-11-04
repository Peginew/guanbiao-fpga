// Finite image-direction indication, not a measured physical needle endpoint.
// Metadata-only synchronous ROM/extent preparation; no pixel register or CDC.
module t06_meter_direction_line #(
 parameter TRIG_FILE="C:/Users/Edward/Desktop/FPGA/Stable3s_Rover_Merged_20261104/fpga/project/user_source/hdl_source/meter_pair/needle_trig128.hex"
)(
 input wire clk,rst_n,load,invalidate,load_valid,
 input wire [8:0] load_angle,load_radius,angle,
 input wire enable,
 input wire [10:0] pixel_x,pixel_y,hub_x,hub_y,
 input wire [10:0] box_x0,box_y0,box_x1,box_y1,
 output wire needle_ink
);
 reg [23:0] trig[0:511]; // synthesis ram_style=bram
 reg [23:0] coeff;
 initial $readmemh(TRIG_FILE,trig,0,359);
 // +1024 and -1024 both require signed12; table packs cos then sin.
 always @(posedge clk)
  if(rst_n&&load&&load_valid&&load_angle<360&&load_radius!=0)
   coeff<=trig[load_angle];
 wire signed [11:0] cs=coeff[23:12],sn=coeff[11:0];
 wire [10:0] abs_cs=cs[11]?-cs:cs,abs_sn=sn[11]?-sn:sn;
 wire major_x=abs_cs>=abs_sn;
 wire [10:0] major_unit=major_x?abs_cs:abs_sn;
 reg pending,ready;
 reg [8:0] radius_pending,angle_pending,angle_tag;
 reg [9:0] major_extent;
 // The third multiplier is metadata-only, sampled after synchronous ROM read.
 wire [19:0] radius_product=radius_pending*major_unit;
 wire [19:0] rounded_product=radius_product+20'd512;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   pending<=0;ready<=0;radius_pending<=0;angle_pending<=0;angle_tag<=0;major_extent<=0;
  end else if(invalidate)begin pending<=0;ready<=0;end
  else if(load)begin
   ready<=0;
   pending<=load_valid&&load_angle<360&&load_radius!=0;
   radius_pending<=load_radius;angle_pending<=load_angle;
  end else if(pending)begin
   major_extent<=rounded_product[19:10];angle_tag<=angle_pending;
   pending<=0;ready<=1;
  end
 end
 wire signed [11:0] dx=$signed({1'b0,pixel_x})-$signed({1'b0,hub_x});
 wire signed [11:0] dy=$signed({1'b0,pixel_y})-$signed({1'b0,hub_y});
 // Explicit signed24 products/subtraction cover the full native viewport.
 wire signed [23:0] dx_sin=dx*sn,dy_cos=dy*cs;
 wire signed [23:0] cross_product=dx_sin-dy_cos;
 wire [23:0] abs_cross=cross_product[23]?-cross_product:cross_product;
 wire signed [11:0] q=major_x?(cs[11]?-dx:dx):(sn[11]?-dy:dy);
 wire box_valid=box_x0<box_x1&&box_y0<box_y1&&box_x1<=1280&&box_y1<=720;
 wire hub_in_box=hub_x>=box_x0&&hub_x<box_x1&&hub_y>=box_y0&&hub_y<box_y1;
 assign needle_ink=enable&&!invalidate&&ready&&angle==angle_tag&&angle<360&&box_valid&&hub_in_box&&
  pixel_x<1280&&pixel_y<720&&pixel_x>=box_x0&&pixel_x<box_x1&&pixel_y>=box_y0&&pixel_y<box_y1&&
  !q[11]&&q[10:0]<={1'b0,major_extent}&&abs_cross<=24'd1024;
endmodule
