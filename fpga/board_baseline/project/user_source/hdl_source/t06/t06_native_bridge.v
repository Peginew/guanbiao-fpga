// Adapter for this teammate ISP: AWB has an EARLY frame pulse, not AXIS SOF.
// Upstream is non-stalling; T06 m_ready is permanently 1. No backpressure.
// Line/frame positions count valid beats, never falling edges of valid.
module t06_native_bridge #(
 parameter WIDTH=1280, HEIGHT=720, ENABLE_MODE_OSD=0
)(
 input clk,rst_n,
 input [95:0] native_data, input native_valid, native_frame_start,
 input [4:0] cfg_mode, input [1:0] cfg_sat_level, input [7:0] cfg_binary_th,
 input [10:0] cfg_edge_th,
 output reg frame_start_early,
 output [127:0] data128, output valid128, sof128, eol128,
 output [4:0] active_mode, output error, output wire [6:0] display_style,
 output [95:0] rgb4, output [31:0] gray4, output gray_valid,gray_sof,gray_eol,gray_abort
);
 localparam GROUPS=WIDTH/4;
 localparam XW=(GROUPS<=1)?1:$clog2(GROUPS);
 localparam YW=(HEIGHT<=1)?1:$clog2(HEIGHT);
 reg [XW-1:0] x;
 reg [YW-1:0] y;
 reg active,pending,source_error;
 reg [4:0] frame_mode;
 wire start_pixel = native_valid && (pending || native_frame_start);
 wire accept = native_valid && (active || native_frame_start);
 wire last_pixel_group = (start_pixel ? 0 : x)==GROUPS-1;
 wire [95:0] filtered;
 wire filtered_valid,filtered_sof,filtered_eol,ready;
 wire core_error,pack_error,status_error;
 wire [95:0] decorated;
 wire decorated_valid,decorated_sof,decorated_eol;
 wire [4:0] filtered_mode;
 wire [1:0] filtered_sat_level;
 wire [6:0] painted_style;
 assign active_mode=frame_mode;
 assign gray_valid=filtered_valid;assign gray_sof=filtered_sof;assign gray_eol=filtered_eol;
 // Pulse-level protocol fault; old sticky error remains unchanged for diagnostics.
 assign gray_abort=(native_frame_start&&active)||(native_valid&&!active&&!native_frame_start)||(accept&&!ready);
 assign error=source_error || core_error || pack_error || status_error;
 always @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin
   x<=0;y<=0;active<=0;pending<=0;source_error<=0;
   frame_start_early<=0;frame_mode<=0;
  end else begin
   // Preserve the original native frame-pulse latency to video_in.
   frame_start_early<=native_frame_start;
   if(native_frame_start) begin
    if(active) source_error<=1; // previous frame did not finish
    active<=1;pending<=1;x<=0;y<=0;
   end
   if(native_valid && !active && !native_frame_start) source_error<=1;
   if(accept) begin
    if(!ready) source_error<=1; // impossible with constant m_ready after reset
    if(start_pixel) begin
     pending<=0;frame_mode<=cfg_mode<20?cfg_mode:5'd0;
     x<=GROUPS==1?0:1;y<=0;
     if(GROUPS==1) begin
      y<=HEIGHT==1?0:1;
      if(HEIGHT==1) active<=0;
     end
    end else if(last_pixel_group) begin
     x<=0;
     if(y==HEIGHT-1) begin y<=0;active<=0;end
     else y<=y+1'b1;
    end else x<=x+1'b1;
   end
  end
 end
 t06_video_filter #(.WIDTH(WIDTH),.HEIGHT(HEIGHT)) u_filter(
  .clk(clk),.rst_n(rst_n),.s_data(native_data),.s_valid(accept),.s_ready(ready),
  .s_sof(start_pixel),.s_eol(last_pixel_group),
  .cfg_mode(cfg_mode),.cfg_sat_level(cfg_sat_level),.cfg_binary_th(cfg_binary_th),.cfg_edge_th(cfg_edge_th),
  .m_data(filtered),.m_rgb(rgb4),.m_gray(gray4),.m_valid(filtered_valid),.m_ready(1'b1),
  .m_sof(filtered_sof),.m_eol(filtered_eol),.m_mode(filtered_mode),.m_sat_level(filtered_sat_level),.protocol_error(core_error)
 );
 generate if(ENABLE_MODE_OSD)begin: g_status
  t06_mode_osd #(.WIDTH(WIDTH),.HEIGHT(HEIGHT)) u_status(
   .clk(clk),.rst_n(rst_n),.s_data(filtered),.s_valid(filtered_valid),.s_ready(),
   .s_sof(filtered_sof),.s_eol(filtered_eol),.s_mode(filtered_mode),.s_sat_level(filtered_sat_level),
   .m_data(decorated),.m_valid(decorated_valid),.m_ready(1'b1),
   .m_sof(decorated_sof),.m_eol(decorated_eol),.protocol_error(status_error),.frame_style(painted_style));
 assign display_style=painted_style;
 end else begin: g_no_status
  assign decorated=filtered;
  assign decorated_valid=filtered_valid;
  assign decorated_sof=filtered_sof;
  assign decorated_eol=filtered_eol;
  assign status_error=1'b0;
  assign display_style={filtered_sat_level,filtered_mode};
 end endgenerate
 t06_pack96_128 u_pack(
  .clk(clk),.rst_n(rst_n),.s_data(decorated),.s_valid(decorated_valid),
  .s_sof(decorated_sof),.s_eol(decorated_eol),.m_data(data128),
  .m_valid(valid128),.m_sof(sof128),.m_eol(eol128),.format_error(pack_error)
 );
endmodule
