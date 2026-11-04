// MOT15 held-bus mailbox. No pixel/DDR requests or video ready output.
module t06_motion_link #(
 parameter WIDTH=1280,HEIGHT=720,MAX_AGE_FRAMES=6,ENABLE_SHARED_ANALYSIS=0
)(
 input csi_clk,hdmi_clk,arst_n,
 input [95:0] rgb4,input [31:0] gray4,input gray_valid,gray_sof,gray_eol,frame_error,
 input [31:0] source_id,input source_id_valid,
 input vs,measure_pulse,input [31:0] display_id,input display_good,
 output [2:0] state,output stable,output [13:0] changed,
 output [15:0] events,output [7:0] xmin,xmax,output [6:0] ymin,ymax,
 output result_valid,output analysis_valid,output [15:0] analysis_rgb_sig,analysis_gray_sig
);
 wire metadata_reset_n=arst_n;
 (* ASYNC_REG="TRUE" *) reg [1:0] c_release,h_release;
 always @(posedge csi_clk or negedge metadata_reset_n)
  if(!metadata_reset_n)c_release<=0;else c_release<={c_release[0],1'b1};
 always @(posedge hdmi_clk or negedge metadata_reset_n)
  if(!metadata_reset_n)h_release<=0;else h_release<={h_release[0],1'b1};
 wire crst=c_release[1],hrst=h_release[1];
 wire [95:0] shared_rgb;wire [31:0] shared_gray,shared_id;
 wire shared_valid,shared_sof,shared_eol,shared_source_valid,shared_error;
 wire [8:0] shared_x;wire [9:0] shared_y;
 wire analysis_pulse,analysis_complete;wire [31:0] analysis_id;
 wire [15:0] rgb_sig,gray_sig;
 generate if(ENABLE_SHARED_ANALYSIS)begin:g_analysis
  t06_analysis_stream #(.WIDTH(WIDTH),.HEIGHT(HEIGHT)) u_stream(
   .clk(csi_clk),.rst_n(crst),.s_rgb(rgb4),.s_gray(gray4),
   .s_valid(gray_valid),.s_sof(gray_sof),.s_eol(gray_eol),.frame_error(frame_error),
   .source_id(source_id),.source_id_valid(source_id_valid),
   .m_rgb(shared_rgb),.m_gray(shared_gray),.m_valid(shared_valid),
   .m_sof(shared_sof),.m_eol(shared_eol),.m_group_x(shared_x),.m_y(shared_y),
   .m_source_id(shared_id),.m_source_valid(shared_source_valid),.m_error(shared_error),
   .frame_pulse(analysis_pulse),.frame_complete(analysis_complete),.frame_id(analysis_id),
   .rgb_signature(rgb_sig),.gray_signature(gray_sig));
 end else begin:g_legacy
  assign shared_rgb=rgb4;assign shared_gray=gray4;assign shared_id=source_id;
  assign shared_valid=gray_valid;assign shared_sof=gray_sof;assign shared_eol=gray_eol;
  assign shared_source_valid=source_id_valid;assign shared_error=frame_error;
  assign shared_x=0;assign shared_y=0;assign analysis_pulse=0;
  assign analysis_complete=1;assign analysis_id=0;assign rgb_sig=0;assign gray_sig=0;
 end endgenerate
 wire cp,cs;wire [2:0] cstate;wire [31:0] cid;
 wire [13:0] cc;wire [15:0] ce;wire [7:0] cx0,cx1;wire [6:0] cy0,cy1;
 t06_motion_core #(.WIDTH(WIDTH),.HEIGHT(HEIGHT),.USE_SHARED_COORDS(ENABLE_SHARED_ANALYSIS)) u_core(
  .clk(csi_clk),.rst_n(crst),.gray4(shared_gray),.s_valid(shared_valid),.s_sof(shared_sof),.s_eol(shared_eol),
  .frame_error(shared_error),.source_id(shared_id),.source_id_valid(shared_source_valid),
  .shared_group_x(shared_x),.shared_y(shared_y),
  .result_pulse(cp),.result_state(cstate),.result_id(cid),.changed(cc),
  .xmin(cx0),.xmax(cx1),.ymin(cy0),.ymax(cy1),.result_stable(cs),.events(ce));
 wire summary_good=!ENABLE_SHARED_ANALYSIS||(analysis_complete&&analysis_id==cid);
 wire [128:0] current_bus={summary_good,rgb_sig,gray_sig,cstate,cs,cc,ce,cx0,cx1,cy0,cy1,cid};
 reg [128:0] held_bus;
 reg req,ack,source_quarantine,rearm_pending,held_rearm,rearm_eligible;
 (* ASYNC_REG="TRUE" *) reg [1:0] ack_sync,req_sync,unsafe_sync;
 wire busy=req!=ack_sync[1];
 always @(posedge csi_clk or negedge crst)begin
  if(!crst)begin held_bus<=0;held_rearm<=0;req<=0;ack_sync<=0;source_quarantine<=1;rearm_pending<=0;rearm_eligible<=0;end
  else begin
   ack_sync<={ack_sync[0],ack};
   // Latest complete result coalesces only while bus is not in flight.
   if(!busy&&(held_bus!=current_bus||(source_quarantine&&rearm_eligible&&!rearm_pending)))begin
    held_bus<=current_bus;req<=~req;
    held_rearm<=source_quarantine&&rearm_eligible&&summary_good&&cstate>=2&&cstate<=4;
    if(source_quarantine&&rearm_eligible&&summary_good&&cstate>=2&&cstate<=4)rearm_pending<=1;
   end
   // Re-arm only after a new valid comparison was really received and ACKed.
   // Stable is a separate three-quiet-frame judgment, never a re-arm condition.
   if(!busy&&rearm_pending)begin source_quarantine<=0;rearm_pending<=0;end
   if(cp&&cstate>=2&&cstate<=4&&summary_good)rearm_eligible<=1;
   // Only a genuinely newly completed comparison can re-arm after a fault.
   if(shared_error||(cp&&(cstate<2||!summary_good)))begin
    source_quarantine<=1;rearm_pending<=0;rearm_eligible<=0;
   end
  end
 end
 reg settle,vs_prev;
 reg [128:0] received,previous;
 // Ages belong to each descriptor, never to unrelated mailbox activity.
 reg [2:0] age,previous_age,selected_age;
 reg [63:0] selected;reg [32:0] selected_analysis;
 reg selected_valid,received_valid,previous_valid,unsafe_prev;
 // A newer descriptor for an ID is authoritative even when invalid.
 // Do not resurrect an older same-ID descriptor after an ID reuse/WARMUP.
 wire [63:0] chosen=received[31:0]==display_id?received[95:32]:previous[95:32];
 wire [2:0] chosen_age_base=received[31:0]==display_id?age:previous_age;
 wire [2:0] chosen_age=(vs&&!vs_prev&&chosen_age_base!=7)?chosen_age_base+1'b1:chosen_age_base;
 wire [32:0] chosen_analysis=received[31:0]==display_id?received[128:96]:previous[128:96];
 wire matched=(received_valid&&received[31:0]==display_id)||
              (previous_valid&&previous[31:0]==display_id&&received[31:0]!=display_id);
 always @(posedge hdmi_clk or negedge hrst)begin
  if(!hrst)begin
   req_sync<=0;unsafe_sync<=3;ack<=0;settle<=0;received<=0;previous<=0;
   age<=7;previous_age<=7;selected_age<=7;vs_prev<=0;selected<=0;selected_analysis<=0;selected_valid<=0;
   received_valid<=0;previous_valid<=0;unsafe_prev<=1;
  end else begin
   req_sync<={req_sync[0],req};unsafe_sync<={unsafe_sync[0],source_quarantine};
   vs_prev<=vs;unsafe_prev<=unsafe_sync[1];
   if(unsafe_sync[1]&&!unsafe_prev)begin received_valid<=0;previous_valid<=0;end
   if(unsafe_sync[1])selected_valid<=0;
   if(vs&&!vs_prev)begin
    if(age!=7)age<=age+1'b1;
    if(previous_age!=7)previous_age<=previous_age+1'b1;
    if(selected_age!=7)selected_age<=selected_age+1'b1;
    selected_valid<=0;
   end
   if(req_sync[1]!=ack&&!settle)settle<=1;
   else if(settle)begin
    previous<=received;received<=held_bus;ack<=req_sync[1];settle<=0;age<=0;
    // A simultaneous raster edge counts for the old descriptor being copied.
    previous_age<=(vs&&!vs_prev&&age!=7)?age+1'b1:age;
    // A re-arm receipt discards every pre-fault descriptor, including late ones.
    previous_valid<=held_rearm?1'b0:received_valid;
    received_valid<=held_bus[128]&&held_bus[95:93]>=2&&held_bus[95:93]<=4&&
                    (!unsafe_sync[1]||held_rearm);
   end
   // LF14 publishes ID/status with measure_pulse; on this edge its NBAs from
   // the prior edge are already visible. Freeze once; late results never relabel.
   if(measure_pulse)begin
    selected<=chosen;selected_analysis<=chosen_analysis;selected_age<=chosen_age;
    selected_valid<=matched&&chosen[63:61]>=2&&chosen[63:61]<=4&&
                    chosen_age<MAX_AGE_FRAMES&&!unsafe_sync[1]&&display_good;
   end
   if(unsafe_sync[1]&&!unsafe_prev)begin received_valid<=0;previous_valid<=0;selected_valid<=0;end
  end
 end
 assign result_valid=selected_valid&&!unsafe_sync[1]&&selected_age<MAX_AGE_FRAMES&&display_good;
 assign analysis_valid=ENABLE_SHARED_ANALYSIS&&result_valid&&selected_analysis[32];
 assign analysis_rgb_sig=analysis_valid?selected_analysis[31:16]:16'd0;
 assign analysis_gray_sig=analysis_valid?selected_analysis[15:0]:16'd0;
 assign state=result_valid?selected[63:61]:3'd0;
 assign stable=result_valid&&selected[60];
 assign changed=selected[59:46];assign events=selected[45:30];
 assign xmin=selected[29:22];assign xmax=selected[21:14];
 assign ymin=selected[13:7];assign ymax=selected[6:0];
endmodule
