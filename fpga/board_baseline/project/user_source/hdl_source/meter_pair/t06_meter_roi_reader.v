// Dynamic future-frame hint -> owned native ROI -> newT confirmation reader.
// This module never stalls CSI and never drives the vehicle. Visual stability
// means repeated image evidence only; it is not a claim that wheels stopped.
module t06_meter_roi_reader #(
 parameter TRIG_FILE="needle_trig128.hex",CNN_MODEL_FILE="C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native/project/user_source/hdl_source/meter_pair/strip_model.hex",CNN_ENABLE=1,
 // MAX_RESULT_AGE is retained only for source/API compatibility; not a kill.
 parameter MAX_CAPTURE_WAIT=20000000,MAX_RESULT_AGE=10000000
)(
 input wire csi_clk,clk,arst_n,mcu_clk,mcu_arst_n,
 input wire [31:0] observer_context,
 input wire [30:0] mcu_haddr,input wire [1:0] mcu_htrans,input wire mcu_hwrite,
 input wire [2:0] mcu_hsize,input wire [31:0] mcu_hwdata,
 output wire [31:0] mcu_hrdata,output wire [1:0] mcu_hresp,output wire mcu_hready,
 output reg [10:0] hub_x_q4,hub_y_q4,output wire [31:0] mcu_result_crc,
 input wire [31:0] gray4,input wire gray_valid,gray_sof,gray_eol,frame_error,
 input wire [31:0] source_id,input wire source_id_valid,
 input wire capture_frame_allowed,
 input wire enabled,cancel,
 input wire [15:0] active_target,input wire [31:0] active_config,
 input wire req_valid,output wire req_ready,
 input wire [10:0] req_x0,input wire [9:0] req_y0,input wire [2:0] req_stride,
 input wire [6:0] req_radius,input wire [31:0] req_hint_source,
 input wire [15:0] req_target,input wire [31:0] req_config,
 input wire confirm_valid,confirm_detector_evidence_ok,confirm_pose_ok,confirm_number_permit,
 input wire [31:0] confirm_source,confirm_config,input wire [15:0] confirm_target,
 input wire [10:0] confirm_center_x,input wire [9:0] confirm_center_y,
 input wire [6:0] confirm_radius,
 input wire calibration_valid,
 input wire [8:0] cal_angle0,cal_angle1,cal_angle2,cal_angle3,
 input wire [15:0] cal_value0,cal_value1,cal_value2,cal_value3,
 output wire busy,output wire capture_armed,
 output wire owned_roi_good,output wire [31:0] owned_roi_source,output wire platform_armed,
 output reg result_pulse,candidate_valid,value_valid,visual_stable,
 output reg [4:0] reason,
 output reg [31:0] result_hint_source,result_source,result_confirmed_source,result_config,
 output reg [15:0] result_target,
 output reg [10:0] result_x0,output reg [9:0] result_y0,
 output reg [2:0] result_stride,output reg [6:0] hub_x,hub_y,
 output reg [8:0] angle_index,
 output reg [15:0] value_bcd,value_q16,
 output wire [31:0] result_age_cycles,
 output reg [1:0] stable_observations,
 output wire [7:0] quality_mean,output wire [21:0] quality_gradient,
 output reg [15:0] result_needle_score,output reg [5:0] result_needle_count,
 // Per-job passed-stage evidence, qualified by the existing result source /
 // target / config. Bits: capture, quality, hub, fine needle, identity+hub
 // association. Bit4 is diagnostic and intentionally excludes needle/pose.
 output wire [4:0] stage_flags,
 output reg result_cnn_valid,result_cnn_pass,
 output reg [15:0] result_cnn_margin,
 // Captured lease evidence, frozen in CAPWAIT before RELEASE.
 // {reason5,diagnostics53,x0_11,y0_10,stride3,radius7,hint32}.
 output reg [120:0] result_capture_debug
);
// CORE wrapper only. The live component owns every CSI/HCLK CDC and RAM lease.
// Old hub/needle/StripCNN blocks are replaced, never prerequisites for analysis.
 localparam IDLE=0,WAIT_CPU=1,CONFIRM=2,MAP=3,PUBLISH=4,ABORT=5;
 (* ASYNC_REG="TRUE" *) reg [1:0] reset_release;
 always @(posedge clk or negedge arst_n)
  if(!arst_n)reset_release<=0;else reset_release<={reset_release[0],1'b1};
 wire rst_n=reset_release[1];
 reg [2:0] state;reg [15:0] owner_target;reg [31:0] owner_config;
 reg [31:0] age;reg age_active;reg [4:0] passed;
 wire owner_bad=(state!=IDLE||candidate_valid||value_valid||age_active)&&
  (owner_target!=active_target||owner_config!=active_config);
 wire kill=!rst_n||!enabled||cancel||owner_bad;
 wire live_ready,live_busy,live_armed,live_result;
 wire [95:0] live_token;wire [31:0] live_hint,live_config,live_crc,live_hwcrc,live_bytes,live_code,live_age;
 wire [15:0] live_target;wire [10:0] live_x;wire [9:0] live_y;
 wire [2:0] live_stride;wire [6:0] live_radius;
 wire live_crc_ok,live_qgood;wire [15:0] live_psi_q8;wire live_psi_valid;
 reg [15:0] held_psi_q8;reg held_psi_valid;wire [7:0] live_mean;wire [21:0] live_gradient;
 wire [4:0] live_qreason,live_flags,live_reason;wire [120:0] live_capture_debug;
 assign req_ready=rst_n&&!kill&&state==IDLE&&live_ready;
 wire take=req_valid&&req_ready;
 // Video recovery only revokes. The component remains in the MCU/global-reset
 // lifetime, so neither a slot nor its monotonic job number is reset by DDR.
 meter_mcu_live_roi #(.MAX_CAPTURE_WAIT(MAX_CAPTURE_WAIT),.MAX_RESULT_AGE(MAX_RESULT_AGE)) live(
  .csi_clk(csi_clk),.clk(clk),.mcu_clk(mcu_clk),.arst_n(mcu_arst_n),
  .observer_context(observer_context),
  .gray4(gray4),.gray_valid(gray_valid),.gray_sof(gray_sof),.gray_eol(gray_eol),.frame_error(frame_error),
  .source_id(source_id),.source_id_valid(source_id_valid),.capture_frame_allowed(capture_frame_allowed),
  .enabled(enabled&&rst_n),.cancel(kill),.active_target(active_target),.active_config(active_config),.session_epoch(32'd1),
  .req_valid(take),.req_ready(live_ready),.req_x0(req_x0),.req_y0(req_y0),.req_stride(req_stride),
  .req_radius(req_radius),.req_hint_source(req_hint_source),.req_target(req_target),.req_config(req_config),
  .busy(live_busy),.capture_armed(live_armed),.platform_armed(platform_armed),
  .owned_roi_good(owned_roi_good),.owned_roi_source(owned_roi_source),.result_valid(live_result),.result_ready(1'b1),
  .result_token(live_token),.result_hint_source(live_hint),.result_target(live_target),.result_config(live_config),
  .result_x0(live_x),.result_y0(live_y),.result_stride(live_stride),.result_radius(live_radius),
  .result_source_crc32(live_hwcrc),.result_crc32(live_crc),.result_bytes(live_bytes),.result_code(live_code),
  .result_psi_q8(live_psi_q8),.result_psi_valid(live_psi_valid),
  .result_checksum_ok(live_crc_ok),.result_quality_ok(live_qgood),.quality_mean(live_mean),
  .quality_gradient(live_gradient),.quality_reason(live_qreason),.stage_flags(live_flags),
  .status_reason(live_reason),.result_capture_debug(live_capture_debug),.result_age_cycles(live_age),
  .haddr(mcu_haddr),.htrans(mcu_htrans),.hwrite(mcu_hwrite),.hsize(mcu_hsize),.hwdata(mcu_hwdata),
  .hrdata(mcu_hrdata),.hresp(mcu_hresp),.hready(mcu_hready),.cpu_reset_quiescent(1'b0));
 assign busy=state!=IDLE||live_busy;
 assign capture_armed=live_armed&&state==WAIT_CPU&&!kill;
 assign result_age_cycles=age;
 assign stage_flags=kill?5'd0:passed;
 reg [7:0] held_mean;reg [21:0] held_gradient;reg [31:0] held_crc;
 assign quality_mean=held_mean;assign quality_gradient=held_gradient;
 assign mcu_result_crc=held_crc;
 reg [6:0] held_radius;
 reg conf_have,conf_identity,conf_pose,conf_number_permit;reg [31:0] conf_source,conf_config;
 reg [15:0] conf_target;reg [10:0] conf_x;reg [9:0] conf_y;reg [6:0] conf_radius;
 wire direct_confirm=confirm_valid&&confirm_source==result_source&&confirm_config==result_config&&confirm_target==result_target;
 wire cached_confirm=conf_have&&conf_source==result_source&&conf_config==result_config&&conf_target==result_target;
 wire identity_ok=direct_confirm?confirm_detector_evidence_ok:conf_identity;
 wire pose_ok=direct_confirm?confirm_pose_ok:conf_pose;
 wire number_permit=direct_confirm?confirm_number_permit:conf_number_permit;
 wire [10:0] ax=direct_confirm?confirm_center_x:conf_x;
 wire [9:0] ay=direct_confirm?confirm_center_y:conf_y;
 wire [6:0] ar=direct_confirm?confirm_radius:conf_radius;
 // Q4 coordinates describe actual block centres; native block-centre offset
 // (stride-1)/2 is retained, including the stride4 half-pixel.
 wire [16:0] nxq4=({6'd0,result_x0}<<4)+hub_x_q4*result_stride+((result_stride-1'b1)<<3);
 wire [16:0] nyq4=({7'd0,result_y0}<<4)+hub_y_q4*result_stride+((result_stride-1'b1)<<3);
 wire [12:0] nx=(nxq4+17'd8)>>4,ny=(nyq4+17'd8)>>4;
 wire [12:0] dx=nx>=ax?nx-ax:ax-nx,dy=ny>=ay?ny-ay:ay-ny;
 wire [6:0] dr=held_radius>=ar?held_radius-ar:ar-held_radius;
 wire association=dx<=({10'd0,result_stride}<<3)&&dy<=({10'd0,result_stride}<<3)&&dr<=4;
 // Full-pointer ABI is unchanged. HUB_ONLY carries no needle direction.
 wire hub_coordinates_ok=live_code[21:11]<=2032&&live_code[10:0]<=2032;
 wire pointer_evidence=live_code[31]&&live_code[30:22]<360&&hub_coordinates_ok;
 // Bits29:22 are a nonzero low5-bit rejection mask:1tip peak,2tip margin,
 //4too short,8too long,16structure. Zero/undefined bits cannot manufacture hub evidence.
 wire hub_only_evidence=live_code[31:30]==2'b01&&live_code[29:27]==0&&
  live_code[26:22]!=0&&hub_coordinates_ok;
 wire hub_evidence=pointer_evidence||hub_only_evidence;
 reg held_hub_only;
 reg mstart;wire mbusy,mdone,mgood;wire [15:0] mbcd,mq16;wire [4:0] mreason;
 t06_meter_psi_return_runtime scale(.clk(clk),.rst_n(rst_n),.start(mstart),.cancel(kill),
  .calibration_valid(calibration_valid),.input_valid(held_psi_valid),.psi_q8(held_psi_q8),
  .busy(mbusy),.done(mdone),.value_valid(mgood),.value_q16(mq16),.value_bcd(mbcd),.reason(mreason));
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=IDLE;owner_target<=0;owner_config<=0;age<=0;age_active<=0;passed<=0;mstart<=0;
   result_pulse<=0;candidate_valid<=0;value_valid<=0;visual_stable<=0;reason<=0;
   result_hint_source<=0;result_source<=0;result_confirmed_source<=0;result_config<=0;result_target<=0;
   result_x0<=0;result_y0<=0;result_stride<=0;hub_x<=0;hub_y<=0;hub_x_q4<=0;hub_y_q4<=0;
   angle_index<=0;value_bcd<=0;value_q16<=0;stable_observations<=0;held_mean<=0;held_gradient<=0;held_crc<=0;held_radius<=0;
   result_needle_score<=0;result_needle_count<=0;result_cnn_valid<=0;result_cnn_pass<=0;result_cnn_margin<=0;result_capture_debug<=0;
   conf_have<=0;conf_identity<=0;conf_pose<=0;conf_number_permit<=0;conf_source<=0;conf_config<=0;conf_target<=0;conf_x<=0;conf_y<=0;conf_radius<=0;held_hub_only<=0;held_psi_q8<=0;held_psi_valid<=0;
  end else begin
   mstart<=0;result_pulse<=0;
   if(age_active&&age!=32'hffffffff)age<=age+1'b1;
   if(confirm_valid&&confirm_target==active_target&&confirm_config==active_config)begin
    conf_have<=1;conf_identity<=confirm_detector_evidence_ok;conf_pose<=confirm_pose_ok;conf_number_permit<=confirm_number_permit;
    conf_source<=confirm_source;conf_config<=confirm_config;conf_target<=confirm_target;
    conf_x<=confirm_center_x;conf_y<=confirm_center_y;conf_radius<=confirm_radius;
   end
   if(!calibration_valid)begin value_valid<=0;value_bcd<=0;value_q16<=0;end
   if(kill)begin
    // A persistent owner change must not trap the shell in ABORT after the
    // component has physically retired. This never clears its pending slot.
    state<=live_busy?ABORT:IDLE;candidate_valid<=0;value_valid<=0;visual_stable<=0;value_bcd<=0;value_q16<=0;
    passed<=0;held_hub_only<=0;held_psi_q8<=0;held_psi_valid<=0;result_cnn_valid<=0;result_cnn_pass<=0;stable_observations<=0;age_active<=0;
    reason<=!enabled||cancel?13:owner_bad?14:15;
   end else case(state)
    IDLE:if(take)begin
     owner_target<=req_target;owner_config<=req_config;age<=0;age_active<=1;state<=WAIT_CPU;
     candidate_valid<=0;value_valid<=0;visual_stable<=0;value_bcd<=0;value_q16<=0;passed<=0;
     held_hub_only<=0;held_psi_q8<=0;held_psi_valid<=0;result_cnn_valid<=0;result_cnn_pass<=0;result_cnn_margin<=0;conf_have<=0;reason<=1;
     held_crc<=0;held_mean<=0;held_gradient<=0;result_capture_debug<=0;
    end
    WAIT_CPU:begin
     if(live_result)begin
      result_hint_source<=live_hint;result_source<=live_token[63:32];result_target<=live_target;result_config<=live_config;
      result_confirmed_source<=0;result_x0<=live_x;result_y0<=live_y;result_stride<=live_stride;held_radius<=live_radius;
      held_mean<=live_mean;held_gradient<=live_gradient;held_crc<=live_crc;
      held_psi_q8<=live_psi_q8;held_psi_valid<=live_psi_valid;
      result_capture_debug<=live_capture_debug;passed<=live_flags&5'b00011;
      if(!live_crc_ok||live_bytes!=16384||live_target!=owner_target||live_config!=owner_config)begin
       reason<=21;stable_observations<=0;state<=PUBLISH;
      end
      else if(!hub_evidence)begin
       // CRC-only code0 is a transport result, never a manufactured pointer.
       result_cnn_valid<=live_code==1;result_cnn_pass<=0;
       reason<=live_code==0?20:live_code==1?5:live_code==2?3:live_code==3?21:22;
       stable_observations<=0;state<=PUBLISH;
      end else begin
       held_hub_only<=hub_only_evidence;result_cnn_valid<=1;result_cnn_pass<=pointer_evidence;
       hub_x_q4<=live_code[21:11];hub_y_q4<=live_code[10:0];hub_x<=live_code[21:15];hub_y<=live_code[10:4];
       angle_index<=pointer_evidence?live_code[30:22]:9'd0;
       passed[2]<=1;passed[3]<=pointer_evidence;reason<=6;state<=CONFIRM;
      end
     end else if(!live_busy&&age>=2)begin reason<=live_reason;state<=PUBLISH;end
    end
    CONFIRM:if(direct_confirm||cached_confirm)begin
     result_confirmed_source<=direct_confirm?confirm_source:conf_source;
     passed[4]<=identity_ok&&association;
     if(!identity_ok||(!held_hub_only&&!pose_ok)||!association)begin
      reason<=!identity_ok?7:(!held_hub_only&&!pose_ok)?8:9;stable_observations<=0;state<=PUBLISH;
     end else if(held_hub_only)begin
      // SameT/CRC/identity/association hold. Quality statistics staymetadata.
      // Strong axis survives missingneedle; it cannot authorize a number.
      reason<=23;candidate_valid<=0;value_valid<=0;visual_stable<=0;
      value_bcd<=0;value_q16<=0;angle_index<=0;passed[3]<=0;result_cnn_pass<=0;
      stable_observations<=0;state<=PUBLISH;
     end else if(!number_permit)begin
      // Intrinsic T crop/partial veto belongs only to numeric output.
      // The sameT axis evidence above remains available; CNN already ran.
      reason<=24;candidate_valid<=0;value_valid<=0;visual_stable<=0;
      value_q16<=0;value_bcd<=0;stable_observations<=0;state<=PUBLISH;
     end else begin
      candidate_valid<=1;
      // This is one valid per-T number candidate, not a stable final READ.
      // Final parent guard still requires its original three fresh sources.
      visual_stable<=0;stable_observations<=0;
      if(calibration_valid)begin mstart<=1;state<=MAP;end
      else begin reason<=11;state<=PUBLISH;end
     end
    end
    MAP:if(!calibration_valid)begin reason<=11;state<=PUBLISH;end
     else if(mdone)begin value_valid<=mgood;value_q16<=mgood?mq16:0;value_bcd<=mgood?mbcd:0;reason<=mgood?0:12;state<=PUBLISH;end
    PUBLISH:begin result_pulse<=1;state<=IDLE;end
    ABORT:if(!live_busy)state<=IDLE;
    default:state<=ABORT;
   endcase
  end
 end
endmodule
