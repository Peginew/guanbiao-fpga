// Owned live CSI ROI -> HCLK quality/CRC -> hard-MCU AHB reader.
// No pressure permission is granted here. CORE invalidates immediately on
// cancellation; the immutable RAM lease is retained until true CPU retirement.
module meter_mcu_live_roi #(
 // MAX_RESULT_AGE is retained only for source/API compatibility; not a kill.
 parameter WIDTH=1280,HEIGHT=720,MAX_CAPTURE_WAIT=20000000,MAX_RESULT_AGE=10000000
)(
 input wire csi_clk,clk,mcu_clk,arst_n,
 input wire [31:0] observer_context,
 input wire [31:0] gray4,input wire gray_valid,gray_sof,gray_eol,frame_error,
 input wire [31:0] source_id,input wire source_id_valid,capture_frame_allowed,
 input wire enabled,cancel,input wire [15:0] active_target,
 input wire [31:0] active_config,session_epoch,
 input wire req_valid,output wire req_ready,
 input wire [10:0] req_x0,input wire [9:0] req_y0,input wire [2:0] req_stride,
 input wire [6:0] req_radius,input wire [31:0] req_hint_source,
 input wire [15:0] req_target,input wire [31:0] req_config,
 output wire busy,capture_armed,platform_armed,
 // Read-only CORE register taps, deliberately independent of cancel/kill.
 output wire owned_roi_good,output wire [31:0] owned_roi_source,
 output reg result_valid,input wire result_ready,
 output reg [95:0] result_token,output reg [31:0] result_hint_source,
 output reg [15:0] result_target,output reg [31:0] result_config,
 output reg [10:0] result_x0,output reg [9:0] result_y0,
 output reg [2:0] result_stride,output reg [6:0] result_radius,
 output reg [31:0] result_source_crc32,result_crc32,result_bytes,result_code,
 output reg result_checksum_ok,result_quality_ok,
 output reg [15:0] result_psi_q8,output reg result_psi_valid,
 output reg [7:0] quality_mean,output reg [21:0] quality_gradient,
 output reg [4:0] quality_reason,output wire [4:0] stage_flags,
 output reg [4:0] status_reason,output reg [120:0] result_capture_debug,
 output wire [31:0] result_age_cycles,
 input wire [30:0] haddr,input wire [1:0] htrans,input wire hwrite,
 input wire [2:0] hsize,input wire [31:0] hwdata,
 output wire [31:0] hrdata,output wire [1:0] hresp,output wire hready,
 // Must represent actual master-reset/bus-quiescence in HCLK. A software
 // timeout or a debug observation is not sufficient. Tie0 if unimplemented.
 input wire cpu_reset_quiescent
);
 (* ASYNC_REG="TRUE" *) reg [1:0] core_reset,mc_reset;
 always @(posedge clk or negedge arst_n)if(!arst_n)core_reset<=0;else core_reset<={core_reset[0],1'b1};
 always @(posedge mcu_clk or negedge arst_n)if(!arst_n)mc_reset<=0;else mc_reset<={mc_reset[0],1'b1};
 wire rst_n=core_reset[1],mrst_n=mc_reset[1];
 localparam C_IDLE=0,C_CAPTURE=1,C_WAIT=2,C_RETSETTLE=3,C_RESULT=4,C_RELEASE=5,C_DRAIN=6;
 reg [2:0] cs;
 reg [15:0] owner_target;reg [31:0] owner_config,owner_epoch,owner_job,job_counter,age;
 reg offer_held,job_live,offer_toggle,ret_ack,age_active;
 reg [174:0] offer_payload;
 (* ASYNC_REG="TRUE" *) reg [1:0] ret_sync,cpu_reset_sync,armed_sync;
 reg ret_seen;
 reg [4:0] stage_passed;
 wire owner_bad=owner_target!=active_target||owner_config!=active_config||owner_epoch!=session_epoch;
 wire retained_context_bad=(result_checksum_ok||(|stage_passed))&&
  (result_target!=active_target||result_config!=active_config||result_token[95:64]!=session_epoch);
 wire core_kill=!enabled||cancel||(cs!=C_IDLE&&owner_bad)||retained_context_bad;
 assign stage_flags=core_kill?5'd0:stage_passed;
 assign owned_roi_good=stage_passed[0];
 assign owned_roi_source=result_token[63:32];
 assign result_age_cycles=age;
 wire cap_ready,cap_busy,cap_commit,cap_lease,cap_good,cap_armed;
 wire [4:0] cap_reason;wire [52:0] cap_diag;
 wire [10:0] cap_x0;wire [9:0] cap_y0;wire [2:0] cap_stride;wire [6:0] cap_radius;
 wire [31:0] cap_source,cap_hint,cap_config;wire [15:0] cap_target;
 reg cap_release;
 // Before publication there is no CPU owner. After publication CORE must not
 // propagate kill into capture.cancel: that would release CSI too early.
 wire cap_cancel=core_kill&&!offer_held;
 wire take_req=req_valid&&req_ready;
 assign req_ready=rst_n&&armed_sync[1]&&cs==C_IDLE&&cap_ready&&!core_kill&&!cpu_reset_sync[1]&&
  req_target==active_target&&req_config==active_config&&session_epoch!=0&&job_counter!=32'hffffffff;
 assign busy=cs!=C_IDLE||cap_busy;
 assign capture_armed=cap_armed&&cs==C_CAPTURE&&!core_kill;
 wire rd_en,rd_authority;wire [13:0] rd_addr;wire [7:0] rd_data;
 t06_meter_roi_capture_mcu #(.WIDTH(WIDTH),.HEIGHT(HEIGHT),.MAX_CAPTURE_WAIT(MAX_CAPTURE_WAIT)) capture(
  .csi_clk(csi_clk),.clk(clk),.arst_n(arst_n),.rd_clk(mcu_clk),.rd_rst_n(mrst_n),.rd_authority(rd_authority),
  .gray4(gray4),.gray_valid(gray_valid),.gray_sof(gray_sof),.gray_eol(gray_eol),.frame_error(frame_error),
  .source_id(source_id),.source_id_valid(source_id_valid),.capture_frame_allowed(capture_frame_allowed),
  .req_valid(take_req),.req_ready(cap_ready),.req_x0(req_x0),.req_y0(req_y0),.req_stride(req_stride),
  .req_radius(req_radius),.req_hint_source(req_hint_source),.req_target(req_target),.req_config(req_config),
  .cancel(cap_cancel),.lease_release(cap_release),.busy(cap_busy),.capture_armed(cap_armed),
  .commit_pulse(cap_commit),.lease_valid(cap_lease),.capture_good(cap_good),.capture_reason(cap_reason),
  .captured_x0(cap_x0),.captured_y0(cap_y0),.captured_stride(cap_stride),.captured_radius(cap_radius),
  .captured_source(cap_source),.captured_hint_source(cap_hint),.captured_config(cap_config),.captured_target(cap_target),
  .rd_en(rd_en),.rd_addr(rd_addr),.rd_data(rd_data),.captured_diagnostics(cap_diag));

 localparam H_IDLE=0,H_SETTLE=1,H_QSTART=2,H_QWAIT=3,H_OFFER=4,H_CPU=5,H_QUIET=6,H_RETURN=7,H_ACK=8;
 reg [3:0] hs;
 (* ASYNC_REG="TRUE" *) reg [1:0] offer_sync,live_sync,retack_sync;
 reg offer_seen,ret_toggle,local_live;reg [1:0] quiet_delay;
 reg [95:0] token;reg [15:0] target;reg [31:0] config_id;
 reg [10:0] x0;reg [9:0] y0;reg [2:0] stride;reg [6:0] radius;
 reg [95:0] return_token;reg [15:0] return_target;reg [31:0] return_config;
 reg [31:0] return_source_crc,return_cpu_crc,return_bytes,return_code;
 reg [15:0] return_psi_q8;reg return_psi_valid;
 wire [15:0] br_psi_q8;wire br_psi_valid;
 reg [7:0] return_mean;reg [21:0] return_gradient;reg [4:0] return_qreason,return_kind;reg return_qgood;
 wire h_revoke=!live_sync[1]||cpu_reset_quiescent;
 wire qstart=hs==H_QSTART&&!h_revoke;
 wire qcancel=h_revoke||hs==H_QUIET;
 wire qrd,qbusy,qdone,qgood,qcomplete;wire [13:0] qa,qdark,qbright;
 wire [7:0] qmean;wire [21:0] qgradient;wire [4:0] qreason;wire [31:0] hw_crc;
 meter_mcu_quality_crc128 quality(.clk(mcu_clk),.rst_n(mrst_n),.start(qstart),.cancel(qcancel),
  .rd_en(qrd),.rd_addr(qa),.rd_data(rd_data),.busy(qbusy),.done(qdone),.quality_ok(qgood),
  .mean_gray(qmean),.dark_count(qdark),.bright_count(qbright),.gradient_sum(qgradient),.reason(qreason),
  .source_crc32(hw_crc),.scan_complete(qcomplete));
 wire br_armed;
 // Compact CORE32 history has global MCU lifetime and is qualified sinceARM.
 // All fields are passive; parent video reset is data and cannot erase history.
 reg [9:0] observer_seen;reg [8:0] observer_last_decide;
 reg [11:0] observer_last_bad_causes;reg observer_seen_bad;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin observer_seen<=0;observer_last_decide<=0;observer_last_bad_causes<=0;observer_seen_bad<=0;end
  else if(armed_sync[1])begin
   // Same two-state sticky truth table, shared ARM enable for denser packing.
   observer_seen<=observer_seen|{observer_context[5:2],(cap_commit&&cap_good),cap_commit,cap_armed,take_req,observer_context[1:0]};
   if(observer_context[2])observer_last_decide<=observer_context[14:6];
   if(cap_commit&&!cap_good)begin observer_seen_bad<=1;observer_last_bad_causes<=cap_diag[52:41];end
  end
 end
 wire [31:0] observer_seq;wire [95:0] observer_snapshot;
 wire [31:0] observer_packed={observer_seen_bad,observer_last_bad_causes,observer_last_decide,observer_seen};
 meter_mcu_roi_observer observer(.s_clk(clk),.d_clk(mcu_clk),.arst_n(arst_n),.armed(br_armed),
  .s_word(observer_packed),.d_seq(observer_seq),.d_snapshot(observer_snapshot));
 assign platform_armed=armed_sync[1];
 wire br_ready,br_busy,br_visible,br_claimed,br_revoked,br_release,br_rejected;
 wire [7:0] br_error;wire br_rd;wire [13:0] br_addr;
 wire br_valid;wire [95:0] br_token;wire [15:0] br_target;wire [31:0] br_config,br_crc,br_bytes,br_code;
 wire observer_offer_accepted;
 wire observer_offer_valid=hs==H_OFFER&&!h_revoke;
 wire observer_active_revoke=br_revoked||(h_revoke&&(hs==H_SETTLE||hs==H_QSTART||hs==H_QWAIT||hs==H_OFFER||hs==H_CPU));
 reg [5:0] observer_h_seen;reg observer_h_frozen;reg [31:0] observer_hword;
 always @(posedge mcu_clk or negedge mrst_n)begin
  if(!mrst_n)begin observer_h_seen<=0;observer_h_frozen<=0;observer_hword<=0;end
  else if(!observer_h_frozen)begin
   if(br_armed)observer_h_seen<=observer_h_seen|{observer_active_revoke,observer_offer_accepted,observer_offer_valid,(qdone&&qcomplete),qdone,qstart};
   if(observer_seq!=0)begin
    observer_hword<={21'd0,hs,observer_h_seen,1'b1};
    observer_h_frozen<=1;
   end
  end
 end
 wire br_result_ready=hs==H_CPU&&!h_revoke;
 wire br_cancel=h_revoke||hs==H_QUIET;
 meter_mcu_roi_ahb_live bridge(.clk(mcu_clk),.rst_n(mrst_n),.haddr(haddr),.htrans(htrans),.hwrite(hwrite),
  .hsize(hsize),.hwdata(hwdata),.hrdata(hrdata),.hresp(hresp),.hready(hready),
  .observer_seq(observer_seq),.observer_snapshot(observer_snapshot),.observer_hword(observer_hword),.observer_offer_accepted(observer_offer_accepted),
  .source_crc32(hw_crc),.quality_flags({25'd0,qreason,qgood,qcomplete}),
  .quality_mean({24'd0,qmean}),.quality_gradient({10'd0,qgradient}),.quality_counts({2'd0,qbright,2'd0,qdark}),
  .offer_valid(hs==H_OFFER&&!h_revoke),.offer_ready(br_ready),.offer_token(token),.offer_target(target),
  .offer_config(config_id),.offer_x0(x0),.offer_y0(y0),.offer_stride(stride),.offer_radius(radius),
  .roi_live(local_live&&!h_revoke),.cancel(br_cancel),.cpu_reset_quiescent(cpu_reset_quiescent),
  .session_busy(br_busy),.owner_visible(br_visible),.cpu_claimed(br_claimed),.revoked(br_revoked),
  .release_pulse(br_release),.offer_rejected(br_rejected),.last_error(br_error),
  .roi_rd_en(br_rd),.roi_rd_addr(br_addr),.roi_rd_data(rd_data),
  .checksum_result_valid(br_valid),.checksum_result_ready(br_result_ready),.checksum_result_token(br_token),
  .checksum_result_target(br_target),.checksum_result_config(br_config),.checksum_crc32(br_crc),
  .checksum_psi_q8(br_psi_q8),.checksum_psi_valid(br_psi_valid),
  .checksum_bytes(br_bytes),.checksum_code(br_code),.platform_armed(br_armed));
 // Exactly one read clock and one local client at a time. Quality runs first;
 // quality failure remains metadata and never suppresses complete ROI analysis.
 assign rd_authority=mrst_n&&!h_revoke&&(hs==H_QWAIT||hs==H_CPU);
 assign rd_en=rd_authority&&((hs==H_QWAIT&&qrd)||(hs==H_CPU&&br_rd));
 assign rd_addr=hs==H_QWAIT?qa:br_addr;

 always @(posedge mcu_clk or negedge mrst_n)begin
  if(!mrst_n)begin
   offer_sync<=0;live_sync<=0;retack_sync<=0;offer_seen<=0;ret_toggle<=0;local_live<=0;hs<=H_IDLE;quiet_delay<=0;
   token<=0;target<=0;config_id<=0;x0<=0;y0<=0;stride<=0;radius<=0;
   return_token<=0;return_target<=0;return_config<=0;return_source_crc<=0;return_cpu_crc<=0;return_bytes<=0;return_code<=0;return_psi_q8<=0;return_psi_valid<=0;
   return_mean<=0;return_gradient<=0;return_qreason<=0;return_qgood<=0;return_kind<=0;
  end else begin
   offer_sync<={offer_sync[0],offer_toggle};live_sync<={live_sync[0],job_live};retack_sync<={retack_sync[0],ret_ack};
   if(h_revoke)local_live<=0;
   case(hs)
    H_IDLE:if(offer_sync[1]!=offer_seen)hs<=H_SETTLE;
    H_SETTLE:begin
     // One extra HCLK after the synchronized request; sender retains this
     // whole bundle until the matching return/ack retirement.
     {token,target,config_id,x0,y0,stride,radius}<=offer_payload;
     offer_seen<=offer_sync[1];local_live<=!h_revoke;
     return_cpu_crc<=0;return_bytes<=0;return_code<=0;return_psi_q8<=0;return_psi_valid<=0;return_source_crc<=0;
     return_mean<=0;return_gradient<=0;return_qreason<=0;return_qgood<=0;
     return_kind<=h_revoke?5'd13:5'd0;
     if(h_revoke)begin quiet_delay<=0;hs<=H_QUIET;end else hs<=H_QSTART;
    end
    H_QSTART:if(h_revoke)begin return_kind<=13;quiet_delay<=0;hs<=H_QUIET;end else hs<=H_QWAIT;
    H_QWAIT:if(h_revoke)begin return_kind<=13;quiet_delay<=0;hs<=H_QUIET;end
     else if(qdone)begin
      return_source_crc<=hw_crc;return_mean<=qmean;return_gradient<=qgradient;return_qreason<=qreason;return_qgood<=qgood;
      if(!qcomplete)begin return_kind<=16;quiet_delay<=0;hs<=H_QUIET;end else hs<=H_OFFER;
     end
    H_OFFER:if(h_revoke)begin return_kind<=13;quiet_delay<=0;hs<=H_QUIET;end else if(br_ready)hs<=H_CPU;
    H_CPU:begin
     if(h_revoke)begin return_kind<=13;quiet_delay<=0;hs<=H_QUIET;end
     else if(br_rejected)begin return_kind<=16;quiet_delay<=0;hs<=H_QUIET;end
     else if(br_valid&&br_result_ready)begin
      return_cpu_crc<=br_crc;return_bytes<=br_bytes;return_code<=br_code;return_psi_q8<=br_psi_q8;return_psi_valid<=br_psi_valid;
      return_kind<=(br_token!=token||br_target!=target||br_config!=config_id||br_bytes!=16384)?5'd16:
       br_crc==hw_crc?5'd0:5'd1;
      quiet_delay<=0;hs<=H_QUIET;
     end
    end
    H_QUIET:begin
     // No native request is issued here. Bridge retains a claimed tombstone
     // until actual QUIE/reset. Two local clocks drain a last quality return.
     local_live<=0;
     if(h_revoke)return_kind<=13;
     if(quiet_delay!=3)quiet_delay<=quiet_delay+1'b1;
     if(quiet_delay>=2&&!qbusy&&!br_busy)hs<=H_RETURN;
    end
    H_RETURN:begin
     return_token<=token;return_target<=target;return_config<=config_id;
     ret_toggle<=~ret_toggle;hs<=H_ACK;
    end
    H_ACK:if(retack_sync[1]==ret_toggle)hs<=H_IDLE;
    default:begin local_live<=0;return_kind<=16;quiet_delay<=0;hs<=H_QUIET;end
   endcase
  end
 end

 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   cs<=C_IDLE;owner_target<=0;owner_config<=0;owner_epoch<=0;owner_job<=0;job_counter<=0;age<=0;age_active<=0;
   offer_held<=0;job_live<=0;offer_toggle<=0;offer_payload<=0;ret_ack<=0;ret_sync<=0;ret_seen<=0;cpu_reset_sync<=0;armed_sync<=0;cap_release<=0;
   result_valid<=0;result_token<=0;result_hint_source<=0;result_target<=0;result_config<=0;result_x0<=0;result_y0<=0;result_stride<=0;result_radius<=0;
   result_source_crc32<=0;result_crc32<=0;result_bytes<=0;result_code<=0;result_psi_q8<=0;result_psi_valid<=0;result_checksum_ok<=0;result_quality_ok<=0;
   quality_mean<=0;quality_gradient<=0;quality_reason<=0;stage_passed<=0;status_reason<=0;result_capture_debug<=0;
  end else begin
   ret_sync<={ret_sync[0],ret_toggle};cpu_reset_sync<={cpu_reset_sync[0],cpu_reset_quiescent};armed_sync<={armed_sync[0],br_armed};cap_release<=0;
   if(age_active&&age!=32'hffffffff)age<=age+1'b1;
   if(core_kill)begin
    result_valid<=0;result_checksum_ok<=0;result_quality_ok<=0;stage_passed<=0;job_live<=0;age_active<=0;
    status_reason<=!enabled||cancel?13:owner_bad?14:15;
   end
   case(cs)
    C_IDLE:if(take_req)begin
     owner_target<=req_target;owner_config<=req_config;owner_epoch<=session_epoch;owner_job<=job_counter+1'b1;job_counter<=job_counter+1'b1;
     age<=0;age_active<=1;stage_passed<=0;result_valid<=0;result_checksum_ok<=0;result_quality_ok<=0;status_reason<=1;
     result_source_crc32<=0;result_crc32<=0;result_code<=0;result_psi_q8<=0;result_psi_valid<=0;result_bytes<=0;result_capture_debug<=0;cs<=C_CAPTURE;
    end
    C_CAPTURE:if(core_kill)cs<=C_DRAIN;
     else if(cap_lease)begin
      result_token<={owner_epoch,cap_source,owner_job};result_target<=cap_target;result_config<=cap_config;
      result_hint_source<=cap_hint;result_x0<=cap_x0;result_y0<=cap_y0;result_stride<=cap_stride;result_radius<=cap_radius;
      result_capture_debug<={cap_reason,cap_diag,cap_x0,cap_y0,cap_stride,cap_radius,cap_hint};
      if(!cap_good||cap_target!=owner_target||cap_config!=owner_config)begin status_reason<=2;result_valid<=1;cs<=C_RESULT;end
      else begin
       stage_passed<=1;offer_payload<={{owner_epoch,cap_source,owner_job},cap_target,cap_config,cap_x0,cap_y0,cap_stride,cap_radius};
       offer_toggle<=~offer_toggle;offer_held<=1;job_live<=1;cs<=C_WAIT;
      end
     end
    C_WAIT:if(ret_sync[1]!=ret_seen)begin ret_seen<=ret_sync[1];cs<=C_RETSETTLE;end
    C_RETSETTLE:begin
     if(!job_live||core_kill||return_kind==13)begin ret_ack<=ret_seen;offer_held<=0;job_live<=0;cs<=C_RELEASE;end
     else begin
      result_source_crc32<=return_source_crc;result_crc32<=return_cpu_crc;result_bytes<=return_bytes;result_code<=return_code;result_psi_q8<=return_psi_q8;result_psi_valid<=return_psi_valid;
      result_checksum_ok<=return_kind==0&&return_token==result_token&&return_target==owner_target&&return_config==owner_config;
      result_quality_ok<=return_qgood;quality_mean<=return_mean;quality_gradient<=return_gradient;quality_reason<=return_qreason;
      stage_passed<=return_qgood?5'd3:5'd1;
      status_reason<=return_kind==0?5'd0:return_kind==1?5'd17:5'd16;
      result_valid<=1;cs<=C_RESULT;
     end
    end
    C_RESULT:if(result_ready||core_kill)begin
     result_valid<=0;if(offer_held)ret_ack<=ret_seen;offer_held<=0;job_live<=0;cs<=C_RELEASE;
    end
    C_RELEASE:begin cap_release<=1;cs<=C_DRAIN;end
    C_DRAIN:if(!cap_busy)cs<=C_IDLE;
    default:begin result_valid<=0;job_live<=0;status_reason<=16;cs<=offer_held?C_WAIT:C_DRAIN;end
   endcase
  end
 end
endmodule
