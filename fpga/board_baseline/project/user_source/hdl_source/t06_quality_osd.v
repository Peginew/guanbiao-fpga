// AQ18 latest-controller diagnostic, not displayed-frame reading validity.
// Payload is transferred atomically; visible fields latch only on VS boundary.
module t06_quality_osd (
 input clk,rst_n,vs,de,input [23:0] rgb,
 input telemetry_valid,input [167:0] telemetry,output [23:0] out_rgb
);
 reg [167:0] pending,shown; reg have_pending,have_shown;
 reg de_prev,vs_prev;reg [10:0] x,y;
 always @(posedge clk or negedge rst_n) begin
  if(!rst_n)begin pending<=0;shown<=0;have_pending<=0;have_shown<=0;de_prev<=0;vs_prev<=0;x<=0;y<=0;end
  else begin
   de_prev<=de;vs_prev<=vs;
   if(telemetry_valid)begin pending<=telemetry;have_pending<=1;end
   if(vs&&!vs_prev)begin x<=0;y<=0;if(have_pending)begin shown<=pending;have_shown<=1;end end
   else begin
    if(!de)x<=0;else if(x!=2047)x<=x+1'b1;
    if(de_prev&&!de&&y!=2047)y<=y+1'b1;
   end
  end
 end
 wire [3:0] st;wire ready_q,fault_q,awb_s,awb_c;
 wire [15:0] exp_q,gain_q,n_q,dark_q,bright_q;
 wire [11:0] r_q,b_q;wire [23:0] ysum_q;wire [31:0] frame_q;
 assign {st,ready_q,fault_q,awb_s,awb_c,exp_q,gain_q,r_q,b_q,ysum_q,n_q,frame_q,dark_q,bright_q}=shown;
 wire panel=de&&x>=704&&x<1080&&y>=176&&y<208;
 wire [8:0] px=x-704;wire [4:0] py=y-176;
 wire [5:0] col=px[8:3];wire [2:0] row=py[3:1],fc=px[2:0];
 reg [4:0] ch;
 function [34:0] font;
  input [4:0] c;
  begin case(c)
   0:font=35'b01110100011001110101110011000101110;
   1:font=35'b00100011000010000100001000010001110;
   2:font=35'b01110100010000100010001000100011111;
   3:font=35'b11110000010000101110000010000111110;
   4:font=35'b00010001100101010010111110001000010;
   5:font=35'b11111100001000011110000010000111110;
   6:font=35'b01110100001000011110100011000101110;
   7:font=35'b11111000010001000100010000100001000;
   8:font=35'b01110100011000101110100011000101110;
   9:font=35'b01110100011000101111000010000101110;
   10:font=35'b01110100011000111111100011000110001;
   11:font=35'b11110100011000111110100011000111110;
   12:font=35'b01111100001000010000100001000001111;
   13:font=35'b11110100011000110001100011000111110;
   14:font=35'b11111100001000011110100001000011111;
   15:font=35'b11111100001000011110100001000010000;
   16:font=35'b10001110111010110101100011000110001; // M
   17:font=35'b01110100011000110001100011000101110; // O
   18:font=35'b11111001000010000100001000010000100; // T
   19:font=35'b01111100001000001110000010000111110; // S
   20:font=35'b00000000001111100000111110000000000; // =
   21:font=35'b11110100011000111110101001001010001; // R
   22:font=35'b10001100010101000100001000010000100; // Y
   23:font=35'b01110100011000110001101011001001101; // Q
   default:font=0;
  endcase end
 endfunction

 reg [4:0] bits;wire [34:0] glyph=font(ch);
 always @*begin
  ch=31;
  if(!py[4])case(col)
    0:ch=10;1:ch=23;2:ch=1;3:ch=8;
    5:ch=19;6:ch=20;7:ch={1'b0,st};
    9:ch=14;10:ch=20;11:ch={1'b0,exp_q[15:12]};12:ch={1'b0,exp_q[11:8]};13:ch={1'b0,exp_q[7:4]};14:ch={1'b0,exp_q[3:0]};
    16:ch=10;17:ch=20;18:ch={1'b0,gain_q[15:12]};19:ch={1'b0,gain_q[11:8]};20:ch={1'b0,gain_q[7:4]};21:ch={1'b0,gain_q[3:0]};
    23:ch=21;24:ch=20;25:ch={1'b0,r_q[11:8]};26:ch={1'b0,r_q[7:4]};27:ch={1'b0,r_q[3:0]};
    29:ch=11;30:ch=20;31:ch={1'b0,b_q[11:8]};32:ch={1'b0,b_q[7:4]};33:ch={1'b0,b_q[3:0]};
    35:ch=18;36:ch=20;37:ch={4'd0,ready_q};
    39:ch=15;40:ch=20;41:ch={4'd0,fault_q};
    43:ch=12;44:ch=20;45:ch={4'd0,awb_c};
  endcase else case(col)
    0:ch=22;1:ch=20;2:ch={1'b0,ysum_q[23:20]};3:ch={1'b0,ysum_q[19:16]};4:ch={1'b0,ysum_q[15:12]};
    5:ch={1'b0,ysum_q[11:8]};6:ch={1'b0,ysum_q[7:4]};7:ch={1'b0,ysum_q[3:0]};
    9:ch=12;10:ch=20;11:ch={1'b0,n_q[15:12]};12:ch={1'b0,n_q[11:8]};13:ch={1'b0,n_q[7:4]};14:ch={1'b0,n_q[3:0]};
    16:ch=15;17:ch=20;18:ch={1'b0,frame_q[15:12]};19:ch={1'b0,frame_q[11:8]};20:ch={1'b0,frame_q[7:4]};21:ch={1'b0,frame_q[3:0]};
    23:ch=13;24:ch=20;25:ch={1'b0,dark_q[15:12]};26:ch={1'b0,dark_q[11:8]};27:ch={1'b0,dark_q[7:4]};28:ch={1'b0,dark_q[3:0]};
    30:ch=11;31:ch=20;32:ch={1'b0,bright_q[15:12]};33:ch={1'b0,bright_q[11:8]};34:ch={1'b0,bright_q[7:4]};35:ch={1'b0,bright_q[3:0]};
    37:ch=19;38:ch=20;39:ch={4'd0,awb_s};
  endcase
  case(row)
    0:bits=glyph[34:30];1:bits=glyph[29:25];2:bits=glyph[24:20];3:bits=glyph[19:15];
    4:bits=glyph[14:10];5:bits=glyph[9:5];6:bits=glyph[4:0];default:bits=0;
  endcase
 end
 wire ink=(fc>=1&&fc<=5)?bits[5-fc]:1'b0;
 assign out_rgb=panel?(ink?(have_shown?(fault_q?24'hff4444:(ready_q?24'h40ff70:24'hffe060)):24'h808080):24'h101018):rgb;
endmodule
