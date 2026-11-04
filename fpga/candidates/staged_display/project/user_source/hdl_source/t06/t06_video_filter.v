// timing_rev3: display-onlyS2..S5 slowkernel pipeline; TAG243/analysis/n+6 preserved.
// Exact finitecoordwidths only; original13bitSobel retained.
// Twenty-mode display candidate. Original modes0..3 and analysis paths preserved.
// Isolated quality candidate: raw Sobel + same-normal local edge support.
// ORIGINAL/GRAY/BINARY and shared raw RGB/gray keep their exact numerical meaning.
// 4 pixels/clock. All stages/RAM share advance. No new clock, CDC or DDR client.
// Continuous input accepted at n is output at n+6 (old n+3).
// EDGE center is source (x-2,y-2); first four source rows/columns are black.
// Internal stream IP: NOT a board top.
// Modes: 0 passthrough, 1 gray, 2 binary, 3 full-horizontal-resolution Sobel.
// Gray = (77R + 150G + 29B + 128) >> 8, unsigned round-to-nearest.
// Raw Sobel center is (x-1,y-1); the support window adds one spatial pixel.
// First four EDGE rows/columns are black; every valid source group is retained.
// Configuration sampled on accepted SOF. All pipeline state freezes on stall.
module t06_video_filter #(
 parameter WIDTH=1280, HEIGHT=720
)(
 input clk, input rst_n,
 input [95:0] s_data, input s_valid, output s_ready,
 input s_sof, input s_eol,
 input [4:0] cfg_mode, input [1:0] cfg_sat_level, input [7:0] cfg_binary_th,
 input [10:0] cfg_edge_th,
 output wire [95:0] m_data, output reg [95:0] m_rgb, output reg [31:0] m_gray, output reg m_valid, input m_ready,
 output reg m_sof, output reg m_eol,
 output reg [4:0] m_mode, output reg [1:0] m_sat_level,
 output reg protocol_error
);
 localparam GROUPS=WIDTH/4;
 localparam AW=(GROUPS<=1)?1:$clog2(GROUPS);
 localparam DEPTH=1<<AW;
 wire advance = !m_valid || m_ready;
 assign s_ready = rst_n && advance;
 wire accept = s_valid && s_ready;
 localparam YW=(HEIGHT<=1)?1:$clog2(HEIGHT);
 reg [AW-1:0] x_count;
 reg [YW-1:0] y_count;
 reg [1:0] row_bank,bank0,bank1;
 reg synced;
 wire [15:0] in_x = s_sof ? 16'd0 : x_count;
 wire [15:0] in_y = s_sof ? 16'd0 : y_count;
 reg [4:0] mode;
 wire [4:0] selected_cfg=cfg_mode<20?cfg_mode:5'd0;
 reg [1:0] sat_frame;
 reg [7:0] binary_th;
 reg [10:0] edge_th;

 function [7:0] gray;
 input [23:0] p;
 reg [15:0] value;
 reg [15:0] r,g,b;
 begin
 r={8'd0,p[23:16]};g={8'd0,p[15:8]};b={8'd0,p[7:0]};
 // Constant shift/add forms avoid consuming 12 DSP multipliers.
 value=(r<<6)+(r<<3)+(r<<2)+r+(g<<7)+(g<<4)+(g<<2)+(g<<1)+(b<<4)+(b<<3)+(b<<2)+b+16'd128;
 gray=value[15:8]; end
 endfunction

 // Six exact verticalsums feed BOTH Gaussian and SobelGx across4lanes.
 function [9:0] row_sum3;
 input [7:0] a,b,c;
 begin row_sum3=({2'd0,a}+{2'd0,c})+({2'd0,b}<<1);end
 endfunction
 function [12:0] gradient_finished;
 input signed [12:0] gx,gy;
 reg [12:0] ax,ay;
 reg [10:0] magnitude_bits;
 reg [1:0] normal;
 begin
 ax=gx[12]?-gx:gx;ay=gy[12]?-gy:gy;magnitude_bits=ax+ay;
 if((ay<<1)<=ax)normal=0;
 else if((ax<<1)<=ay)normal=2;
 else normal=(gx[12]==gy[12])?1:3;
 gradient_finished={magnitude_bits,normal};
 end endfunction
 function [7:0] spatial_shared;
 input [4:0] md;
 input [7:0] blur,a,e,i;
 reg signed [10:0] value;
 begin
  value=0;
  case(md)
   14:begin
    value=11'sd128+(($signed({3'd0,i})-$signed({3'd0,a}))>>>1);
    spatial_shared=value<0?8'd0:value>255?8'd255:value[7:0];
   end
   15:spatial_shared=(blur<8 || {1'b0,e}>{1'b0,blur}-9'd8)?8'hff:8'd0;
   default:spatial_shared=0; // unusedTAGbits; modes16..19 use late_spatial5
  endcase
 end endfunction

 wire [31:0] exact_gray4;
 t06_gray4_exact_dsp u_gray_exact(.rgb4(s_data),.gray4(exact_gray4));
 reg v0,v1,v2;
 reg sof0,sof1,sof2,eol0,eol1,eol2;
 reg [AW-1:0] x0,x1,x2;
 reg [YW-1:0] y0,y1,y2;
 // Advance the line-first comparator with the existing x1 register.
 reg line_first1;
 reg [4:0] mode0,mode1,mode2;
 reg [1:0] sat0,sat1,sat2;
 reg [7:0] th0,th1,th2;
 reg [10:0] eth0,eth1,eth2;
 reg [95:0] raw0,raw1,raw2;
 reg [31:0] gray0,gray1,gray2;
 reg [31:0] spatial2;
 // Three rotating line banks avoid read/write collision dependence.
 // The current row is written; the previous two rows are read from other banks.
 // RAM and output registers have no reset; valid + border masks protect startup.
 reg [31:0] line_a [0:DEPTH-1]; // synthesis ram_style=bram
 reg [31:0] line_b [0:DEPTH-1]; // synthesis ram_style=bram
 reg [31:0] line_c [0:DEPTH-1]; // synthesis ram_style=bram
 reg [31:0] qa,qb,qc;
 wire [31:0] top1 = bank1==0 ? qb : bank1==1 ? qc : qa;
 wire [31:0] mid1 = bank1==0 ? qc : bank1==1 ? qa : qb;
 always @(posedge clk) begin
   if(advance) begin
     qa<=line_a[x0[AW-1:0]];qb<=line_b[x0[AW-1:0]];qc<=line_c[x0[AW-1:0]];
     if(rst_n && v0) begin
      if(bank0==0)line_a[x0[AW-1:0]]<=gray0;
      if(bank0==1)line_b[x0[AW-1:0]]<=gray0;
      if(bank0==2)line_c[x0[AW-1:0]]<=gray0;
     end
   end
 end
 reg [15:0] top_tail,mid_tail,bot_tail;
 wire [47:0] top_win = {line_first1 ? 16'd0 : top_tail,top1};
 wire [47:0] mid_win = {line_first1 ? 16'd0 : mid_tail,mid1};
 wire [47:0] bot_win = {line_first1 ? 16'd0 : bot_tail,gray1};
 wire [9:0] vertical [0:5];
 wire [7:0] blur_shared [0:3];
 genvar vc,hc;
 generate for(vc=0;vc<6;vc=vc+1)begin:g_vertical
  assign vertical[vc]={2'd0,top_win[47-8*vc -:8]}+
    ({2'd0,mid_win[47-8*vc -:8]}<<1)+{2'd0,bot_win[47-8*vc -:8]};
 end
 for(hc=0;hc<4;hc=hc+1)begin:g_blur
  wire [11:0] gaussian_sum={2'd0,vertical[hc]}+({2'd0,vertical[hc+1]}<<1)+
     {2'd0,vertical[hc+2]}+12'd8;
  assign blur_shared[hc]=gaussian_sum[11:4];
 end endgenerate


 // Displayonly slowkernel retiming. Allstages use originaladvance; no extra
 // streamlatency or newclock. S2..S5 overlap existing supporttag transport.
 // S2: singlecompare percolumn (top/mid), thirdrow delayed; Lap pair sums.
 // S3: finalvertical min/max, neighborpair sum. S4: horizontalmin/max, Lapdiff.
 // S5: select/morphdifference/absoluteclip; S6 reads late_spatial5.
 reg [7:0] late_ab_lo2[0:5],late_ab_hi2[0:5],late_bottom2[0:5];
 reg [7:0] late_vertical_lo3[0:5],late_vertical_hi3[0:5];
 reg [7:0] late_min4[0:3],late_max4[0:3];
 reg [8:0] late_pair02[0:3],late_pair12[0:3];
 reg [9:0] late_center2[0:3],late_center3[0:3],late_neighbor3[0:3];
 reg signed [10:0] late_lap4[0:3];
 reg [4:0] late_mode2,late_mode3,late_mode4;
 reg [3:0] late_border2,late_border3,late_border4;
 reg [31:0] late_spatial5;
 wire [5:0] late_ab_order;
 genvar late_column;
 generate for(late_column=0;late_column<6;late_column=late_column+1)begin:g_late_firstcompare
  assign late_ab_order[late_column]=top_win[47-8*late_column -:8]<=mid_win[47-8*late_column -:8];
 end endgenerate
 function [7:0] late_min3;
  input [7:0] a,b,c;
  reg [7:0] ab;
  begin ab=a<=b?a:b;late_min3=ab<=c?ab:c;end
 endfunction
 function [7:0] late_max3;
  input [7:0] a,b,c;
  reg [7:0] ab;
  begin ab=a>=b?a:b;late_max3=ab>=c?ab:c;end
 endfunction
 function [7:0] late_absolute_byte;
  input signed [10:0] value;
  reg [10:0] magnitude;
  begin
   magnitude=value[10]?(~value+11'd1):value;
   late_absolute_byte=(|magnitude[10:8])?8'hff:magnitude[7:0];
  end
 endfunction
 integer lc,ll;
 always@(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   late_mode2<=0;late_mode3<=0;late_mode4<=0;
   late_border2<=0;late_border3<=0;late_border4<=0;late_spatial5<=0;
   for(lc=0;lc<6;lc=lc+1)begin
    late_ab_lo2[lc]<=0;late_ab_hi2[lc]<=0;late_bottom2[lc]<=0;
    late_vertical_lo3[lc]<=0;late_vertical_hi3[lc]<=0;
   end
   for(ll=0;ll<4;ll=ll+1)begin
    late_min4[ll]<=0;late_max4[ll]<=0;late_pair02[ll]<=0;late_pair12[ll]<=0;
    late_center2[ll]<=0;late_center3[ll]<=0;late_neighbor3[ll]<=0;late_lap4[ll]<=0;
   end
  end else if(advance)begin
   // Bubbles travel through exactly the samestages as valid/data/tag. No
   // independentenables may advance this branch during backpressure.
   late_mode2<=mode1;late_mode3<=late_mode2;late_mode4<=late_mode3;
   late_border3<=late_border2;late_border4<=late_border3;
   for(lc=0;lc<6;lc=lc+1)begin
    late_ab_lo2[lc]<=late_ab_order[lc]?top_win[47-8*lc -:8]:mid_win[47-8*lc -:8];
    late_ab_hi2[lc]<=late_ab_order[lc]?mid_win[47-8*lc -:8]:top_win[47-8*lc -:8];
    late_bottom2[lc]<=bot_win[47-8*lc -:8];
    late_vertical_lo3[lc]<=late_ab_lo2[lc]<=late_bottom2[lc]?late_ab_lo2[lc]:late_bottom2[lc];
    late_vertical_hi3[lc]<=late_ab_hi2[lc]>=late_bottom2[lc]?late_ab_hi2[lc]:late_bottom2[lc];
   end
   for(ll=0;ll<4;ll=ll+1)begin
    late_border2[ll]<=(y1<2)||(line_first1&&(ll<2));
    late_min4[ll]<=late_min3(late_vertical_lo3[ll],late_vertical_lo3[ll+1],late_vertical_lo3[ll+2]);
    late_max4[ll]<=late_max3(late_vertical_hi3[ll],late_vertical_hi3[ll+1],late_vertical_hi3[ll+2]);
    // Balanced two-pair9bit sums; center4e and totalneighbors fit10bits.
    late_pair02[ll]<={1'b0,top_win[39-8*ll -:8]}+{1'b0,mid_win[47-8*ll -:8]};
    late_pair12[ll]<={1'b0,mid_win[31-8*ll -:8]}+{1'b0,bot_win[39-8*ll -:8]};
    late_center2[ll]<={mid_win[39-8*ll -:8],2'b0};
    late_neighbor3[ll]<={1'b0,late_pair02[ll]}+{1'b0,late_pair12[ll]};
    late_center3[ll]<=late_center2[ll];
    late_lap4[ll]<=$signed({1'b0,late_center3[ll]})-$signed({1'b0,late_neighbor3[ll]});
    if(late_border4[ll])late_spatial5[31-8*ll -:8]<=0;
    else case(late_mode4)
     16:late_spatial5[31-8*ll -:8]<=late_min4[ll];
     17:late_spatial5[31-8*ll -:8]<=late_max4[ll];
     18:late_spatial5[31-8*ll -:8]<=late_max4[ll]-late_min4[ll];
     19:late_spatial5[31-8*ll -:8]<=late_absolute_byte(late_lap4[ll]);
     default:late_spatial5[31-8*ll -:8]<=0;
    endcase
   end
  end
 end

 // 3x512x36 RGB333 banks. At stage2 select source(x-2,y-2), exactly
 // the supportedSobel center; fullRGB888 analysis and ORIGINAL stay separate.
 function [35:0] quantize333;
  input [95:0] rgb;
  integer q;
  begin for(q=0;q<4;q=q+1)quantize333[35-9*q -:9]={rgb[95-24*q -:3],rgb[87-24*q -:3],rgb[79-24*q -:3]};end
 endfunction
 reg [35:0] color0,cart_color2;
 reg [31:0] aligned_gray2;
 wire [35:0] color_qa,color_qb,color_qc;
 wire [35:0] top_color1=bank1==0?color_qb:bank1==1?color_qc:color_qa;
 reg [17:0] color_tail;
 wire [53:0] color_window={line_first1?18'd0:color_tail,top_color1};
 // Sameedge/CE as the originalarrays; only the unusedcapacity/mapping changes.
 t06_color_line_ram #(.WORDS(GROUPS)) u_color_a(.clk(clk),.ce(advance),
  .we(rst_n && v0 && bank0==0),.address(x0),.din(color0),.dout(color_qa));
 t06_color_line_ram #(.WORDS(GROUPS)) u_color_b(.clk(clk),.ce(advance),
  .we(rst_n && v0 && bank0==1),.address(x0),.din(color0),.dout(color_qb));
 t06_color_line_ram #(.WORDS(GROUPS)) u_color_c(.clk(clk),.ce(advance),
  .we(rst_n && v0 && bank0==2),.address(x0),.din(color0),.dout(color_qc));
 function [7:0] saturated_channel;
  input [7:0] v,y;input [1:0] level;
  reg signed [10:0] delta,boost,value;
  begin
   delta=$signed({3'd0,v})-$signed({3'd0,y});
   // 00=0.5,01=1.0,10=1.5,11=2.0. Signedshift implements floor.
   case(level)1:boost=0;3:boost=delta;default:boost=delta>>>1;endcase
   value=(level==0?$signed({3'd0,y}):$signed({3'd0,v}))+boost;
   saturated_channel=value<0?8'd0:value>255?8'd255:value[7:0];
  end
 endfunction
 function [23:0] saturation_pixel;
  input [23:0] rgb;input [7:0] y;input [1:0] level;
  begin saturation_pixel={saturated_channel(rgb[23:16],y,level),saturated_channel(rgb[15:8],y,level),saturated_channel(rgb[7:0],y,level)};end
 endfunction
 function [23:0] expanded333;
  input [8:0] c;
  begin expanded333={{c[8:6],c[8:6],c[8:7]},{c[5:3],c[5:3],c[5:4]},{c[2:0],c[2:0],c[2:1]}};end
 endfunction
 function [23:0] direction_color;
  input [53:0] rows;input integer lane;
  reg [2:0] center;
  begin center=rows[53-3*(7+lane) -:3];case(center[1:0])
   0:direction_color=24'h00ffff;1:direction_color=24'hff00ff;
   2:direction_color=24'h50ff50;3:direction_color=24'hffa000;
  endcase end
 endfunction
 reg signed [12:0] grad_gx2[0:3],grad_gy2[0:3];
 wire [12:0] grad_finish2[0:3];
 reg [3:0] border2;
 integer k;
 always @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin
   x_count<=0; y_count<=0; synced<=0; protocol_error<=0;
   row_bank<=0;bank0<=0;bank1<=0;
   mode<=0;sat_frame<=2; binary_th<=128; edge_th<=80;
   v0<=0;v1<=0;v2<=0;
   sof0<=0;sof1<=0;sof2<=0;
   eol0<=0;eol1<=0;eol2<=0;
   x0<=0;y0<=0;x1<=0;y1<=0;x2<=0;y2<=0;line_first1<=1;
   raw0<=0;raw1<=0;raw2<=0;
   gray0<=0;gray1<=0;gray2<=0;spatial2<=0;color0<=0;cart_color2<=0;aligned_gray2<=0;color_tail<=0;
   mode0<=0;mode1<=0;mode2<=0;sat0<=0;sat1<=0;sat2<=0;
   th0<=0;th1<=0;th2<=0;eth0<=0;eth1<=0;eth2<=0;
   top_tail<=0;mid_tail<=0;bot_tail<=0;border2<=0;
   for(k=0;k<4;k=k+1)begin grad_gx2[k]<=0;grad_gy2[k]<=0;end
  end else if(advance) begin
   v0<=accept && (synced || s_sof);
   if(accept) begin
    if(!synced && !s_sof) protocol_error<=1;
    if(s_sof) begin
      synced<=1; mode<=selected_cfg;binary_th<=cfg_binary_th;sat_frame<=cfg_sat_level;edge_th<=cfg_edge_th;
    end
    if(synced || s_sof) begin
     if(s_eol != (in_x==GROUPS-1)) protocol_error<=1;
     if(s_sof && synced && (x_count!=0 || y_count!=0)) protocol_error<=1;
     if(!s_sof && synced && x_count==0 && y_count==0) protocol_error<=1;
     bank0<=s_sof?0:row_bank;
     if(s_sof)row_bank<=GROUPS==1?1:0;
     else if(in_x==GROUPS-1) row_bank<=in_y==HEIGHT-1?0:(row_bank==2?0:row_bank+1'b1);
     x_count <= in_x==GROUPS-1 ? 0 : in_x+1'b1;
     y_count <= in_x==GROUPS-1 ? (in_y==HEIGHT-1 ? 0 : in_y+1'b1) : in_y;
     x0<=in_x;y0<=in_y;sof0<=s_sof;eol0<=s_eol;raw0<=s_data;
     mode0<=s_sof?selected_cfg:mode;
     sat0<=s_sof?cfg_sat_level:sat_frame;
     th0<=s_sof?cfg_binary_th:binary_th;eth0<=s_sof?cfg_edge_th:edge_th;
     gray0<=exact_gray4;color0<=quantize333(s_data);
    end
   end
   v1<=v0;
   if(v0) begin
    x1<=x0;y1<=y0;line_first1<=(x0==0);bank1<=bank0;sof1<=sof0;eol1<=eol0;raw1<=raw0;gray1<=gray0;
    mode1<=mode0;sat1<=sat0;th1<=th0;eth1<=eth0;
   end
   v2<=v1;
   if(v1) begin
    sof2<=sof1;eol2<=eol1;raw2<=raw1;gray2<=gray1;x2<=x1;y2<=y1;
    mode2<=mode1;sat2<=sat1;th2<=th1;eth2<=eth1;
    color_tail<=top_color1[17:0];cart_color2<=color_window[53:18];aligned_gray2<=top_win[47:16];
    top_tail<=top1[15:0];mid_tail<=mid1[15:0];bot_tail<=gray1[15:0];
    for(k=0;k<4;k=k+1) begin
     border2[k]<=(y1<2)||(line_first1&&(k<2));
     // All four spatial modes use the SAME center (x-1,y-1) as this 3x3 window.
     // Causal display is shifted one pixel; top/left two source pixels are black.
     spatial2[31-8*k -:8]<=(y1<2 || (line_first1 && k<2))?8'd0:spatial_shared(mode1,blur_shared[k],top_win[47-8*k -:8],
       mid_win[39-8*k -:8],bot_win[31-8*k -:8]);
     grad_gx2[k]<=$signed({3'd0,vertical[k+2]})-$signed({3'd0,vertical[k]});
     grad_gy2[k]<=$signed({3'd0,row_sum3(top_win[47-8*k -:8],top_win[39-8*k -:8],top_win[31-8*k -:8])})-
       $signed({3'd0,row_sum3(bot_win[47-8*k -:8],bot_win[39-8*k -:8],bot_win[31-8*k -:8])});
    end
   end

  end
 end
 // Each feature is exactly three bits: {raw_edge_above_original_threshold, normal}.
 wire [11:0] features;
 genvar lane;
 generate for(lane=0;lane<4;lane=lane+1)begin:g_feature
  assign grad_finish2[lane]=gradient_finished(grad_gx2[lane],grad_gy2[lane]);
  assign features[11-3*lane -:3]={(!border2[lane] && grad_finish2[lane][12:2]>=eth2),grad_finish2[lane][1:0]};
 end endgenerate
 localparam TAGW=243;
 wire [TAGW-1:0] support_tag;
 wire [53:0] support_rows;
 wire support_valid,support_sof,support_eol;
 wire [3:0] support_mask;
 wire [15:0] support_x,support_y;
 t06_edge_support_rows #(.WIDTH(WIDTH),.TAGW(TAGW)) u_support_rows(
  .clk(clk),.rst_n(rst_n),.ce(advance),.s_data(features),
  .s_tag({cart_color2,aligned_gray2,sat2,raw2,gray2,mode2,th2,spatial2}),.s_valid(v2),.s_sof(sof2),.s_eol(eol2),
  .s_x({{(16-AW){1'b0}},x2}),.s_y({{(16-YW){1'b0}},y2}),.m_rows(support_rows),.m_tag(support_tag),
  .m_valid(support_valid),.m_sof(support_sof),.m_eol(support_eol),
  .m_x(support_x),.m_y(support_y),.m_supported(support_mask));
 function supported;
  input [53:0] rows;
  input integer l;
  reg [2:0] center,neighbor;
  reg found;
  integer r,c;
  begin
   center=rows[53-3*(6+l+1) -:3];found=0;
   for(r=0;r<3;r=r+1)for(c=0;c<3;c=c+1)begin
    neighbor=rows[53-3*(r*6+l+c) -:3];
    if((r!=1 || c!=1) && neighbor[2] && neighbor[1:0]==center[1:0])found=1;
   end
   supported=center[2] && found;
  end
 endfunction
 // Synchronous pointROM read occurs on the existing finaloutput register edge.
 // m_mode/valid and ROMq hold together under backpressure; no extra streamcycle.
 reg [95:0] base_data;
 wire [95:0] point_data;
 t06_point_transform_rom u_point_rom(.clk(clk),.ce(rst_n && advance && support_valid),
  .md(support_tag[44:40]),.rgb4(support_tag[172:77]),.gray4(support_tag[76:45]),.pixels(point_data));
 assign m_data=((m_mode>=4 && m_mode<=6)||m_mode==9||m_mode==10)?point_data:base_data;
 integer out_lane;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   m_valid<=0;base_data<=0;m_rgb<=0;m_gray<=0;m_sof<=0;m_eol<=0;m_mode<=0;m_sat_level<=0;
  end else if(advance)begin
   m_valid<=support_valid;
   if(support_valid)begin
    m_sof<=support_sof;m_eol<=support_eol;m_mode<=support_tag[44:40];m_sat_level<=support_tag[174:173];
    m_rgb<=support_tag[172:77];m_gray<=support_tag[76:45];
    for(out_lane=0;out_lane<4;out_lane=out_lane+1)begin
     case(support_tag[44:40])
      0:base_data[95-24*out_lane -:24]<=support_tag[172-24*out_lane -:24];
      1:base_data[95-24*out_lane -:24]<={3{support_tag[76-8*out_lane -:8]}};
      2:base_data[95-24*out_lane -:24]<=support_tag[76-8*out_lane -:8]>=support_tag[39:32] ? 24'hffffff : 24'h0;
      3:base_data[95-24*out_lane -:24]<=support_y>=4 && support_x>=1 && support_mask[out_lane] ? 24'hffffff : 24'h0;
      14,15:base_data[95-24*out_lane -:24]<={3{support_tag[31-8*out_lane -:8]}};
      16,17,18,19:base_data[95-24*out_lane -:24]<={3{late_spatial5[31-8*out_lane -:8]}};
      7:base_data[95-24*out_lane -:24]<=saturation_pixel(support_tag[172-24*out_lane -:24],support_tag[76-8*out_lane -:8],support_tag[174:173]);
      8:base_data[95-24*out_lane -:24]<=support_y<4||support_x<1?24'hffffff:
        support_mask[out_lane]?24'd0:{3{{1'b1,support_tag[206-8*out_lane -:7]}}};
      11:base_data[95-24*out_lane -:24]<={support_tag[172-24*out_lane -:8],16'd0};
      12:base_data[95-24*out_lane -:24]<=support_y<4||support_x<1||support_mask[out_lane]?24'd0:expanded333(support_tag[242-9*out_lane -:9]);
      13:base_data[95-24*out_lane -:24]<=support_y<4||support_x<1?24'd0:
        support_mask[out_lane]?direction_color(support_rows,out_lane):{3{{2'd0,support_tag[206-8*out_lane -:6]}}};
      default:base_data[95-24*out_lane -:24]<=24'd0;
     endcase
    end
   end
  end
 end
endmodule

// 3 rotating banks, 12 bits/4-pixel group. Current-row read collision is ignored;
// current row is bypassed and only the other two banks supply prior rows.
// RAM/q have no array reset. SOF + first-four-pixel border mask protect stale data.
module t06_edge_support_rows #(
 parameter WIDTH=1280,TAGW=138
)(
 input clk,rst_n,ce,
 input [11:0] s_data,input [TAGW-1:0] s_tag,
 input s_valid,s_sof,s_eol,input [15:0] s_x,s_y,
 output reg [53:0] m_rows,output reg [TAGW-1:0] m_tag,
 output reg m_valid,m_sof,m_eol,output reg [15:0] m_x,m_y,output reg [3:0] m_supported
);
 localparam GROUPS=WIDTH/4,AW=(GROUPS<=1)?1:$clog2(GROUPS),DEPTH=1<<AW;
 reg [1:0] row_bank,bank0,bank1;
 reg v0,v1,sof0,sof1,eol0,eol1;
 reg [15:0] x0,x1,y0,y1;
 reg [11:0] data0,data1;
 reg [TAGW-1:0] tag0,tag1;
 wire [35:0] q;
 genvar b;
 generate for(b=0;b<3;b=b+1)begin:g_bank
  reg [11:0] line_mem[0:DEPTH-1]; // synthesis ram_style=bram
  reg [11:0] qreg;
  always @(posedge clk)if(ce)begin
   qreg<=line_mem[x0[AW-1:0]];
   if(rst_n && v0 && bank0==b)line_mem[x0[AW-1:0]]<=data0;
  end
  assign q[12*b +:12]=qreg;
 end endgenerate
 reg [5:0] tail[0:2];
 reg [11:0] word;
 reg [17:0] joined;
 reg [53:0] built_rows;
 function row_supported;
  input [53:0] rows;
  input integer l;
  reg [2:0] center,neighbor;
  reg found;
  integer r,c;
  begin
   center=rows[53-3*(6+l+1) -:3];found=0;
   for(r=0;r<3;r=r+1)for(c=0;c<3;c=c+1)begin
    neighbor=rows[53-3*(r*6+l+c) -:3];
    if((r!=1 || c!=1) && neighbor[2] && neighbor[1:0]==center[1:0])found=1;
   end
   row_supported=center[2] && found;
  end
 endfunction
 integer r,which,support_lane;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   row_bank<=0;bank0<=0;bank1<=0;v0<=0;v1<=0;
   sof0<=0;sof1<=0;eol0<=0;eol1<=0;
   x0<=0;x1<=0;y0<=0;y1<=0;data0<=0;data1<=0;tag0<=0;tag1<=0;
   m_rows<=0;m_supported<=0;m_tag<=0;m_valid<=0;m_sof<=0;m_eol<=0;m_x<=0;m_y<=0;
   word=0;joined=0;which=0;built_rows=0;
   for(r=0;r<3;r=r+1)tail[r]<=0;
  end else if(ce)begin
   v0<=s_valid;
   if(s_valid)begin
    data0<=s_data;tag0<=s_tag;sof0<=s_sof;eol0<=s_eol;
    x0<=s_x;y0<=s_y;bank0<=s_sof?0:row_bank;
    if(s_sof)row_bank<=GROUPS==1?1:0;
    else if(s_x==GROUPS-1)row_bank<=row_bank==2?0:row_bank+1'b1;
   end
   v1<=v0;
   if(v0)begin
    data1<=data0;tag1<=tag0;sof1<=sof0;eol1<=eol0;
    x1<=x0;y1<=y0;bank1<=bank0;
   end
   m_valid<=v1;
   if(v1)begin
    m_tag<=tag1;m_sof<=sof1;m_eol<=eol1;m_x<=x1;m_y<=y1;
    for(r=0;r<3;r=r+1)begin
     which=bank1+1+r;if(which>=3)which=which-3;
     word=r==2 ? data1 : q[12*which +:12];
     joined={x1==0?6'd0:tail[r],word};tail[r]<=joined[5:0];
     m_rows[53-18*r -:18]<=joined;
     built_rows[53-18*r -:18]=joined;
    end
    for(support_lane=0;support_lane<4;support_lane=support_lane+1)
     m_supported[support_lane]<=row_supported(built_rows,support_lane);
   end
  end
 end
endmodule
