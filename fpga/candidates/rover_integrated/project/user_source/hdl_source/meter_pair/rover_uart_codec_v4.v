`timescale 1ns/1ps
// Explicit protocol V4, fixed32 bytes: SYNC2 + body28 + CRC2.
// RX is one224-bit compact body register, consumed only at frame_valid; there
// is no second body snapshot. TX retains the proven single-ERAM atomic bank.
// This codec does not imply V1, V2 or V3 wire compatibility.
module rover_uart_codec_v4(
 input wire clk,rst_n,input wire [31:0] now_ms,
 input wire [7:0] rx_byte,input wire rx_valid,rx_error,
 output reg [223:0] rx_body,
 output reg frame_valid,frame_error,
 input wire [31:0] tx_word,output reg [2:0] capture_index,
 input wire frame_send,output wire frame_ready,
 output reg capture_busy,capture_done,
 output wire [7:0] tx_byte,output wire tx_valid,input wire tx_ready
);
 function [15:0] crc_byte;
  input [15:0] previous;input [7:0] data;reg [15:0] c;integer b;
  begin c=previous^{data,8'd0};for(b=0;b<8;b=b+1)c=c[15]?(c<<1)^16'h1021:c<<1;crc_byte=c;end
 endfunction
 reg [4:0] used;reg [15:0] rcrc;reg [7:0] crc_low;
 reg [4:0] last_byte_ms;
 wire [4:0] byte_age=now_ms[4:0]-last_byte_ms;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin used<=0;rcrc<=16'hffff;crc_low<=0;last_byte_ms<=0;frame_valid<=0;frame_error<=0;end
  else begin
   frame_valid<=0;frame_error<=0;
   if(used!=0&&byte_age>=20)begin used<=0;frame_error<=1;end
   if(rx_error)begin used<=0;frame_error<=1;end
   else if(rx_valid)begin
    last_byte_ms<=now_ms[4:0];
    if(used==0||byte_age>=20)begin
     if(rx_byte==8'ha5)begin used<=1;rcrc<=16'hffff;end else used<=0;
    end else if(used==1)begin
     if(rx_byte==8'h5a)begin used<=2;rcrc<=16'hffff;end
     else if(rx_byte!=8'ha5)used<=0;
    end else if(used<30)begin
     rcrc<=crc_byte(rcrc,rx_byte);used<=used+1'b1;
     rx_body<={rx_byte,rx_body[223:8]};
    end else if(used==30)begin crc_low<=rx_byte;used<=31;end
    else begin
     used<=0;
     if({rx_byte,crc_low}==rcrc&&rx_body[7:0]==8'd4&&rx_body[15:8]>=1&&rx_body[15:8]<=10)frame_valid<=1;
     else begin frame_error<=1;if(rx_byte==8'ha5)begin used<=1;rcrc<=16'hffff;end end
    end
   end
  end
 end
 reg [4:0] ti;reg tbusy;reg [15:0] tcrc;
 wire [4:0] body_index=ti-5'd2;
 wire [4:0] look_index=body_index+5'd1;
 wire [2:0] ram_raddr=(ti<2||ti>=30)?3'd0:
  (tbusy&&tx_ready&&ti<29)?look_index[4:2]:body_index[4:2];
 wire [31:0] ram_q;
 // Parameters/port conventions follow the installed official PH1P DP RAM
 // wrapper ram_f82973da5ab5. Both ports use the same clock; NOREG is one
 // synchronous memory-read edge without an extra output register.
 PH1P_LOGIC_ERAM #(.DATA_WIDTH_A(32),.DATA_WIDTH_B(32),
  .ADDR_WIDTH_A(9),.ADDR_WIDTH_B(9),.DATA_DEPTH_A(512),.DATA_DEPTH_B(512),
  .MODE("DP"),.REGMODE_A("NOREG"),.REGMODE_B("NOREG"),
  .WRITEMODE_A("NORMAL"),.WRITEMODE_B("NORMAL"),.IMPLEMENT("20K(FAST)"),
  .ECC_ENCODE("DISABLE"),.ECC_DECODE("DISABLE"),.CLKMODE("ASYNC"),
  .SSROVERCE("DISABLE"),.OREGSET_A("RESET"),.OREGSET_B("RESET"),
  .RESETMODE_A("ASYNC"),.RESETMODE_B("ASYNC"),
  .ASYNC_RESET_RELEASE_A("ASYNC"),.ASYNC_RESET_RELEASE_B("ASYNC"),
  .INIT_FILE("NONE"),.FILL_ALL("NONE")) u_tx_eram(
  .dia(tx_word),.dib(32'd0),.addra({6'd0,capture_index}),.addrb({6'd0,ram_raddr}),
  .cea(1'b1),.ceb(1'b1),.ocea(1'b0),.oceb(1'b0),.clka(clk),.clkb(clk),
  .wea(capture_busy),.web(1'b0),.bea(1'b0),.beb(1'b0),.rsta(1'b0),.rstb(1'b0),
  .doa(),.dob(ram_q),.ecc_sbiterr(),.ecc_dbiterr(),.ecc_sbiterrinj(1'b0),.ecc_dbiterrinj(1'b0));
 assign frame_ready=!tbusy&&!capture_busy&&tx_ready;assign tx_valid=tbusy;
 assign tx_byte=ti==0?8'ha5:ti==1?8'h5a:ti<30?ram_q[{body_index[1:0],3'b000}+:8]:ti==30?tcrc[7:0]:tcrc[15:8];
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin ti<=0;tbusy<=0;tcrc<=16'hffff;capture_index<=0;capture_busy<=0;capture_done<=0;end
  else begin
   capture_done<=0;
   if(frame_send&&frame_ready)begin capture_index<=0;capture_busy<=1;end
   if(capture_busy)begin
    if(capture_index==6)begin
     capture_busy<=0;capture_done<=1;ti<=0;tbusy<=1;tcrc<=16'hffff;
    end else capture_index<=capture_index+1'b1;
   end else if(tbusy&&tx_ready)begin
   if(ti>=2&&ti<30)tcrc<=crc_byte(tcrc,tx_byte);
   if(ti==31)tbusy<=0;else ti<=ti+1'b1;
   end
  end
 end
endmodule
