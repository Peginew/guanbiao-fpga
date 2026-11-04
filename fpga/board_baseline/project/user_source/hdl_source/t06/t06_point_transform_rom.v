// Six exact2048x8 DPROMs: each color duplicates once to serve fourpixelports.
// Seven pointmodes share the same memory; no approximation or image downsampling.
module t06_point_transform_rom #(
 parameter R_FILE="C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_video20_mcu/project/user_source/hdl_source/t06/point_r.dath",
 parameter G_FILE="C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_video20_mcu/project/user_source/hdl_source/t06/point_g.dath",
 parameter B_FILE="C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_video20_mcu/project/user_source/hdl_source/t06/point_b.dath"
)(input clk,ce,input [4:0] md,input [95:0] rgb4,input [31:0] gray4,
 output [95:0] pixels);
 wire [2:0] table_mode=md-5'd4;
 wire use_gray=(md==9 || md==10);
 wire point_ce=ce && md>=4 && md<=10;
 genvar channel,pair;
 generate for(channel=0;channel<3;channel=channel+1)begin:g_channel
  for(pair=0;pair<2;pair=pair+1)begin:g_pair
   wire [7:0] a=use_gray?gray4[31-16*pair -:8]:rgb4[95-48*pair-8*channel -:8];
   wire [7:0] b=use_gray?gray4[23-16*pair -:8]:rgb4[71-48*pair-8*channel -:8];
   PH1P_LOGIC_ERAM #(
    .DATA_WIDTH_A(8),.DATA_WIDTH_B(8),.ADDR_WIDTH_A(11),.ADDR_WIDTH_B(11),
    .DATA_DEPTH_A(2048),.DATA_DEPTH_B(2048),.BYTE_ENABLE(0),.BYTE_A(1),.BYTE_B(1),
    .MODE("DP"),.REGMODE_A("NOREG"),.REGMODE_B("NOREG"),
    .WRITEMODE_A("NORMAL"),.WRITEMODE_B("READBEFOREWRITE"),
    .RESETMODE_A("ASYNC"),.RESETMODE_B("ASYNC"),.OREGSET_A("RESET"),.OREGSET_B("RESET"),
    .SSROVERCE("DISABLE"),.ECC_DECODE("DISABLE"),.ECC_ENCODE("DISABLE"),
    .ASYNC_RESET_RELEASE_A("ASYNC"),.ASYNC_RESET_RELEASE_B("ASYNC"),
    .CLKMODE("ASYNC"),.DEBUGGABLE("NO"),.PACKABLE("NO"),.FORCE_KEEP("ON"),
    .INIT_FILE(channel==0?R_FILE:channel==1?G_FILE:B_FILE),.FILL_ALL("NONE"),.IMPLEMENT("20K")
   ) rom(
    .doa(pixels[95-48*pair-8*channel -:8]),.dob(pixels[71-48*pair-8*channel -:8]),
    .ecc_sbiterr(),.ecc_dbiterr(),.dia(8'd0),.dib(8'd0),.ecc_sbiterrinj(1'b0),.ecc_dbiterrinj(1'b0),
    .cea(point_ce),.ocea(1'b0),.clka(clk),.wea(1'b0),.rsta(1'b0),
    .ceb(point_ce),.oceb(1'b0),.clkb(clk),.web(1'b0),.rstb(1'b0),
    .bea(1'b0),.beb(1'b0),.addra({table_mode,a}),.addrb({table_mode,b})
   );
  end
 end endgenerate
endmodule
