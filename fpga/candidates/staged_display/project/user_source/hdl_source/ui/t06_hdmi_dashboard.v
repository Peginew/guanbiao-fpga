// Shared sparse text RAM + shared glyph ROM. No full-screen image RAM, CPU,
// blur, framebuffer client, combinational decimal division or new clock.
// All fields snapshot at raster row4 after LF first true source. The shared
// writer finishes before header row12; tests check write-before-visible.
module t06_hdmi_dashboard #(
 parameter TEXT_FILE="C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_staged_display_20261104/project/user_source/hdl_source/ui/ui_text.mem", FONT_FILE="C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_staged_display_20261104/project/user_source/hdl_source/ui/ui_font.mem"
)(
 input wire clk,rst_n,vs,de,input wire [23:0] rgb,
 input wire [4:0] mode,input wire [1:0] sat,
 input wire [251:0] meter_payload,input wire [71:0] meter_debug,
 input wire [3:0] meter_show,input wire estimated,
 input wire [31:0] age_loc,age_geo,age_read,
 input wire [15:0] psi_hundredths,input wire psi_display_valid,
 input wire [31:0] psi_source_id,input wire hard_fault,
 // REF is display-only. Its permission is independent of CNN/READ failure.
 input wire [1:0] ref_mode,input wire ref_valid,input wire [15:0] ref_psi,
 input wire [1:0] lf_status,input wire [31:0] lf_source,lf_latency,
 input wire [1:0] lf_metadata_fault,input wire lf_bad,lf_valid,
 input wire [2:0] mot_state,input wire mot_stable,mot_valid,
 input wire [13:0] mot_changed,input wire [15:0] mot_events,
 input wire a4_valid,input wire [15:0] a4_rgb,a4_gray,
 input wire aq_valid,input wire [167:0] aq_payload,
 output reg out_vs,out_de,output reg [23:0] out_rgb
);
 `include "C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_staged_display_20261104/project/user_source/hdl_source/ui/ui_codes.vh"
 reg [9:0] text_ram[0:4095]; // 40Kbits, reused by captions and changing digits.
 reg [5:0] glyph_rom[0:8191]; // 48Kbits, shared Chinese/Latin halves.
 initial begin $readmemh(TEXT_FILE,text_ram);$readmemh(FONT_FILE,glyph_rom);end
 reg [10:0] x,y;reg de_prev,vs_prev;
 wire boundary=vs&&!vs_prev;
 reg [31:0] frame_counter;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin x<=0;y<=0;de_prev<=0;vs_prev<=0;frame_counter<=0;end
  else begin
   de_prev<=de;vs_prev<=vs;
   if(boundary)begin x<=0;y<=0;frame_counter<=frame_counter+1'b1;end
   else begin
    if(!de)x<=0;else if(x<1279)x<=x+1'b1;
    if(de_prev&&!de)y<=y+1'b1;
   end
  end
 end
 reg [4:0] mode_q;reg [1:0] sat_q;
 reg [251:0] meter_q;reg [71:0] debug_q;reg [3:0] show_q;
 reg loc_estimated_q;reg [31:0] age_loc_q,age_geo_q,age_read_q;
 reg [15:0] psi_value;reg psi_valid;
 reg [1:0] ref_mode_q;reg ref_valid_q;reg [15:0] ref_psi_q;
 // Hide a stale value immediately on switch/configuration change or withdrawal.
 wire ref_config_current=(ref_mode==ref_mode_q)&&((ref_mode_q==0)||(ref_psi==ref_psi_q));
 wire ref_active=(ref_mode_q!=0)&&ref_config_current;
 wire main_value_visible=ref_config_current&&(ref_mode_q!=0 ? (ref_valid_q&&ref_valid):
                         (meter_show[2]&&psi_display_valid&&!hard_fault));
 reg [1:0] lf_state_q;reg [31:0] lf_source_q,lf_latency_q,lf_frames_q;
 reg [3:0] lf_flags_q;
 reg [2:0] mot_state_q;reg mot_stable_q;reg [13:0] mot_changed_q;reg [15:0] mot_events_q;
 reg a4_valid_q;reg [15:0] a4_rgb_q,a4_gray_q;
 reg aq_have_q;reg [167:0] aq_q,aq_latest;reg aq_seen;
 wire [3:0] aq_state;wire aq_ready,aq_fault,aq_awb_stable,aq_credible;
 wire [15:0] aq_exp,aq_gain,aq_count,aq_dark,aq_bright;
 wire [11:0] aq_r,aq_b;wire [23:0] aq_ysum;wire [31:0] aq_frame;
 assign {aq_state,aq_ready,aq_fault,aq_awb_stable,aq_credible,aq_exp,aq_gain,aq_r,aq_b,aq_ysum,aq_count,aq_frame,aq_dark,aq_bright}=aq_q;
 wire m_loc,m_geo,m_read;wire [10:0] m_x0,m_y0,m_x1,m_y1,m_cx,m_cy,m_hx,m_hy;
 wire [31:0] m_loc_source,m_geo_source,m_read_source;wire [15:0] m_target,m_score,m_bcd;wire [8:0] m_angle;wire [7:0] m_reason;
 assign {m_loc,m_x0,m_y0,m_x1,m_y1,m_cx,m_cy,m_loc_source,m_target,m_score,m_geo,m_geo_source,m_hx,m_hy,m_angle,m_read,m_bcd,m_read_source,m_reason}=meter_q;
 wire debug_valid;wire [31:0] debug_source;wire [4:0] debug_reason,debug_flags;
 wire [5:0] debug_mask;wire [9:0] debug_diam;wire signed [4:0] debug_roll;wire [7:0] debug_print;
 assign {debug_valid,debug_source,debug_reason,debug_mask,debug_flags,debug_diam,debug_roll,debug_print}=debug_q;
 wire [4:0] roll_magnitude=debug_roll[4] ? -debug_roll:debug_roll;
 // One source snapshot for all fields in a frame, never live mixed digits.
 wire observation_start=de&&x==0&&y==4;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   mode_q<=0;sat_q<=1;meter_q<=0;debug_q<=0;show_q<=0;loc_estimated_q<=0;
   age_loc_q<=0;age_geo_q<=0;age_read_q<=0;psi_value<=0;psi_valid<=0;
   ref_mode_q<=0;ref_valid_q<=0;ref_psi_q<=0;
   lf_state_q<=0;lf_source_q<=0;lf_latency_q<=0;lf_frames_q<=0;lf_flags_q<=4'b1111;
   mot_state_q<=0;mot_stable_q<=0;mot_changed_q<=0;mot_events_q<=0;
   a4_valid_q<=0;a4_rgb_q<=0;a4_gray_q<=0;aq_have_q<=0;aq_q<=0;aq_latest<=0;aq_seen<=0;
  end else begin
   if(aq_valid)begin aq_latest<=aq_payload;aq_seen<=1;end
   if(observation_start)begin mode_q<=mode;sat_q<=sat;end
   if(observation_start)begin
    meter_q<=meter_payload;debug_q<=meter_debug;show_q<=meter_show;loc_estimated_q<=estimated;
    ref_mode_q<=ref_mode;ref_valid_q<=ref_valid;ref_psi_q<=ref_psi;
    age_loc_q<=age_loc;age_geo_q<=age_geo;age_read_q<=age_read;
    psi_value<=psi_hundredths;psi_valid<=psi_display_valid&&meter_show[2]&&psi_source_id==meter_payload[39:8];
    lf_state_q<=lf_status;lf_source_q<=lf_source;lf_latency_q<=lf_latency;lf_frames_q<=frame_counter;
    lf_flags_q<={lf_metadata_fault,lf_bad,!lf_valid};
    mot_state_q<=mot_state;mot_stable_q<=mot_stable&&mot_valid;mot_changed_q<=mot_changed;mot_events_q<=mot_events;
    a4_valid_q<=a4_valid;a4_rgb_q<=a4_rgb;a4_gray_q<=a4_gray;
    aq_have_q<=aq_seen||aq_valid;aq_q<=aq_valid ? aq_payload:aq_latest;
   end
  end
 end
 // The only decimal converter is time-shared over all scalar display fields.
 reg [5:0] field_index;reg [3:0] engine_state,emit_index;reg header_pass;
 reg [31:0] field_value;reg [11:0] field_address;reg [3:0] field_digits,field_length,field_frac;
 reg [2:0] field_kind;reg field_valid;
 always @*begin
  field_value=0;field_address=0;field_digits=1;field_length=1;field_frac=0;field_kind=0;field_valid=0;
  case(field_index)
   `include "C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_staged_display_20261104/project/user_source/hdl_source/ui/ui_field_cases.vh"
   default:begin end
  endcase
 end
 wire converter_busy,converter_done;wire [39:0] decimal_bcd;
 reg converter_start;
 t06_ui_bin32_bcd decimal_converter(.clk(clk),.rst_n(rst_n),.start(converter_start),.value(field_value),.busy(converter_busy),.done(converter_done),.bcd(decimal_bcd));
 reg [31:0] saved_value;reg [39:0] saved_bcd;reg saved_valid,saved_negative;
 reg [11:0] saved_address;reg [3:0] saved_digits,saved_length,saved_frac;reg [2:0] saved_kind;
 reg [8:0] emit_character;reg [3:0] emit_digit;integer digit_pos;reg nonzero_seen;
 function [8:0] ascii_digit;
  input [3:0] digit;begin case(digit)
   0:ascii_digit=CH_30;1:ascii_digit=CH_31;2:ascii_digit=CH_32;3:ascii_digit=CH_33;4:ascii_digit=CH_34;
   5:ascii_digit=CH_35;6:ascii_digit=CH_36;7:ascii_digit=CH_37;8:ascii_digit=CH_38;9:ascii_digit=CH_39;
   10:ascii_digit=CH_41;11:ascii_digit=CH_42;12:ascii_digit=CH_43;13:ascii_digit=CH_44;14:ascii_digit=CH_45;default:ascii_digit=CH_46;
  endcase end
 endfunction
 function [8:0] state_character;
  input [2:0] kind;input [31:0] value;input [3:0] column;
  reg [55:0] word;
  reg [7:0] letter;
  begin
   word="       ";
   if(kind==3)word=value!=0 ? "LAST   ":"WAIT   ";
   if(kind==7)word=value!=0 ? "REF    ":"       ";
   if(kind==4)word=value==0 ? "WAIT   ":loc_estimated_q ? "EST    ":"CAND   ";
   if(kind==5)case(value[1:0])0:word="INVALID";1:word="NEW    ";2:word="REPEAT ";3:word="STALE  ";endcase
   letter=word[55-column*8 -:8];
   case(letter)
    "L":state_character=CH_4C;"A":state_character=CH_41;"S":state_character=CH_53;"T":state_character=CH_54;
    "W":state_character=CH_57;"I":state_character=CH_49;"C":state_character=CH_43;"N":state_character=CH_4E;
    "D":state_character=CH_44;"E":state_character=CH_45;"P":state_character=CH_50;"R":state_character=CH_52;
    "F":state_character=CH_46;"V":state_character=CH_56;default:state_character=CH_20;
   endcase
  end
 endfunction
 always @*begin
  emit_character=CH_20;emit_digit=0;digit_pos=0;
  if(!saved_valid)emit_character=CH_2D;
  else if((saved_kind>=3&&saved_kind<=5)||saved_kind==7)emit_character=state_character(saved_kind,saved_value,emit_index);
  else if(saved_kind==6&&emit_index==0)emit_character=saved_negative ? CH_2D:CH_20;
  else if(saved_kind==2)emit_character=saved_value[saved_digits-1-emit_index] ? CH_31:CH_30;
  else if(saved_frac!=0&&emit_index==saved_length-saved_frac-1)emit_character=CH_2E;
  else begin
   digit_pos=saved_digits-1-emit_index;
   if(saved_kind==6)digit_pos=saved_digits-emit_index;
   if(saved_frac!=0&&emit_index>saved_length-saved_frac-1)digit_pos=digit_pos+1;
   if(saved_kind==1)emit_digit=saved_value[digit_pos*4 +:4];
   else emit_digit=saved_bcd[digit_pos*4 +:4];
   emit_character=ascii_digit(emit_digit);
   if(saved_kind!=1&&!nonzero_seen&&emit_digit==0&&digit_pos>saved_frac)emit_character=CH_20;
   // The separate sign occupies a preallocated blank immediately before digits.
  end
 end
 wire write_character=engine_state==4;
 always @(posedge clk)if(write_character)text_ram[saved_address+emit_index]<={1'b1,emit_character};
 // Header uses the first MODE and SAT slots. All other fields update after LF.
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin field_index<=0;engine_state<=0;emit_index<=0;converter_start<=0;header_pass<=0;
   saved_value<=0;saved_bcd<=0;saved_valid<=0;saved_negative<=0;saved_address<=0;saved_digits<=0;saved_length<=0;saved_frac<=0;saved_kind<=0;nonzero_seen<=0;end
  else begin
   converter_start<=0;
   if(observation_start)begin field_index<=0;engine_state<=1;header_pass<=0;end
   else case(engine_state)
    0:begin end
    1:begin converter_start<=1;engine_state<=2;end
    2:begin engine_state<=3;end
    3:if(converter_done)begin
     saved_value<=field_value;saved_bcd<=decimal_bcd;saved_valid<=field_valid;saved_negative<=debug_roll[4];saved_address<=field_address;
     saved_digits<=field_digits;saved_length<=field_length;saved_frac<=field_frac;saved_kind<=field_kind;
     emit_index<=0;nonzero_seen<=0;engine_state<=4;
    end
    4:begin
     if(emit_digit!=0&&!(saved_kind==6&&emit_index==0))nonzero_seen<=1;
     if(emit_index+1==saved_length)begin
      if((header_pass&&field_index==1)||field_index==57)engine_state<=0;
      else begin field_index<=field_index+1'b1;engine_state<=1;end
     end else emit_index<=emit_index+1'b1;
    end
    default:engine_state<=0;
   endcase
  end
 end
 // Full native 1280x720 raster. Only the compact OSD pixels are modified.
 // Cells are6x12, Chinese captions use two adjacent cells; no video resampler.
 reg text_hit;reg [11:0] address;reg [2:0] font_column;reg [3:0] font_row;
 reg [23:0] background,foreground;reg [10:0] local_x,local_y;
 reg [7:0] col;reg [4:0] row;reg [2:0] region;
 wire [23:0] panel_background={1'b0,rgb[23:17],1'b0,rgb[15:9],1'b0,rgb[7:1]}+24'h08111a;
 always @*begin
  address=0;text_hit=0;font_column=0;font_row=0;local_x=0;local_y=0;col=0;row=0;region=0;
  background=rgb;foreground=24'h9dbbd0;
  if((x>=112&&x<1264&&y>=6&&y<32)||(x>=864&&x<1264&&y>=70&&y<298)||
     (y>=548&&y<654&&((x>=16&&x<316)||(x>=328&&x<628)||(x>=640&&x<1264)))||
     (x>=16&&x<1264&&y>=674&&y<706))background=panel_background;
  if((y==6||y==31)&&x>=112&&x<1264)background=24'h34596c;
  if((y==70||y==297)&&x>=864&&x<1264)background=24'h34596c;
  if((x==864||x==1263)&&y>=70&&y<298)background=24'h34596c;
  if((y==548||y==653)&&((x>=16&&x<316)||(x>=328&&x<628)||(x>=640&&x<1264)))background=24'h34596c;
  if(x>=120&&x<1260&&y>=12&&y<24)begin text_hit=1;local_x=x-120;local_y=y-12;region=1;end
  else if(x>=872&&x<1256&&y>=76&&y<292)begin text_hit=1;local_x=x-872;local_y=y-76;region=2;end
  else if(x>=24&&x<1260&&y>=554&&y<650)begin text_hit=1;local_x=x-24;local_y=y-554;region=3;end
  else if(x>=24&&x<1260&&y>=678&&y<702)begin text_hit=1;local_x=x-24;local_y=y-678;region=4;end
  col=local_x/11'd6;row=local_y/11'd12;
  font_column=local_x-col*11'd6;font_row=local_y-row*11'd12;
  case(region)
   1:address=col;
   2:address=12'd190+row*12'd64+col;
   3:address=12'd1342+row*12'd206+col;
   4:begin address=12'd2990+row*12'd206+col;
      if((col/8'd20)+row*5'd10==mode_q)begin background=24'h23546a;foreground=24'h82e3ed;end end
   default:address=0;
  endcase
  if(x>=872&&x<962&&y>=88&&y<124)begin
   text_hit=1;local_x=x-872;local_y=y-88;col=local_x/11'd18;
   address=12'd254+col;font_column=(local_x-col*11'd18)/11'd3;font_row=local_y/11'd3;
   foreground=24'hf4bc6e;
   if(!main_value_visible)text_hit=0;
  end else if(x>=872&&x<992&&y>=88&&y<124)text_hit=0;
  // Added REF badge and SET row are invisible in AUTO and during switch mismatch.
  if(((x>=998&&x<1016&&y>=76&&y<88)||(x>=1004&&x<1088&&y>=112&&y<124))&&!ref_active)text_hit=0;
 end
 reg [9:0] tile_q;reg [2:0] column_q,column_qq;reg [3:0] row_q;
 reg hit_q,hit_qq,vs_q,vs_qq,de_q,de_qq;reg [23:0] bg_q,bg_qq,fg_q,fg_qq;
 reg [5:0] glyph_q;
 always @(posedge clk)begin tile_q<=text_ram[address];glyph_q<=glyph_rom[{tile_q[8:0],row_q}];end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin column_q<=0;column_qq<=0;row_q<=0;hit_q<=0;hit_qq<=0;vs_q<=0;vs_qq<=0;de_q<=0;de_qq<=0;
   bg_q<=0;bg_qq<=0;fg_q<=0;fg_qq<=0;out_vs<=0;out_de<=0;out_rgb<=0;end
  else begin
   column_q<=font_column;column_qq<=column_q;row_q<=font_row;
   hit_q<=text_hit;hit_qq<=hit_q;vs_q<=vs;vs_qq<=vs_q;de_q<=de;de_qq<=de_q;
   bg_q<=background;bg_qq<=hit_q&&tile_q[8:0]!=CH_20 ? {1'b0,bg_q[23:17],1'b0,bg_q[15:9],1'b0,bg_q[7:1]}+24'h04080d:bg_q;fg_q<=foreground;fg_qq<=tile_q[9] ? (fg_q==24'hf4bc6e ? 24'hf4bc6e:24'he4f0f8):fg_q;
   out_vs<=vs_qq;out_de<=de_qq;
   out_rgb<=de_qq ? (hit_qq&&column_qq<6&&glyph_q[5-column_qq] ? fg_qq:bg_qq):24'd0;
  end
 end
endmodule
