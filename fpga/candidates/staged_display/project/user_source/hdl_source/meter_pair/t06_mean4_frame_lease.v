// Private complete-frame320x180 mean4 snapshot. No ready/backpressure to video.
// CSI: 320 four-pixel groups/row,720rows,SOF on the first valid group.
// Ownership transfers only after the next fresh SOF closes an exact full frame.
module t06_mean4_frame_lease #(
 parameter MAX_OWNER_CYCLES=1500000000
)(
 input wire csi_clk,core_clk,arst_n,
 input wire [31:0] gray4,input wire s_valid,s_sof,s_eol,frame_error,
 input wire source_valid,input wire [31:0] source_id,source_epoch,cfg_revision,
 input wire enabled,core_cancel,
 output reg capture_open_pulse,output reg [31:0] capture_open_source,capture_open_epoch,capture_open_cfg,
 output reg owner_valid,output reg [31:0] owner_source,owner_epoch,owner_cfg,owner_lease,
 output reg [31:0] capture_age,output reg owner_pulse,owner_revoke,
 output reg [31:0] owner_capture_csi_cycles,
 input wire release_valid,input wire [31:0] release_lease,
 input wire rd_req,input wire [15:0] rd_addr,input wire [31:0] rd_lease,
 output reg rd_valid,output reg [7:0] rd_data,output reg rd_fault,
 output reg [31:0] dropped_frames
);
 reg [1:0] c_release,p_release;
 always @(posedge csi_clk or negedge arst_n)if(!arst_n)c_release<=0;else c_release<={c_release[0],1'b1};
 always @(posedge core_clk or negedge arst_n)if(!arst_n)p_release<=0;else p_release<={p_release[0],1'b1};
 wire crst=c_release[1],prst=p_release[1];
 (* ram_style="bram" *)reg [11:0] row_accum[0:319];reg [7:0] frame_ram[0:57599];
 reg [11:0] accum_q;
 reg [8:0] x;reg [9:0] y;reg [17:0] groups;reg [15:0] writes;
 reg [1:0] state;localparam WAIT=0,CAPTURE=1,OWNED=2;
 reg bad,frame_done,req,ack;
 (* async_reg="true" *)reg ack1,ack2,req1,req2,cancel1,cancel2;
 (* async_reg="true" *)reg generation1,generation2;
 reg cancel_generation,captured_generation,payload_generation;
 reg cancel_barrier;reg [1:0] cancel_drain_count;
 reg generation_ack;
 (* async_reg="true" *)reg generation_ack1,generation_ack2;
 reg [31:0] cid,cepoch,ccfg,payload_id,payload_epoch,payload_cfg;
 reg [31:0] last_id,last_epoch;reg have_sof;
 reg [31:0] capture_csi_cycles,payload_capture_cycles;
 reg stage_valid;reg [8:0] stage_x;reg [9:0] stage_y;reg [9:0] stage_sum;
 wire [9:0] hsum={2'd0,gray4[31:24]}+{2'd0,gray4[23:16]}+{2'd0,gray4[15:8]}+{2'd0,gray4[7:0]};
 wire [12:0] total={1'b0,accum_q}+{3'd0,stage_sum};
 wire [12:0] rounded_total=total+13'd8;
 wire sof=s_valid&&s_sof;
 wire [31:0] source_delta=source_id-last_id;
 wire fresh_sof=!have_sof||source_epoch!=last_epoch||(source_delta!=0&&!source_delta[31]);
 wire eol_good=s_eol==(x==319);
 wire final_write_pending=stage_valid&&stage_y==719&&stage_x==319;
 wire close_good=fresh_sof&&state==CAPTURE&&frame_done&&!bad&&!frame_error&&source_valid&&enabled&&!cancel2&&captured_generation==generation2&&
                 groups==230400&&(writes==57600||(writes==57599&&final_write_pending))&&source_epoch==cepoch&&cfg_revision==ccfg;
 wire [15:0] frame_write_addr={stage_y[9:2],8'b0}+{2'b0,stage_y[9:2],6'b0}+{7'd0,stage_x};
 wire row_we=stage_valid&&stage_y[1:0]!=3;
 wire [11:0] row_wdata=stage_y[1:0]==0?{2'd0,stage_sum}:total[11:0];
 // Expiry/cancel barrier requests retire with rd_fault, never disappear.
 wire read_allowed=owner_valid&&!core_cancel&&!cancel_barrier&&capture_age<MAX_OWNER_CYCLES-1&&rd_lease==owner_lease&&rd_addr<57600&&!(release_valid&&release_lease==owner_lease);
 always @(posedge core_clk)if(rd_req&&read_allowed)rd_data<=frame_ram[rd_addr];
 // Synchronous previous-row sum. Horizontal groups on adjacent rows are far
 // apart; stage metadata keeps the one-cycle RAM return associated with x/y.
 always @(posedge csi_clk)begin
  if(crst&&s_valid&&state==CAPTURE&&!s_sof&&!bad)accum_q<=row_accum[x];
  if(row_we)row_accum[stage_x]<=row_wdata;
  if(stage_valid)begin
   if(stage_y[1:0]==3)frame_ram[frame_write_addr]<=rounded_total[11:4];
  end
 end
 always @(posedge csi_clk or negedge crst)begin
  if(!crst)begin
   state<=WAIT;x<=0;y<=0;groups<=0;writes<=0;bad<=0;frame_done<=0;req<=0;ack1<=0;ack2<=0;cancel1<=0;cancel2<=0;generation1<=0;generation2<=0;captured_generation<=0;payload_generation<=0;generation_ack<=0;
   cid<=0;cepoch<=0;ccfg<=0;payload_id<=0;payload_epoch<=0;payload_cfg<=0;last_id<=0;last_epoch<=0;have_sof<=0;capture_csi_cycles<=0;payload_capture_cycles<=0;
   stage_valid<=0;stage_x<=0;stage_y<=0;stage_sum<=0;capture_open_pulse<=0;capture_open_source<=0;capture_open_epoch<=0;capture_open_cfg<=0;dropped_frames<=0;
  end else begin
   ack1<=ack;ack2<=ack1;cancel1<=core_cancel;cancel2<=cancel1;generation1<=cancel_generation;generation2<=generation1;generation_ack<=generation2;stage_valid<=0;capture_open_pulse<=0;
   if(stage_valid&&stage_y[1:0]==3)writes<=writes+1'b1;
   if(state==CAPTURE)begin
    if(capture_csi_cycles!=32'hffffffff)capture_csi_cycles<=capture_csi_cycles+1'b1;
    else bad<=1;
   end
   if(state==OWNED&&ack2==req)state<=WAIT;
   if(state==CAPTURE&&(frame_error||!source_valid||!enabled||cancel2||source_epoch!=cepoch||cfg_revision!=ccfg||captured_generation!=generation2))bad<=1;
   if(sof)begin
    if(source_valid&&fresh_sof)begin have_sof<=1;last_id<=source_id;last_epoch<=source_epoch;end
    if(close_good)begin payload_id<=cid;payload_epoch<=cepoch;payload_cfg<=ccfg;payload_generation<=captured_generation;payload_capture_cycles<=capture_csi_cycles+1'b1;req<=~req;state<=OWNED;end
    else if(fresh_sof&&(state==WAIT||(state==OWNED&&ack2==req)||state==CAPTURE)&&enabled&&source_valid&&!frame_error&&!cancel2)begin
     state<=CAPTURE;cid<=source_id;cepoch<=source_epoch;ccfg<=cfg_revision;captured_generation<=generation2;groups<=1;writes<=0;bad<=s_eol;frame_done<=0;x<=1;y<=0;capture_csi_cycles<=0;
     stage_valid<=1;stage_x<=0;stage_y<=0;stage_sum<=hsum;
     capture_open_pulse<=1;capture_open_source<=source_id;capture_open_epoch<=source_epoch;capture_open_cfg<=cfg_revision;
    end else begin dropped_frames<=dropped_frames+1'b1;if(state==CAPTURE)bad<=1;end
   end else if(s_valid&&state==CAPTURE)begin
    if(frame_done||!eol_good||source_id!=cid||!source_valid||groups>=230400)bad<=1;
    if(!frame_done)begin
     groups<=groups+1'b1;
     if(!bad&&!frame_error&&source_valid&&source_id==cid&&eol_good&&!cancel2)begin stage_valid<=1;stage_x<=x;stage_y<=y;stage_sum<=hsum;end
     if(x==319)begin x<=0;if(y==719)begin frame_done<=1;y<=0;end else y<=y+1'b1;end else x<=x+1'b1;
    end
   end
  end
 end
 reg [1:0] meta_wait;reg pending;reg [31:0] lease_counter;
 always @(posedge core_clk or negedge prst)begin
  if(!prst)begin req1<=0;req2<=0;ack<=0;pending<=0;meta_wait<=0;owner_valid<=0;owner_source<=0;owner_epoch<=0;owner_cfg<=0;owner_lease<=0;lease_counter<=0;capture_age<=0;owner_capture_csi_cycles<=0;owner_pulse<=0;owner_revoke<=0;rd_valid<=0;rd_fault<=0;cancel_generation<=0;cancel_barrier<=0;cancel_drain_count<=0;generation_ack1<=0;generation_ack2<=0;end
  else begin
   req1<=req;req2<=req1;generation_ack1<=generation_ack;generation_ack2<=generation_ack1;owner_pulse<=0;owner_revoke<=0;rd_valid<=0;rd_fault<=0;
   // A generation is not a free-running event counter. Coalesce repeated
   // cancel pulses until CSI has observed this generation and all prior reqs
   // have drained. The old rising-edge toggle could alias after two pulses:
   // runs/cancel_burst01 preserves13 natural-frame resurrection failures.
   if(core_cancel&&!cancel_barrier)begin cancel_generation<=~cancel_generation;cancel_barrier<=1;cancel_drain_count<=0;end
   else if(cancel_barrier)begin
    if(!core_cancel&&generation_ack2==cancel_generation&&req2==ack&&!pending)begin
     if(cancel_drain_count==2)begin cancel_barrier<=0;cancel_drain_count<=0;end
     else cancel_drain_count<=cancel_drain_count+1'b1;
    end else cancel_drain_count<=0;
   end
   if(owner_valid&&capture_age<MAX_OWNER_CYCLES)capture_age<=capture_age+1'b1;
   if(rd_req)begin
    if(read_allowed)rd_valid<=1;
    else rd_fault<=1;
   end
   if(!cancel_barrier&&!core_cancel&&!owner_valid&&!pending&&req2!=ack)begin pending<=1;meta_wait<=0;end
   if(pending&&!cancel_barrier&&!core_cancel)begin
    if(meta_wait<2)meta_wait<=meta_wait+1'b1;
    else if(payload_generation!=cancel_generation)begin pending<=0;ack<=req2;owner_valid<=0;owner_revoke<=1;end
    else begin
     pending<=0;owner_valid<=1;owner_source<=payload_id;owner_epoch<=payload_epoch;owner_cfg<=payload_cfg;
     lease_counter<=lease_counter+1'b1;owner_lease<=lease_counter+1'b1;owner_capture_csi_cycles<=payload_capture_cycles;
     // Conservative age in core-cycle units: counting each103.52MHz capture
     // cycle as a75MHz core cycle OVERestimates elapsed capture time. Native
     // integration must retain core<=CSI or replace this explicit conversion.
     capture_age<=payload_capture_cycles;owner_pulse<=1;
    end
   end
   if(core_cancel||cancel_barrier||(owner_valid&&capture_age>=MAX_OWNER_CYCLES-1)||(release_valid&&owner_valid&&release_lease==owner_lease))begin
    owner_valid<=0;pending<=0;ack<=req2;rd_valid<=0;owner_revoke<=1;
   end
  end
 end
endmodule
