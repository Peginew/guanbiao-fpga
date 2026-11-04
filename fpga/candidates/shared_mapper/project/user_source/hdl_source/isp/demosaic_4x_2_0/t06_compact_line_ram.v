// Same installed PH1P ERAM primitive and DP/NOREG/collision settings as the
// generated 2048-word memories. Only unreachable address capacity is removed.
// At WIDTH1280, callers cycle exclusively0..319: AW9/512words. No new clock,
// reset, enable, latency, pixel transform, or valid-control logic is introduced.
module t06_compact_line_ram #(
 parameter DATA_WIDTH=33,WORDS=320,
 parameter AW=(WORDS<=2)?1:$clog2(WORDS),
 parameter DEPTH=(1<<AW)
)(
 input clka,wea,input [10:0] addra,input [DATA_WIDTH-1:0] dia,
 input clkb,web,input [10:0] addrb,input [DATA_WIDTH-1:0] dib,
 output [DATA_WIDTH-1:0] doa,dob
);
 PH1P_LOGIC_ERAM #(
  .DATA_WIDTH_A(DATA_WIDTH),.DATA_WIDTH_B(DATA_WIDTH),
  .ADDR_WIDTH_A(AW),.ADDR_WIDTH_B(AW),.DATA_DEPTH_A(DEPTH),.DATA_DEPTH_B(DEPTH),
  .MODE("DP"),.REGMODE_A("NOREG"),.REGMODE_B("NOREG"),
  .WRITEMODE_A("NORMAL"),.WRITEMODE_B("READBEFOREWRITE"),
  .IMPLEMENT("20K(FAST)"),.ECC_ENCODE("DISABLE"),.ECC_DECODE("DISABLE"),
  .CLKMODE("ASYNC"),.SSROVERCE("DISABLE"),.OREGSET_A("RESET"),.OREGSET_B("RESET"),
  .RESETMODE_A("ASYNC"),.RESETMODE_B("ASYNC"),
  .ASYNC_RESET_RELEASE_A("ASYNC"),.ASYNC_RESET_RELEASE_B("ASYNC"),
  .INIT_FILE("NONE"),.FILL_ALL("NONE")
 ) ram(
  .dia(dia),.dib(dib),.addra(addra[AW-1:0]),.addrb(addrb[AW-1:0]),
  .clka(clka),.clkb(clkb),.wea(wea),.web(web),
  .cea(1'b1),.ceb(1'b1),.ocea(1'b0),.oceb(1'b0),
  .bea(1'b0),.beb(1'b0),.rsta(1'b0),.rstb(1'b0),
  .doa(doa),.dob(dob),.ecc_sbiterr(),.ecc_dbiterr(),
  .ecc_sbiterrinj(1'b0),.ecc_dbiterrinj(1'b0)
 );
endmodule
