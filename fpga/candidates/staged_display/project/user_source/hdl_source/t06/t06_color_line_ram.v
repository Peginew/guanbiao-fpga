// Exact rotatingRGB333 line memory, sameCSIclock and sameoneedge read latency.
// Pseudo-dualport wide mode uses the physicalPDP20K 40bit configuration.
// BothinitialDP andSP attempts stillused2ERAM/bank. The installed official
// RAMF9F0D0P0/RAM/RTL/ram.v defines SDP_RAM via MODE("PDPW").
// OnlyA writes, onlyB reads; CE is parentadvance, frozenonstall.
// PDPW permits NORMAL only. The writebank's simultaneousread is notobserved:
// parenttop_color1 alwaysselects a differentrotatingrowbank at the matchingedge.
module t06_color_line_ram #(
 parameter WORDS=320,
 parameter AW=(WORDS<=2)?1:$clog2(WORDS),
 parameter DEPTH=1<<AW
)(input clk,ce,we,input [AW-1:0] address,input [35:0] din,output [35:0] dout);
 PH1P_LOGIC_ERAM #(
  .DATA_WIDTH_A(36),.DATA_WIDTH_B(36),.ADDR_WIDTH_A(AW),.ADDR_WIDTH_B(AW),
  .DATA_DEPTH_A(DEPTH),.DATA_DEPTH_B(DEPTH),.BYTE_ENABLE(0),.BYTE_A(1),.BYTE_B(1),
  .MODE("PDPW"),.REGMODE_A("NOREG"),.REGMODE_B("NOREG"),
  .WRITEMODE_A("NORMAL"),.WRITEMODE_B("NORMAL"),
  .RESETMODE_A("ASYNC"),.RESETMODE_B("ASYNC"),.OREGSET_A("RESET"),.OREGSET_B("RESET"),
  .SSROVERCE("DISABLE"),.ECC_DECODE("DISABLE"),.ECC_ENCODE("DISABLE"),
  .ASYNC_RESET_RELEASE_A("ASYNC"),.ASYNC_RESET_RELEASE_B("ASYNC"),
  .CLKMODE("ASYNC"),.DEBUGGABLE("NO"),.PACKABLE("NO"),.FORCE_KEEP("ON"),
  .INIT_FILE("NONE"),.FILL_ALL("NONE"),.IMPLEMENT("20K")
 ) ram(
  .doa(),.dob(dout),.ecc_sbiterr(),.ecc_dbiterr(),
  .dia(din),.dib(36'd0),.ecc_sbiterrinj(1'b0),.ecc_dbiterrinj(1'b0),
  .cea(ce),.ocea(1'b0),.clka(clk),.wea(we),.rsta(1'b0),
  .ceb(ce),.oceb(1'b0),.clkb(clk),.web(1'b0),.rstb(1'b0),
  .bea(1'b0),.beb(1'b0),.addra(address),.addrb(address)
 );
endmodule
