// Exact4096x5 ROM: address={mode5,charindex4,glyphrow3}; low5bits are5x7 glyphrow.
module t06_mode_glyph_rom #(
 parameter INIT_FILE="C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_video20_mcu/project/user_source/hdl_source/t06/mode_glyph.dath"
)(input clk,ce,input [11:0] address,output [4:0] row_bits);
 PH1P_LOGIC_ERAM #(
  .DATA_WIDTH_A(5),.DATA_WIDTH_B(5),.ADDR_WIDTH_A(12),.ADDR_WIDTH_B(12),
  .DATA_DEPTH_A(4096),.DATA_DEPTH_B(4096),.BYTE_ENABLE(0),.BYTE_A(1),.BYTE_B(1),
  .MODE("SP"),.REGMODE_A("NOREG"),.REGMODE_B("NOREG"),
  .WRITEMODE_A("NORMAL"),.WRITEMODE_B("READBEFOREWRITE"),
  .RESETMODE_A("ASYNC"),.RESETMODE_B("ASYNC"),.OREGSET_A("RESET"),.OREGSET_B("RESET"),
  .SSROVERCE("DISABLE"),.ECC_DECODE("DISABLE"),.ECC_ENCODE("DISABLE"),
  .ASYNC_RESET_RELEASE_A("ASYNC"),.ASYNC_RESET_RELEASE_B("ASYNC"),
  .CLKMODE("ASYNC"),.DEBUGGABLE("NO"),.PACKABLE("NO"),.FORCE_KEEP("ON"),
  .INIT_FILE(INIT_FILE),.FILL_ALL("NONE"),.IMPLEMENT("20K")
 ) rom(
  .doa(row_bits),.dob(),.ecc_sbiterr(),.ecc_dbiterr(),
  .dia(5'd0),.dib(5'd0),.ecc_sbiterrinj(1'b0),.ecc_dbiterrinj(1'b0),
  .cea(ce),.ocea(1'b0),.clka(clk),.wea(1'b0),.rsta(1'b0),
  .ceb(1'b0),.oceb(1'b0),.clkb(1'b0),.web(1'b0),.rstb(1'b0),
  .bea(1'b0),.beb(1'b0),.addra(address),.addrb(12'd0)
 );
endmodule
