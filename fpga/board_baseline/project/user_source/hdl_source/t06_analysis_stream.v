// P1.F4 shared pre-OSD analysis stream. All pixels remain tentative until close.
// Same CSI clock, no ready/backpressure and no main-video register stage.
module t06_analysis_stream #(
 parameter WIDTH=1280,HEIGHT=720
)(
 input clk,rst_n,input [95:0] s_rgb,input [31:0] s_gray,
 input s_valid,s_sof,s_eol,frame_error,
 input [31:0] source_id,input source_id_valid,
 output [95:0] m_rgb,output [31:0] m_gray,
 output m_valid,m_sof,m_eol,output [8:0] m_group_x,output [9:0] m_y,
 output [31:0] m_source_id,output m_source_valid,m_error,
 output reg frame_pulse,frame_complete,output reg [31:0] frame_id,
 output reg [15:0] rgb_signature,gray_signature
);
 localparam GROUPS=WIDTH/4,TOTAL=GROUPS*HEIGHT;
 reg active,bad,done,identity_valid;
 reg [8:0] gx;reg [9:0] gy;
 reg [17:0] groups_seen;
 reg [31:0] fid;
 reg [15:0] rgb_acc,gray_acc;
 wire start=s_valid&&s_sof;
 wire take=s_valid&&(active||s_sof);
 wire [8:0] ix=s_sof?9'd0:gx;
 wire [9:0] iy=s_sof?10'd0:gy;
 wire bad_eol=take&&(s_eol!=(ix==GROUPS-1));
 wire orphan=s_valid&&!active&&!s_sof;
 // Fixed word rotations retain lane-order evidence; wiring/XOR only.
 wire [15:0] rgb_fold=s_rgb[95:80]^{s_rgb[78:64],s_rgb[79]}^{s_rgb[60:48],s_rgb[63:61]}^
                         {s_rgb[42:32],s_rgb[47:43]}^{s_rgb[24:16],s_rgb[31:25]}^{s_rgb[4:0],s_rgb[15:5]};
 wire [15:0] gray_fold=s_gray[31:16]^{s_gray[12:0],s_gray[15:13]};
 wire close_good=active&&!bad&&!frame_error&&source_id_valid&&done&&groups_seen==TOTAL;
 assign m_rgb=s_rgb;assign m_gray=s_gray;
 assign m_valid=rst_n&&take;
 assign m_sof=m_valid&&s_sof;assign m_eol=m_valid&&s_eol;
 assign m_group_x=ix;assign m_y=iy;
 assign m_source_id=s_sof?source_id:fid;
 assign m_source_valid=rst_n&&(s_sof?source_id_valid:identity_valid);
 // Report current faults only; sticky bad must not poison all later frames.
 assign m_error=frame_error||bad_eol||orphan||(active&&!source_id_valid);
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   active<=0;bad<=0;done<=0;identity_valid<=0;gx<=0;gy<=0;groups_seen<=0;fid<=0;
   rgb_acc<=0;gray_acc<=0;frame_pulse<=0;frame_complete<=0;frame_id<=0;
   rgb_signature<=0;gray_signature<=0;
  end else begin
   frame_pulse<=0;
   if(active&&(frame_error||!source_id_valid))bad<=1;
   if(start)begin
    if(active)begin
     frame_pulse<=1;frame_complete<=close_good;frame_id<=fid;
     rgb_signature<=close_good?rgb_acc:16'd0;
     gray_signature<=close_good?gray_acc:16'd0;
    end
    active<=1;bad<=frame_error||!source_id_valid||bad_eol;
    identity_valid<=source_id_valid;fid<=source_id;groups_seen<=1;done<=0;
    rgb_acc<=rgb_fold;gray_acc<=gray_fold;
   end else if(take)begin
    if(done||bad_eol)bad<=1;
    if(groups_seen<TOTAL+1)groups_seen<=groups_seen+1'b1;
    rgb_acc<={rgb_acc[14:0],rgb_acc[15]}^rgb_fold;
    gray_acc<={gray_acc[14:0],gray_acc[15]}^gray_fold;
   end
   if(take)begin
    if(ix==GROUPS-1)begin
     gx<=0;
     if(iy==HEIGHT-1)begin gy<=0;done<=1;end else gy<=iy+1'b1;
    end else begin gx<=ix+1'b1;gy<=iy;end
   end
  end
 end
endmodule
