// Video metadata only: no pixel modification and no backpressure.
// Time origin: first valid RAW10 group following the native RAW frame boundary.
// Time destination: first final-HDMI DE pixel carrying an actual camera pixel.
// 1-us common 100-MHz timebase. All metadata bridges hold buses until toggle ACK.
module t06_latency_timebase #(
 parameter integer CLOCKS_PER_US=100, parameter [31:0] INITIAL_US=0
)(input clk,input rst_n,output reg [31:0] time_gray,output reg [31:0] time_us);
 localparam PW=(CLOCKS_PER_US<=1)?1:$clog2(CLOCKS_PER_US);
 reg [PW-1:0] prescale;
 wire [31:0] next_us=time_us+32'd1;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin time_us<=INITIAL_US;time_gray<=INITIAL_US^(INITIAL_US>>1);prescale<=0;end
  else if(prescale==CLOCKS_PER_US-1)begin
   prescale<=0;time_us<=next_us;time_gray<=next_us^(next_us>>1);
  end else prescale<=prescale+1'b1;
 end
endmodule

module t06_latency_frame_core #(
 parameter integer CLOCKS_PER_US=100,parameter [31:0] INITIAL_US=0,
 parameter [31:0] MAX_AGE_US=100000
)(
 input time_clk,time_rst_n,
 input csi_clk,csi_rst_n,raw_frame_start,raw_valid,
 input isp_frame_start,isp_valid,isp_sof_aligned,
 input [6:0] camera_display_style,
 input ddr_clk,ddr_rst_n,frame_boundary,frame_good,
 input [1:0] write_bank,latest_bank,input latest_valid,frame_acquire,
 input hdmi_clk,hdmi_rst_n,display_frame_start,final_de,final_source_valid,final_frame_bad,
 output reg measure_pulse,output reg [1:0] status,
 output reg [31:0] source_frame_id,capture_us,display_us,latency_us,
 output reg [31:0] new_frames,repeat_frames,skipped_source_frames,invalid_displays,
 output reg [31:0] stale_displays,partial_displays,captured_frames,
 output reg [31:0] committed_frames,dropped_frames,bad_metadata_frames,
 output reg current_frame_bad,
 output reg [6:0] display_style,
 output wire source_metadata_fault,output wire display_metadata_fault,
 output wire [31:0] csi_source_id,output wire csi_source_valid
);
 // Any domain reset flushes the whole metadata epoch. Pixel/ISP resets are not
 // driven by this module. Each metadata domain releases after two local edges.
 wire metadata_reset_n=csi_rst_n&&ddr_rst_n&&hdmi_rst_n&&time_rst_n;
 (* ASYNC_REG="TRUE" *) reg [1:0] c_reset,d_reset,h_reset;
 always @(posedge csi_clk or negedge metadata_reset_n)
  if(!metadata_reset_n)c_reset<=0;else c_reset<={c_reset[0],1'b1};
 always @(posedge ddr_clk or negedge metadata_reset_n)
  if(!metadata_reset_n)d_reset<=0;else d_reset<={d_reset[0],1'b1};
 always @(posedge hdmi_clk or negedge metadata_reset_n)
  if(!metadata_reset_n)h_reset<=0;else h_reset<={h_reset[0],1'b1};
 wire c_rst_n=c_reset[1],d_rst_n=d_reset[1],h_rst_n=h_reset[1];
 function [31:0] ungray(input [31:0] g);
  integer k;begin ungray[31]=g[31];for(k=30;k>=0;k=k-1)ungray[k]=ungray[k+1]^g[k];end
 endfunction
 function [31:0] satinc(input [31:0] a);begin satinc=&a?a:a+1'b1;end endfunction
 function [31:0] satadd(input [31:0] a,input [31:0] b);
  reg [32:0] s;begin s={1'b0,a}+{1'b0,b};satadd=s[32]?32'hffffffff:s[31:0];end
 endfunction
 wire [31:0] common_gray,common_us;
 t06_latency_timebase #(.CLOCKS_PER_US(CLOCKS_PER_US),.INITIAL_US(INITIAL_US)) u_time(
  .clk(time_clk),.rst_n(time_rst_n),.time_gray(common_gray),.time_us(common_us));
 (* ASYNC_REG="TRUE" *) reg [31:0] time_c1,time_c2,time_h1,time_h2;
 reg [2:0] c_time_ready,h_time_ready;
 always @(posedge csi_clk or negedge c_rst_n)
  if(!c_rst_n)begin time_c1<=0;time_c2<=0;c_time_ready<=0;end
  else begin time_c1<=common_gray;time_c2<=time_c1;c_time_ready<={c_time_ready[1:0],1'b1};end
 always @(posedge hdmi_clk or negedge h_rst_n)
  if(!h_rst_n)begin time_h1<=0;time_h2<=0;h_time_ready<=0;end
  else begin time_h1<=common_gray;time_h2<=time_h1;h_time_ready<={h_time_ready[1:0],1'b1};end

 // Source descriptor FIFO is local to CSI. Depth4 bounds ISP frame overlap.
 reg [31:0] q_id[0:3],q_time[0:3];
 reg [1:0] q_wr,q_rd;reg [2:0] q_count;
 reg [31:0] raw_id,isp_sequence,isp_raw_id;
 reg [31:0] captured_count,captured_gray;
 reg raw_pending,source_fault,isp_raw_valid,raw_seen;
 wire raw_capture=raw_valid&&(raw_pending||raw_frame_start);
 wire processed_first=isp_valid&&isp_sof_aligned;
 wire pop=processed_first&&q_count!=0&&!source_fault;
 // A full FIFO can replace its consumed head in the same cycle. Nonblocking
 // reads below see the old head even when q_wr==q_rd, preserving order.
 wire push=raw_capture&&(q_count<4||pop)&&!source_fault&&c_time_ready[2];
 wire [31:0] next_raw_id=raw_frame_start?raw_id+1'b1:raw_id;
 wire [31:0] current_sequence=isp_frame_start?isp_sequence+1'b1:isp_sequence;
 // Native ISP early is generated from the first RAW line. It must occur after
 // its RAW SOF and before the NEXT RAW SOF. This is an explicit pipeline contract
 // checked by the CSI/ISP integration regression; it is not AXIS tuser timing.
 wire [31:0] expected_raw_id=isp_frame_start?next_raw_id:isp_raw_id;
 wire expected_raw_valid=isp_frame_start?(raw_seen||raw_frame_start):isp_raw_valid;
 // Passive same-clock export of the existing RAW/ISP identity association.
 assign csi_source_id=isp_raw_id;
 assign csi_source_valid=c_rst_n&&isp_raw_valid&&!source_fault&&c_time_ready[2];
 reg src_req;reg [103:0] src_payload;
 reg src_ack;
 (* ASYNC_REG="TRUE" *) reg [1:0] src_ack_sync;
 always @(posedge csi_clk or negedge c_rst_n)
  if(!c_rst_n)src_ack_sync<=0;else src_ack_sync<={src_ack_sync[0],src_ack};
 wire src_busy=src_req!=src_ack_sync[1];
 always @(posedge csi_clk or negedge c_rst_n)begin
  if(!c_rst_n)begin
   q_wr<=0;q_rd<=0;q_count<=0;raw_id<=0;isp_sequence<=0;isp_raw_id<=0;isp_raw_valid<=0;
   raw_pending<=0;raw_seen<=0;source_fault<=0;src_req<=0;src_payload<=0;
   captured_count<=0;captured_gray<=0;
  end else begin
   if(raw_frame_start)begin raw_id<=raw_id+1'b1;raw_pending<=1;raw_seen<=1;end
   if(raw_capture)raw_pending<=0;
   if(raw_capture)begin
    captured_count<=captured_count+1'b1;
    captured_gray<=(captured_count+1'b1)^((captured_count+1'b1)>>1);
   end
   if(isp_frame_start)begin
    isp_sequence<=isp_sequence+1'b1;
    isp_raw_id<=next_raw_id;isp_raw_valid<=raw_seen||raw_frame_start;
   end
   if(raw_capture&&c_time_ready[2]&&q_count==4&&!pop)source_fault<=1;
   if(push)begin q_id[q_wr]<=next_raw_id;q_time[q_wr]<=ungray(time_c2);q_wr<=q_wr+1'b1;end
   if(pop)q_rd<=q_rd+1'b1;
   case({push,pop})2'b10:q_count<=q_count+1'b1;2'b01:q_count<=q_count-1'b1;default:q_count<=q_count;endcase
   if(processed_first)begin
    if(src_busy)source_fault<=1;
    else begin
     // When RAW and processed first coincide on an empty queue, bypass the FIFO.
     // Separate RAW identity from the ISP boundary sequence (which can include
     // a residual partial frame after DDR restart). Never silently shift IDs.
     if(pop)begin
      src_payload<={camera_display_style,expected_raw_valid&&q_id[q_rd]==expected_raw_id,current_sequence,q_id[q_rd],q_time[q_rd]};
      if(!expected_raw_valid||q_id[q_rd]!=expected_raw_id)source_fault<=1;
     end
     else if(push&&q_count==0)begin
      src_payload<={camera_display_style,expected_raw_valid&&next_raw_id==expected_raw_id,current_sequence,next_raw_id,ungray(time_c2)};
      if(!expected_raw_valid||next_raw_id!=expected_raw_id)source_fault<=1;
      q_rd<=q_rd+1'b1;q_count<=0;
     end else src_payload<={camera_display_style,1'b0,current_sequence,64'd0};
     src_req<=~src_req;
    end
   end
  end
 end

 // A bus payload remains stable through two toggle synchronizers and a settle
 // cycle, until ACK returns. No individual binary-bus bit synchronizers.
 (* ASYNC_REG="TRUE" *) reg [1:0] src_req_sync;
 reg src_settle;
 reg [31:0] current_ddr_sequence;
 reg seen_boundary,boundary_settle,pending_descriptor;
 reg [103:0] descriptor;
 reg [1:0] current_write_bank;
 // Only the current writer needs a staged descriptor; committed bank records
 // remain four-way. A single staging register avoids 3 redundant 96-bit copies.
 reg staging_valid;reg [1:0] staging_bank;
 reg published_valid[0:3];
 reg [31:0] staged_id,staged_time,staged_sequence;
 reg [6:0] staged_style,published_style[0:3];
 reg [31:0] published_id[0:3],published_time[0:3];
 reg display_req;reg [71:0] display_payload;
 reg display_ack,display_fault;
 (* ASYNC_REG="TRUE" *) reg [1:0] display_ack_sync;
 wire display_busy=display_req!=display_ack_sync[1];
 reg [31:0] d_committed,d_dropped,d_bad_metadata;
 reg stats_req,stats_ack;
 reg [95:0] stats_payload;
 (* ASYNC_REG="TRUE" *) reg [1:0] stats_ack_sync;
 wire stats_busy=stats_req!=stats_ack_sync[1];
 wire [95:0] current_stats={d_committed,d_dropped,d_bad_metadata};
 integer j;
 always @(posedge ddr_clk or negedge d_rst_n)begin
  if(!d_rst_n)begin
   src_req_sync<=0;src_ack<=0;src_settle<=0;current_ddr_sequence<=0;
   seen_boundary<=0;boundary_settle<=0;pending_descriptor<=0;descriptor<=0;
   current_write_bank<=0;display_req<=0;display_payload<=0;
   d_committed<=0;d_dropped<=0;d_bad_metadata<=0;
   stats_req<=0;stats_payload<=0;stats_ack_sync<=0;
   display_ack_sync<=0;display_fault<=0;
   staging_valid<=0;staging_bank<=0;staged_id<=0;staged_time<=0;staged_sequence<=0;staged_style<=0;
   for(j=0;j<4;j=j+1)begin
    published_valid[j]<=0;
    published_id[j]<=0;published_time[j]<=0;published_style[j]<=0;
   end
  end else begin
   src_req_sync<={src_req_sync[0],src_req};
   display_ack_sync<={display_ack_sync[0],display_ack};
   stats_ack_sync<={stats_ack_sync[0],stats_ack};
   // Latest-value coalescing. The held bus cannot change before returned ACK.
   // Counters themselves never lose events when HDMI is slow or stopped.
   if(!stats_busy&&stats_payload!=current_stats)begin
    stats_payload<=current_stats;stats_req<=~stats_req;
   end
   // Receive only into an empty pending slot. Otherwise leave request unacked
   // and its source bus held. A consume and a new receive cannot overwrite
   // pending_descriptor on the same edge.
   if(src_req_sync[1]!=src_ack&&!src_settle&&!pending_descriptor)src_settle<=1;
   else if(src_settle)begin
    descriptor<=src_payload;pending_descriptor<=1;src_ack<=src_req_sync[1];src_settle<=0;
   end
   if(frame_boundary)begin
    // write_bank here is the PRECEDING frame's bank, before manager NBAs.
    if(seen_boundary)begin
     if(frame_good)d_committed<=satinc(d_committed);
     else d_dropped<=satinc(d_dropped);
     if(frame_good&&staging_valid&&staging_bank==write_bank&&staged_sequence==current_ddr_sequence)begin
      published_valid[write_bank]<=1;published_id[write_bank]<=staged_id;
      published_time[write_bank]<=staged_time;published_style[write_bank]<=staged_style;
     end else begin
      published_valid[write_bank]<=0;
      // A rejected camera frame is a video drop, not a metadata error.
      if(frame_good)d_bad_metadata<=satinc(d_bad_metadata);
     end
    end
    seen_boundary<=1;current_ddr_sequence<=current_ddr_sequence+1'b1;boundary_settle<=1;
   end else if(boundary_settle)begin
    // Manager has now allocated the NEXT write bank.
    current_write_bank<=write_bank;staging_valid<=0;
    published_valid[write_bank]<=0;boundary_settle<=0;
   end else if(pending_descriptor&&seen_boundary)begin
    if(descriptor[95:64]==current_ddr_sequence)begin
     staging_valid<=descriptor[96];staging_bank<=current_write_bank;
     staged_sequence<=descriptor[95:64];
     staged_id<=descriptor[63:32];staged_time<=descriptor[31:0];staged_style<=descriptor[103:97];
     pending_descriptor<=0;
    end else if((current_ddr_sequence-descriptor[95:64])<32'h80000000)begin
     pending_descriptor<=0; // delayed old descriptor must not label a new frame
    end
   end
   if(frame_acquire)begin
    // This is exactly the bank video_out samples on its acquire edge.
    // Do not sample manager.read_bank, whose NBA changes on this same edge.
    if(display_busy)display_fault<=1;
    else begin
     display_payload<={published_style[latest_bank],latest_valid&&published_valid[latest_bank],published_id[latest_bank],published_time[latest_bank]};
     display_req<=~display_req;
    end
   end
  end
 end

 (* ASYNC_REG="TRUE" *) reg [1:0] display_req_sync,display_fault_sync,source_fault_sync;
 reg display_settle,descriptor_ready,descriptor_valid,first_seen,vs_last;
 reg frame_any_de,frame_measure_valid,frame_bad_seen;
 (* ASYNC_REG="TRUE" *) reg [1:0] stats_req_sync;
 (* ASYNC_REG="TRUE" *) reg [31:0] captured_h1,captured_h2;
 reg stats_settle;
 reg [31:0] hdmi_id,hdmi_capture,last_id;
 reg [6:0] hdmi_style;
 reg last_id_valid;
 wire [31:0] sampled_display_us=ungray(time_h2);
 wire [31:0] age_us=sampled_display_us-hdmi_capture;
 wire [31:0] id_delta=hdmi_id-last_id;
 assign source_metadata_fault=source_fault_sync[1];
 assign display_metadata_fault=display_fault_sync[1];
 always @(posedge hdmi_clk or negedge h_rst_n)begin
  if(!h_rst_n)begin
   display_req_sync<=0;display_ack<=0;display_settle<=0;
   display_fault_sync<=0;source_fault_sync<=0;descriptor_ready<=0;descriptor_valid<=0;
   frame_any_de<=0;frame_measure_valid<=0;frame_bad_seen<=0;current_frame_bad<=0;
   stats_req_sync<=0;stats_ack<=0;stats_settle<=0;captured_h1<=0;captured_h2<=0;
   captured_frames<=0;committed_frames<=0;dropped_frames<=0;bad_metadata_frames<=0;
   first_seen<=0;vs_last<=0;hdmi_id<=0;hdmi_capture<=0;hdmi_style<=0;display_style<=0;last_id<=0;last_id_valid<=0;
   status<=0;source_frame_id<=0;capture_us<=0;display_us<=0;latency_us<=0;
   new_frames<=0;repeat_frames<=0;skipped_source_frames<=0;invalid_displays<=0;measure_pulse<=0;
   stale_displays<=0;partial_displays<=0;
  end else begin
   display_req_sync<={display_req_sync[0],display_req};
   display_fault_sync<={display_fault_sync[0],display_fault};
   source_fault_sync<={source_fault_sync[0],source_fault};
   captured_h1<=captured_gray;captured_h2<=captured_h1;
   captured_frames<=ungray(captured_h2);
   stats_req_sync<={stats_req_sync[0],stats_req};
   if(stats_req_sync[1]!=stats_ack&&!stats_settle)stats_settle<=1;
   else if(stats_settle)begin
    committed_frames<=stats_payload[95:64];dropped_frames<=stats_payload[63:32];
    bad_metadata_frames<=stats_payload[31:0];
    stats_ack<=stats_req_sync[1];stats_settle<=0;
   end
   vs_last<=display_frame_start;measure_pulse<=0;
   if(final_de)begin
    frame_any_de<=1;
    // A frame with no source pixel cannot keep displaying an older valid LAT.
    // A successful first-source measurement below supersedes this assignment.
    if(!frame_any_de)begin status<=0;latency_us<=0;end
   end
   if(final_de&&final_frame_bad)begin frame_bad_seen<=1;current_frame_bad<=1;end
   if(display_frame_start&&!vs_last)begin
    // Close the preceding rendered frame once, including frames that never
    // produced a source pixel. Reset/blank startup periods have no DE to count.
    if(frame_any_de&&!frame_measure_valid)invalid_displays<=satinc(invalid_displays);
    if(frame_any_de&&frame_bad_seen)partial_displays<=satinc(partial_displays);
    if(frame_any_de&&!frame_measure_valid)begin status<=0;latency_us<=0;end
    first_seen<=0;descriptor_ready<=0;frame_any_de<=0;
    frame_measure_valid<=0;frame_bad_seen<=0;current_frame_bad<=0;
   end
   if(display_req_sync[1]!=display_ack&&!display_settle)display_settle<=1;
   else if(display_settle)begin
    descriptor_valid<=display_payload[64];hdmi_id<=display_payload[63:32];
    hdmi_capture<=display_payload[31:0];hdmi_style<=display_payload[71:65];descriptor_ready<=1;
    display_ack<=display_req_sync[1];display_settle<=0;
   end
   if(final_de&&final_source_valid&&!first_seen)begin
    first_seen<=1;measure_pulse<=1;display_us<=sampled_display_us;
    source_frame_id<=hdmi_id;capture_us<=hdmi_capture;display_style<=hdmi_style;
    if(!h_time_ready[2]||!descriptor_ready||!descriptor_valid||display_fault_sync[1]||source_fault_sync[1]||age_us[31]||(last_id_valid&&id_delta[31]))begin
     status<=0;latency_us<=0;
    end else begin
     frame_measure_valid<=1;
     latency_us<=age_us;
     status<=age_us>MAX_AGE_US?2'd3:(last_id_valid&&hdmi_id==last_id?2'd2:2'd1);
     if(age_us>MAX_AGE_US)stale_displays<=satinc(stale_displays);
     if(last_id_valid&&hdmi_id==last_id)repeat_frames<=satinc(repeat_frames);
     else begin
      new_frames<=satinc(new_frames);
      if(last_id_valid&&id_delta>1&&!id_delta[31])skipped_source_frames<=satadd(skipped_source_frames,id_delta-1'b1);
     end
     last_id<=hdmi_id;last_id_valid<=1;
    end
   end
  end
 end
endmodule

