// Same-edge exactglyphROM candidate. OneERAM replaces label/glyph combinationalnetwork.
// Four RGB888 pixels, MSB pixel first. Burn mode status into the processed
// frame BEFORE DDR, so frame buffering cannot separate label from its pixels.
// One elastic stage; data/SOF/EOL hold under backpressure. No new clock or pin.
module t06_mode_osd #(parameter WIDTH=1280, HEIGHT=720)(
 input clk,rst_n,
 input [95:0] s_data,input s_valid,output s_ready,input s_sof,s_eol,
 input [4:0] s_mode, input [1:0] s_sat_level,
 output [95:0] m_data,output reg m_valid,input m_ready,
 output reg m_sof,m_eol,output reg protocol_error,output wire [6:0] frame_style
);
 wire advance=!m_valid || m_ready;
 assign s_ready=rst_n && advance;
 reg [15:0] x,y;
 reg synced;
 reg [4:0] frame_mode;reg [1:0] frame_sat;
 assign frame_style={frame_sat,frame_mode};
 wire [4:0] selected_mode=s_mode<20?s_mode:5'd0;
 wire [1:0] paint_sat=s_sof?s_sat_level:frame_sat;
 wire [15:0] px=s_sof?16'd0:x;
 wire [15:0] py=s_sof?16'd0:y;
 wire [4:0] paint_mode=s_sof?selected_mode:frame_mode;
 wire [4:0] glyph_mode=paint_mode==7?(5'd20+{3'd0,paint_sat}):paint_mode;
 wire [15:0] tx=px-16'd40;
 wire [15:0] ty=py-16'd20;
 // Groups start on multiples of four and text cells on multiples of sixteen.
 // Thus all four pixels share the same character and glyph row.
 // ROM and pixel/base/column registers update on the SAME original output edge.
 // There is no extra streamstage. Reset gates the textmask, never the memory.
 wire [4:0] rom_row;
 wire rom_ce=rst_n && advance && s_valid && (synced || s_sof);
 reg [95:0] base_data;
 reg [3:0] text_mask;
 reg [2:0] column_base;
 assign m_data=base_data;
 reg [15:0] lx;
 reg [2:0] col;
 integer k;
 always @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin
   x<=0;y<=0;synced<=0;frame_mode<=0;frame_sat<=0;
   base_data<=0;text_mask<=0;column_base<=0;m_valid<=0;m_sof<=0;m_eol<=0;protocol_error<=0;
  end else if(advance) begin
   m_valid<=s_valid && (synced || s_sof);
   if(s_valid) begin
    if(!synced && !s_sof)protocol_error<=1;
    if(s_sof)begin synced<=1;frame_mode<=selected_mode;frame_sat<=s_sat_level;end
    if(synced || s_sof)begin
     if(s_eol!=(px==WIDTH-4))protocol_error<=1;
     if(s_sof && synced && (x!=0 || y!=0))protocol_error<=1;
     if(!s_sof && synced && x==0 && y==0)protocol_error<=1;
     x<=px==WIDTH-4?0:px+4;
     y<=px==WIDTH-4?(py==HEIGHT-1?0:py+1'b1):py;
     base_data<=s_data;m_sof<=s_sof;m_eol<=s_eol;column_base<=tx[3:1];

    end
   end
  end
 end
endmodule
