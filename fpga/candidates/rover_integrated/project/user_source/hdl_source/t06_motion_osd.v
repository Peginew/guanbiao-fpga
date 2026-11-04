// Small passive MOT15 panel and exact-source matched change rectangle.
// All inputs in the HDMI pixel clock domain. RGB combinational, no DE/VS delay.
module t06_motion_osd #(
 parameter WIDTH=1280,HEIGHT=720,SOURCE_X_OFFSET=0,SOURCE_Y_OFFSET=0,ENABLE_ANALYSIS_PANEL=0,SHOW_TEXT=1
)(
 input clk,rst_n,vs,de,input [23:0] rgb,
 input [2:0] state,input stable,result_valid,input [13:0] changed,
 input [15:0] events,input [7:0] xmin,xmax,input [6:0] ymin,ymax,
 input analysis_valid,input [15:0] analysis_rgb_sig,analysis_gray_sig,
 output [23:0] out_rgb
);
 reg de_prev,vs_prev;reg [10:0] x,y;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin de_prev<=0;vs_prev<=0;x<=0;y<=0;end
  else begin
   de_prev<=de;vs_prev<=vs;
   if(vs&&!vs_prev)begin x<=0;y<=0;end
   else begin
    if(!de)x<=0;else if(x!=2047)x<=x+1'b1;
    if(de_prev&&!de&&y!=2047)y<=y+1'b1;
   end
  end
 end
 wire [10:0] bx0={xmin,3'b000}+SOURCE_X_OFFSET;
 wire [10:0] bx_end={xmax,3'b111}+SOURCE_X_OFFSET;
 wire [10:0] bx1=bx_end>=WIDTH?WIDTH-1:bx_end;
 wire [10:0] by0={1'b0,ymin,3'b000}+SOURCE_Y_OFFSET;
 wire [10:0] by_end={1'b0,ymax,3'b111}+SOURCE_Y_OFFSET;
 wire [10:0] by1=by_end>=HEIGHT?HEIGHT-1:by_end;
 wire box=result_valid&&state==3&&de&&x>=bx0&&x<=bx1&&y>=by0&&y<=by1&&
          (x==bx0||x==bx1||y==by0||y==by1);
 // 27 characters at x704..919/y112..127. Hex avoids decimal dividers.
 wire motion_panel=de&&x>=704&&x<920&&y>=112&&y<128;
 wire analysis_panel=ENABLE_ANALYSIS_PANEL&&de&&x>=704&&x<872&&y>=144&&y<160;
 wire panel=motion_panel||analysis_panel;
 wire [7:0] px=x-704;wire [3:0] py=y-112;
 wire [4:0] col=px[7:3];wire [2:0] row=py[3:1],fc=px[2:0];
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
   default:font=0;
  endcase end
 endfunction
 reg [4:0] bits;wire [34:0] glyph=font(ch);
 always @*begin
  ch=31;
  if(analysis_panel)begin
   case(col)
    0:ch=10;1:ch=4;3:ch=19;4:ch=20;5:ch={4'd0,analysis_valid};
    7:ch=21;8:ch=20;9:ch={1'b0,analysis_rgb_sig[15:12]};10:ch={1'b0,analysis_rgb_sig[11:8]};
    11:ch={1'b0,analysis_rgb_sig[7:4]};12:ch={1'b0,analysis_rgb_sig[3:0]};
    14:ch=22;15:ch=20;16:ch={1'b0,analysis_gray_sig[15:12]};17:ch={1'b0,analysis_gray_sig[11:8]};
    18:ch={1'b0,analysis_gray_sig[7:4]};19:ch={1'b0,analysis_gray_sig[3:0]};
   endcase
  end else case(col)
   0:ch=16;1:ch=17;2:ch=18;3:ch=1;4:ch=5;
   6:ch=19;7:ch=20;8:ch={2'b0,state};
   10:ch=18;11:ch=20;12:ch={4'd0,stable};
   14:ch=12;15:ch=20;16:ch={3'd0,changed[13:12]};
   17:ch={1'b0,changed[11:8]};18:ch={1'b0,changed[7:4]};19:ch={1'b0,changed[3:0]};
   21:ch=14;22:ch=20;23:ch={1'b0,events[15:12]};24:ch={1'b0,events[11:8]};
   25:ch={1'b0,events[7:4]};26:ch={1'b0,events[3:0]};
  endcase
  case(row)
   0:bits=glyph[34:30];1:bits=glyph[29:25];2:bits=glyph[24:20];
   3:bits=glyph[19:15];4:bits=glyph[14:10];5:bits=glyph[9:5];6:bits=glyph[4:0];default:bits=0;
  endcase
 end
 wire ink=fc>=1&&fc<=5&&bits[5-fc];
 wire [23:0] color=!result_valid?24'hb0b0b0:state==4?24'hffb040:state==3?24'hff6060:stable?24'h60ff80:24'he0f0ff;
 assign out_rgb=SHOW_TEXT&&panel?(ink?(analysis_panel?(analysis_valid?24'h60ff80:24'hb0b0b0):color):24'h081018):box?24'hff6060:rgb;
endmodule
