// Restricted-gauge analysis pipeline. No physical IO assignment or motor driver.
// SEARCH S is a hint. A separate, complete new T is locally confirmed and read.
// Permission inputs are explicit; no default/tied pose/focus/stop qualification.
module t06_meter_visual_pipeline #(
 parameter PAIR_FILE="pair_base_rom.mem",TRIG_FILE="needle_trig128.hex",
 parameter MAX_PHASE_CYCLES=225000000,
 parameter MAX_LOCATION_AGE_CYCLES=15000000,MAX_ARM_CYCLES=1000000,MAX_READ_JOB_CYCLES=150000000
)(
 input wire core_clk,csi_clk,arst_n,
 input wire mcu_clk,mcu_arst_n,
 input wire [30:0] mcu_haddr,input wire [1:0] mcu_htrans,input wire mcu_hwrite,
 input wire [2:0] mcu_hsize,input wire [31:0] mcu_hwdata,
 output wire [31:0] mcu_hrdata,output wire [1:0] mcu_hresp,output wire mcu_hready,

 input wire enabled,cancel,stream_fault,
 input wire observer_display_fault,
 input wire [31:0] gray4,input wire gray_valid,gray_sof,gray_eol,frame_error,
 input wire source_valid,input wire [31:0] source_id,source_epoch,cfg_revision,
 input wire [31:0] now_ms,motion_epoch,active_config,
 input wire stationary,controlled_frontal_setup,focus_setup_permit,calibration_valid,
 // Live control evidence remains separate from LAST-success display.
 output wire value_update,value_valid,output wire [15:0] value_q16,value_bcd,
 output reg display_value_update,output wire display_value_valid,
 output wire display_hard_revoke,
 output reg [15:0] display_value_bcd,display_value_q16,output reg [31:0] display_value_source,
 output wire [31:0] value_source,output wire [15:0] value_target,
 output reg location_partial,output wire location_valid,output reg [10:0] box_x0,box_x1,center_x,
 output reg [9:0] box_y0,box_y1,diameter,center_y,
 output reg [31:0] location_source,location_epoch,
 output wire global_lock,output wire [31:0] target_id,
 output wire [3:0] pipeline_state,output reg [4:0] pipeline_reason,
 output wire [4:0] read_reason,reader_reason,
 output wire [7:0] printed_count,output wire [15:0] needle_score,
 output wire [5:0] needle_count,output wire [8:0] needle_angle,
 output wire image_readability_candidate,
 output wire [31:0] reader_source,confirmed_source,
 output wire reader_observation,
 output wire geometry_valid,output wire [10:0] native_hub_x,
 output wire [9:0] native_hub_y,output reg [31:0] geometry_source,
 // Display-only translated box from the SAME saved T as hub/angle/source.
 output wire [43:0] geometry_box_payload,
 output wire geometry_held_only,
 output reg geometry_needle_valid,output reg [8:0] geometry_needle_angle,
 output wire debug_owner_valid,debug_roi_armed,debug_release,
 output wire [31:0] debug_owner_source,
 // Atomic evidence for the latest completed observation, not live job state.
 // A newer in-flight job never relabels or refreshes this source/age bundle.
 output reg diag_valid,output reg [31:0] diag_source,
 output reg [4:0] diag_reader_reason,output reg [5:0] diag_fail_mask,
 output reg [4:0] diag_stage_flags,output reg [9:0] diag_diameter,
 output reg signed [4:0] diag_roll,output reg [7:0] diag_print_count,
 output reg [5:0] diag_needle_count,output reg [15:0] diag_needle_score,
 output reg [8:0] diag_angle,output reg [7:0] diag_mean,
 output reg [120:0] diag_capture_debug
);
 localparam WAIT_OWNER=0,SEARCH_WAIT=1,REQUEST_ROI=2,WAIT_ARMED=3,
            WAIT_RELEASE=4,DECIDE_NEXT=5,RESTART=7;
 (* ASYNC_REG="TRUE" *)reg [1:0] core_release;
 always @(posedge core_clk or negedge arst_n)if(!arst_n)core_release<=0;else core_release<={core_release[0],1'b1};
 wire rst_n=core_release[1];
 (* ASYNC_REG="TRUE" *)reg [1:0] csi_release;
 always @(posedge csi_clk or negedge arst_n)if(!arst_n)csi_release<=0;else csi_release<={csi_release[0],1'b1};
 wire csi_rst_n=csi_release[1];
 reg [3:0] state;assign pipeline_state=state;
 reg location_have,geometry_have;
 reg [10:0] geometry_hub_x,geometry_center_x;
 reg [9:0] geometry_hub_y,geometry_center_y,geometry_diameter;
 reg [10:0] geometry_x0,geometry_x1,confirmed_x0,confirmed_x1;
 reg [9:0] geometry_y0,geometry_y1,confirmed_y0,confirmed_y1;
 reg signed [4:0] geometry_roll,location_roll;
 reg [31:0] location_age_cycles;
 wire read_withdraw;
 reg [31:0] phase_cycles,last_config,last_motion;
 // A motor action invalidates the reading window, not image tracking.
 wire context_change=last_config!=active_config;
 wire motion_change=last_motion!=motion_epoch;
 wire source_context_bad,platform_context_bad;
 wire external_kill=!enabled||cancel||stream_fault||context_change||source_context_bad||platform_context_bad;
 wire phase_timeout=state!=WAIT_OWNER&&phase_cycles>=MAX_PHASE_CYCLES-1;
 reg restart_cancel;
 wire worker_cancel=external_kill||restart_cancel||phase_timeout;
 (* ASYNC_REG="TRUE" *)reg [1:0] enabled_csi;
 always @(posedge csi_clk or negedge arst_n)if(!arst_n)enabled_csi<=0;else enabled_csi<={enabled_csi[0],enabled};
 wire cap_open;wire [31:0] cap_source,cap_epoch,cap_cfg;
 wire owner_valid,owner_pulse,owner_revoke;wire [31:0] owner_source,owner_epoch,owner_cfg,owner_lease,owner_age,owner_capture_cycles;
 reg release_valid;reg [31:0] release_lease;
 wire rd_req,rd_valid,rd_fault;wire [15:0] rd_addr;wire [31:0] rd_lease;wire [7:0] rd_data;
 t06_mean4_frame_lease frame_cache(
  .csi_clk(csi_clk),.core_clk(core_clk),.arst_n(arst_n),.gray4(gray4),.s_valid(gray_valid),.s_sof(gray_sof),.s_eol(gray_eol),.frame_error(frame_error),
  .source_valid(source_valid),.source_id(source_id),.source_epoch(source_epoch),.cfg_revision(cfg_revision),.enabled(enabled_csi[1]),.core_cancel(worker_cancel),
  .capture_open_pulse(cap_open),.capture_open_source(cap_source),.capture_open_epoch(cap_epoch),.capture_open_cfg(cap_cfg),
  .owner_valid(owner_valid),.owner_source(owner_source),.owner_epoch(owner_epoch),.owner_cfg(owner_cfg),.owner_lease(owner_lease),.capture_age(owner_age),.owner_pulse(owner_pulse),.owner_revoke(owner_revoke),.owner_capture_csi_cycles(owner_capture_cycles),
  .release_valid(release_valid),.release_lease(release_lease),.rd_req(rd_req),.rd_addr(rd_addr),.rd_lease(rd_lease),.rd_valid(rd_valid),.rd_data(rd_data),.rd_fault(rd_fault),.dropped_frames());
 reg pair_start,pair_track,scan_is_track;
 wire pair_context_good;
 wire pair_busy,pair_done,pair_fault,pair_valid,pair_partial,pair_margin_valid,pair_fresh,reacquire_due;
 wire [7:0] pair_count;wire signed [8:0] pair_margin;
 wire [10:0] px0,px1,pcx;wire [9:0] py0,py1,pcy,pdiam;wire [2:0] proll;
 wire [31:0] psource,pepoch,pcfg,please,page;
 t06_pair_search #(.PAIR_FILE(PAIR_FILE),.MAX_TRACK_USES(128)) search(
  .clk(core_clk),.rst_n(rst_n),.cancel(worker_cancel),.start(pair_start),.track_mode(pair_track),
  .owner_valid(owner_valid),.owner_source(owner_source),.owner_epoch(owner_epoch),.owner_cfg(owner_cfg),.owner_lease(owner_lease),.owner_age(owner_age),
  .busy(pair_busy),.done(pair_done),.fault(pair_fault),.candidate_valid(pair_valid),.partial(pair_partial),.best_count(pair_count),.far_margin_count(pair_margin),.margin_valid(pair_margin_valid),.fresh_track_confirm(pair_fresh),
  .box_x0(px0),.box_x1(px1),.box_y0(py0),.box_y1(py1),.center_x(pcx),.center_y(pcy),.diameter(pdiam),.low_center_x(),.low_center_y(),.roll_index(proll),
  .result_source(psource),.result_epoch(pepoch),.result_cfg(pcfg),.result_lease(please),.result_age(page),.actual_cycles(),.gray_reads(),.evaluated_positions(),.reason(),.global_lock(global_lock),.reacquire_due(reacquire_due),.target_id(target_id),
  .rd_req(rd_req),.rd_addr(rd_addr),.rd_lease(rd_lease),.rd_valid(rd_valid),.rd_data(rd_data),.rd_fault(rd_fault));
 // cap_open is registered after the realCSI SOF. Delay every source/control
 // component exactly together so ROI capture sees the same T, first pixel too.
 reg [31:0] delayed_gray,delayed_source;
 reg delayed_valid,delayed_sof,delayed_eol,delayed_error,delayed_source_valid;
 always @(posedge csi_clk or negedge csi_rst_n)begin
  if(!csi_rst_n)begin delayed_gray<=0;delayed_source<=0;delayed_valid<=0;delayed_sof<=0;delayed_eol<=0;delayed_error<=0;delayed_source_valid<=0;end
  else begin delayed_gray<=gray4;delayed_source<=source_id;delayed_valid<=gray_valid;delayed_sof<=gray_sof;delayed_eol<=gray_eol;delayed_error<=frame_error;delayed_source_valid<=source_valid;end
 end
 reg roi_request,roi_cancel,roi_cancel_soft;wire roi_ready,roi_busy,roi_armed,roi_result,roi_candidate,roi_number,roi_stable;
 wire roi_owned_good,roi_platform_armed;wire [31:0] roi_owned_source;
 reg read_job_active,read_waiting_T,read_confirmed;
 // Passive first cancellation path, held through video recovery until MCU reset.
 reg [3:0] cancel_cause_event,first_cancel_cause;
 always @(posedge core_clk or negedge mcu_arst_n)begin
  if(!mcu_arst_n)first_cancel_cause<=0;
  else if(first_cancel_cause==0&&cancel_cause_event!=0)first_cancel_cause<=cancel_cause_event;
 end
 reg [31:0] read_expected_source;
 reg [10:0] roi_x;reg [9:0] roi_y;reg [2:0] roi_stride;reg [6:0] roi_radius;
 reg [31:0] hint_source,hint_epoch,hint_cfg,hint_lease;
 reg [15:0] active_target_id;
 reg [31:0] capture_lower_ms,capture_motion;
 reg confirm_valid,confirm_identity,confirm_pose;
 reg [31:0] confirm_source;reg [10:0] confirm_x;reg [9:0] confirm_y;reg [6:0] confirm_radius;
 reg [7:0] confirmed_count;reg [9:0] confirmed_diameter;reg signed [4:0] confirmed_roll;
 wire reader_cnn_valid,reader_cnn_pass;wire [15:0] reader_cnn_margin;
 wire [31:0] result_hint,result_cfg,result_age;wire [15:0] result_target;
 wire [10:0] result_x;wire [9:0] result_y;wire [2:0] result_stride;
 wire [6:0] hub_x,hub_y;wire [15:0] roi_q16,roi_bcd;wire [1:0] stable_count;wire [7:0] mean_gray;wire [21:0] gradient;
 wire [4:0] roi_stage_flags;wire [120:0] reader_capture_debug;
 wire [12:0] reader_native_x,reader_native_y,progress_native_x,progress_native_y;wire [31:0] mcu_result_crc;
 wire progress_have,progress_pulse,progress_needle;wire [10:0] progress_x;
 wire [9:0] progress_y;wire [8:0] progress_angle;wire [2:0] progress_stride;wire [6:0] progress_radius;
 wire [31:0] progress_source,progress_config;wire [15:0] progress_target;
 // Passive observation only. These registers never control the pipeline.
 wire [31:0] observer_context;
 wire read_output_withdraw,measurement_fault;
 reg confirmed_partial,confirmed_crop_complete;
 wire signed [4:0] pair_roll_degrees=$signed({2'b00,proll})*5'sd3-5'sd9;
 wire profile_permit=calibration_valid&&controlled_frontal_setup&&focus_setup_permit;
 t06_meter_roi_reader #(.TRIG_FILE(TRIG_FILE)) reader(
  .mcu_clk(mcu_clk),.mcu_arst_n(mcu_arst_n),.mcu_haddr(mcu_haddr),.mcu_htrans(mcu_htrans),
  .mcu_hwrite(mcu_hwrite),.mcu_hsize(mcu_hsize),.mcu_hwdata(mcu_hwdata),
  .mcu_hrdata(mcu_hrdata),.mcu_hresp(mcu_hresp),.mcu_hready(mcu_hready),
  .observer_context(observer_context),
  .owned_roi_good(roi_owned_good),.owned_roi_source(roi_owned_source),.platform_armed(roi_platform_armed),
  .hub_x_q4(),.hub_y_q4(),.native_hub_x(reader_native_x),.native_hub_y(reader_native_y),.mcu_result_crc(mcu_result_crc),
  .progress_valid(progress_have),.progress_pulse(progress_pulse),.progress_needle_valid(progress_needle),
  .progress_hub_x_q4(),.progress_hub_y_q4(),.progress_native_x(progress_native_x),.progress_native_y(progress_native_y),.progress_angle(progress_angle),
  .progress_source(progress_source),.progress_config(progress_config),.progress_target(progress_target),
  .progress_x0(progress_x),.progress_y0(progress_y),.progress_stride(progress_stride),.progress_radius(progress_radius),
  .csi_clk(csi_clk),.clk(core_clk),.arst_n(arst_n),.gray4(delayed_gray),.gray_valid(delayed_valid),.gray_sof(delayed_sof),.gray_eol(delayed_eol),.frame_error(delayed_error),.source_id(delayed_source),.source_id_valid(delayed_source_valid),.capture_frame_allowed(cap_open),
  .enabled(enabled),.cancel(worker_cancel||roi_cancel),.active_target(active_target_id),.active_config(active_config),
  .req_valid(roi_request),.req_ready(roi_ready),.req_x0(roi_x),.req_y0(roi_y),.req_stride(roi_stride),.req_radius(roi_radius),.req_hint_source(hint_source),.req_target(active_target_id),.req_config(active_config),
  .confirm_valid(confirm_valid),.confirm_detector_evidence_ok(confirm_identity),.confirm_pose_ok(confirm_pose),
  .confirm_number_permit(!confirmed_partial&&confirmed_crop_complete),.confirm_source(confirm_source),.confirm_config(active_config),.confirm_target(active_target_id),.confirm_center_x(confirm_x),.confirm_center_y(confirm_y),.confirm_radius(confirm_radius),
  .calibration_valid(profile_permit),.cal_angle0(9'd142),.cal_angle1(9'd169),.cal_angle2(9'd191),.cal_angle3(9'd231),.cal_value0(16'd0),.cal_value1(16'd13763),.cal_value2(16'd20972),.cal_value3(16'd33423),
  .busy(roi_busy),.capture_armed(roi_armed),.result_pulse(roi_result),.candidate_valid(roi_candidate),.value_valid(roi_number),.visual_stable(roi_stable),.reason(reader_reason),
  .result_hint_source(result_hint),.result_source(reader_source),.result_confirmed_source(confirmed_source),.result_config(result_cfg),.result_target(result_target),.result_x0(result_x),.result_y0(result_y),.result_stride(result_stride),.hub_x(hub_x),.hub_y(hub_y),.angle_index(needle_angle),.value_bcd(roi_bcd),.value_q16(roi_q16),.result_age_cycles(result_age),.stable_observations(stable_count),.quality_mean(mean_gray),.quality_gradient(gradient),.result_needle_score(needle_score),.result_needle_count(needle_count),.stage_flags(roi_stage_flags),.result_cnn_valid(reader_cnn_valid),.result_cnn_pass(reader_cnn_pass),.result_cnn_margin(reader_cnn_margin),.result_capture_debug(reader_capture_debug));
 assign printed_count=confirmed_count;
 wire frontal_compatible,scale_ok,roll_ok,detail_ok;
 visual_readability_gate #(.CNN_ENABLE(1)) readability(
  .identity_accepted(confirm_identity),.geometry_candidate(roi_candidate),.pixel_quality_ok(roi_candidate),.number_valid(roi_number),
  .printed_count(confirmed_count),.diameter(confirmed_diameter),.printed_roll(confirmed_roll),.needle_score(needle_score),.needle_count(needle_count),.cnn_valid(reader_cnn_valid),.cnn_positive(reader_cnn_pass),
  .frontal_template_compatible(frontal_compatible),.scale_window_ok(scale_ok),.roll_window_ok(roll_ok),.thin_detail_supported(detail_ok),.image_readability_candidate(image_readability_candidate));
 reg observation,reader_result_pending;
 wire guard_update,guard_valid;wire [15:0] guard_q16,guard_bcd,guard_target;wire [31:0] guard_source;
 // Guard position/radius tolerances are in native image pixels, independent
 // of a future ROI changing from stride3 to stride4 as its box scale changes.
 visual_read_guard #(.RADIUS_TOL(6)) guard(
  .clk(core_clk),.rst_n(rst_n),.enabled(enabled),
  .cancel(worker_cancel||(roi_cancel&&!roi_cancel_soft)||measurement_fault||motion_change||!stationary||!profile_permit),
  .soft_withdraw(read_withdraw||location_partial||roi_cancel_soft),
  .stream_fault(stream_fault),.stationary(stationary),.now_ms(now_ms),.motion_epoch(motion_epoch),.active_config(active_config),.active_target(active_target_id),.calibration_valid(profile_permit),
  .observation(observation),.local_confirm(confirm_identity&&confirm_source==reader_source&&(!roi_number||confirmed_source==reader_source)),.identity_ok(confirm_identity),.pose_ok(controlled_frontal_setup&&frontal_compatible&&scale_ok&&roll_ok),.focus_ok(focus_setup_permit&&detail_ok),.exposure_ok(roi_candidate),.roi_good(roi_candidate),.needle_ok(roi_candidate),.number_valid(roi_number&&image_readability_candidate),
  .capture_ms(capture_lower_ms),.capture_epoch(capture_motion),.detector_source(confirm_source),.reader_source(reader_source),.observation_config(result_cfg),.observation_target(result_target),.center_x(confirm_x),.center_y(confirm_y),.radius(confirmed_diameter[9:1]),.angle(needle_angle),.number_q16(roi_q16),.number_bcd(roi_bcd),
  .value_update(guard_update),.value_valid(guard_valid),.value_q16(guard_q16),.value_bcd(guard_bcd),.value_target(guard_target),.value_source(guard_source),.position_observations(),.needle_observations(),.reason(read_reason));
 // Analysis may run before CAL/pose/needle are available. Final output
 // and displayed geometry retain the stricter stopped/profile requirements.
 // Analysis requires a current locator/owner, not already-readable optics.
 assign read_withdraw=!global_lock||!location_valid;
 // A partial full-dial estimate remains an output-quality veto, never
 // an analysis veto. The new crop metadata adds no numeric-output permission.
 assign read_output_withdraw=read_withdraw||location_partial||motion_change||!stationary||!profile_permit;
 // Current U may withdraw CURRENT; it never rewrites frozen T attributes.
 assign value_valid=guard_valid&&guard_target==active_target_id&&global_lock&&!worker_cancel&&!read_output_withdraw&&!roi_cancel&&!measurement_fault;
 assign location_valid=location_have&&global_lock&&!worker_cancel&&location_age_cycles<MAX_LOCATION_AGE_CYCLES;
 // Translation only. Evidence/source/angle/box dimensions remain those of T.
 wire signed [12:0] projected_hub_x=$signed({2'b00,center_x})+$signed({2'b00,geometry_hub_x})-$signed({2'b00,geometry_center_x});
 wire signed [12:0] projected_hub_y=$signed({3'b000,center_y})+$signed({3'b000,geometry_hub_y})-$signed({3'b000,geometry_center_y});
 wire projected_in_bounds=projected_hub_x>=0&&projected_hub_x<1280&&projected_hub_y>=0&&projected_hub_y<720;
 wire signed [12:0] projected_x0=$signed({2'b00,center_x})+$signed({2'b00,geometry_x0})-$signed({2'b00,geometry_center_x});
 wire signed [12:0] projected_x1=$signed({2'b00,center_x})+$signed({2'b00,geometry_x1})-$signed({2'b00,geometry_center_x});
 wire signed [12:0] projected_y0=$signed({3'b000,center_y})+$signed({3'b000,geometry_y0})-$signed({3'b000,geometry_center_y});
 wire signed [12:0] projected_y1=$signed({3'b000,center_y})+$signed({3'b000,geometry_y1})-$signed({3'b000,geometry_center_y});
 wire projected_box_in_bounds=projected_x0>=0&&projected_x0<projected_x1&&projected_x1<=1280&&
  projected_y0>=0&&projected_y0<projected_y1&&projected_y1<=720;
 // Reuse the real TRACK/recheck identity envelope (t06_pair_search): native
 // D +/-16 and one roll-index step of3degrees. This is display association,
 // not scale/roll rectification or a current numeric-output qualification.
 // Anchoring both deltas to saved T prevents adjacent drifts accumulating.
 wire signed [10:0] display_dd=$signed({1'b0,diameter})-$signed({1'b0,geometry_diameter});
 wire signed [5:0] display_dr=$signed({location_roll[4],location_roll})-$signed({geometry_roll[4],geometry_roll});
 wire geometry_shape_compatible=display_dd>=-11'sd16&&display_dd<=11'sd16&&
  display_dr>=-6'sd3&&display_dr<=6'sd3;
 wire geometry_associated=location_valid&&geometry_shape_compatible;
 wire saved_T_in_bounds=geometry_hub_x<1280&&geometry_hub_y<720&&
  geometry_x0<geometry_x1&&geometry_y0<geometry_y1&&geometry_x1<=1280&&geometry_y1<=720;
 // No current U: retain the original screen coordinates of the whole T,
 // explicitly labelled held-only. A known conflicting/out-of-screen U must
 // not revive T merely by aging out. Its cached geometry still vetoes this.
 wire soft_no_U=!location_valid&&geometry_shape_compatible&&projected_in_bounds&&
  projected_box_in_bounds&&saved_T_in_bounds;
 // Refuse even a one-cycle fallback when SEARCH has already rejected owner
 // evidence; the original restart/worker path subsequently clears the package.
 wire search_reject_now=pair_done&&(pair_fault||!pair_valid||!pair_context_good||
  (scan_is_track?!pair_fresh:!pair_margin_valid));
 assign geometry_valid=geometry_have&&!display_hard_revoke&&!search_reject_now&&
  ((geometry_associated&&projected_in_bounds&&projected_box_in_bounds)||soft_no_U);
 assign geometry_held_only=geometry_valid&&!location_valid;
 assign geometry_box_payload=geometry_held_only?{geometry_x0,{1'b0,geometry_y0},geometry_x1,{1'b0,geometry_y1}}:
  projected_box_in_bounds?{projected_x0[10:0],projected_y0[10:0],projected_x1[10:0],projected_y1[10:0]}:44'd0;
 assign native_hub_x=geometry_held_only?geometry_hub_x:projected_in_bounds?projected_hub_x[10:0]:11'd0;
 assign native_hub_y=geometry_held_only?geometry_hub_y:projected_in_bounds?projected_hub_y[9:0]:10'd0;
 assign value_update=guard_update;
 assign value_q16=value_valid?guard_q16:16'd0;
 assign value_bcd=value_valid?guard_bcd:16'd0;
 assign value_source=value_valid?guard_source:32'd0;
 assign value_target=value_valid?guard_target:16'd0;
 assign reader_observation=observation;
 // Geometry ports are display-only LAST-success evidence; their only native
 // consumer is link/OSD. They never authorize a current READ or car action.
 // Geometry is diagnostic and never authorizes READ. It carries the exact T
 // source even when later image/detail/profile gates reject the numeric value.
 reg display_value_have;reg [15:0] display_owner_target;
 wire display_owner_bad=(geometry_have||display_value_have)&&display_owner_target!=active_target_id;
 // A reader rejection is not an owner loss. Existing target/stop/stream/fault
 // invalidations revoke both displays immediately; no new timeout/ticket.
 // Compute deadline withdraws CURRENT READ above; it is not evidence that
 // a previously recognized same-owner axis/needle has become a different dial.
 wire display_revoke=!rst_n||external_kill||restart_cancel||motion_change||!stationary||measurement_fault||
  !controlled_frontal_setup||!focus_setup_permit||display_owner_bad;
 assign display_hard_revoke=display_revoke;
 wire axis_display_update=observation&&roi_stage_flags[2]&&roi_stage_flags[4]&&confirm_identity&&
  reader_source==confirm_source&&result_cfg==active_config&&result_target==active_target_id;
 // Once FULL exists, keep its entire LAST package through later HUB_ONLY.
 // The new hub remains in the completed-job diagnostic bundle; it cannot
 // silently replace the saved hub while retaining another source's needle.
 // A stage may precede TRACK-T confirmation. Its held valid allows the
 // confirmation pulse to publish it later; a newer tracking U is never used.
 wire early_context=progress_have&&read_job_active&&read_confirmed&&confirm_identity&&
  progress_source==confirm_source&&progress_source==read_expected_source&&
  progress_source==roi_owned_source&&roi_owned_good&&progress_config==hint_cfg&&
  progress_config==active_config&&progress_target==active_target_id&&capture_motion==motion_epoch;
 wire early_request=early_context&&(progress_pulse||confirm_valid)&&!axis_display_update;
 // Reader owns the only mapper. Early native coordinates were cached
 // on the same accepted-code edge and remain tied to that entire package.
 wire [12:0] display_nx=early_request?progress_native_x:reader_native_x;
 wire [12:0] display_ny=early_request?progress_native_y:reader_native_y;
 wire [12:0] early_dx=display_nx>=confirm_x?display_nx-confirm_x:confirm_x-display_nx;
 wire [12:0] early_dy=display_ny>=confirm_y?display_ny-confirm_y:confirm_y-display_ny;
 wire [6:0] early_dr=progress_radius>=confirm_radius?progress_radius-confirm_radius:confirm_radius-progress_radius;
 wire early_axis_update=early_request&&display_nx<1280&&display_ny<720&&
  early_dx<=({10'd0,progress_stride}<<3)&&early_dy<=({10'd0,progress_stride}<<3)&&early_dr<=4;
 wire display_needle=early_request?progress_needle:roi_stage_flags[3];
 wire [8:0] display_angle=early_request?progress_angle:needle_angle;
 wire [31:0] display_source=early_request?progress_source:reader_source;
 wire [15:0] display_target=early_request?progress_target:result_target;
 wire geometry_package_update=(axis_display_update||early_axis_update)&&
  (!geometry_have||!geometry_needle_valid||display_needle);
 assign display_value_valid=display_value_have&&!display_revoke&&calibration_valid;
 always @(posedge core_clk or negedge rst_n)begin
  if(!rst_n)begin display_value_have<=0;display_owner_target<=0;display_value_update<=0;display_value_bcd<=0;display_value_q16<=0;display_value_source<=0;end
  else begin
   display_value_update<=0;
   if(display_revoke)begin display_value_have<=0;display_value_bcd<=0;display_value_q16<=0;display_value_source<=0;end
   else begin
    if(geometry_package_update)display_owner_target<=display_target;
    if(!calibration_valid)begin display_value_have<=0;display_value_bcd<=0;display_value_q16<=0;display_value_source<=0;end
    else if(guard_update&&value_valid)begin
     display_value_have<=1;display_owner_target<=guard_target;display_value_update<=1;
     display_value_bcd<=guard_bcd;display_value_q16<=guard_q16;display_value_source<=guard_source;
    end
   end
  end
 end
 always @(posedge core_clk or negedge rst_n)begin
  if(!rst_n)begin geometry_have<=0;geometry_hub_x<=0;geometry_hub_y<=0;geometry_center_x<=0;geometry_center_y<=0;geometry_diameter<=0;geometry_roll<=0;geometry_source<=0;geometry_needle_valid<=0;geometry_needle_angle<=0;geometry_x0<=0;geometry_x1<=0;geometry_y0<=0;geometry_y1<=0;end
  else if(display_revoke)begin geometry_have<=0;geometry_source<=0;geometry_needle_valid<=0;geometry_needle_angle<=0;end
  else if(geometry_package_update)begin
    geometry_have<=1;geometry_hub_x<=display_nx[10:0];geometry_hub_y<=display_ny[9:0];geometry_source<=display_source;
    geometry_center_x<=confirm_x;geometry_center_y<=confirm_y;geometry_diameter<=confirmed_diameter;geometry_roll<=confirmed_roll;
    geometry_x0<=confirmed_x0;geometry_x1<=confirmed_x1;geometry_y0<=confirmed_y0;geometry_y1<=confirmed_y1;
    geometry_needle_valid<=display_needle;geometry_needle_angle<=display_needle?display_angle:9'd0;
  end // One failed number/pose observation retains the whole successful package.
 end
 // These six bits are the same observation's existing readability vetoes,
 // not the guard's next-cycle priority reason. [5]identity+printed support,
 // [4]diameter,[3]roll,[2]thin detail,[1]ROI geometry candidate,[0]number.
 // No bit changes any permission, candidate, calibration or numeric result.
 always @(posedge core_clk or negedge rst_n)begin
  if(!rst_n)begin
   diag_valid<=0;diag_source<=0;diag_reader_reason<=0;diag_fail_mask<=0;
   diag_stage_flags<=0;diag_diameter<=0;diag_roll<=0;diag_print_count<=0;
   diag_needle_count<=0;diag_needle_score<=0;diag_angle<=0;diag_mean<=0;diag_capture_debug<=0;
  end else if(display_hard_revoke)diag_valid<=0;
  else if(observation)begin
   if(reader_source==confirm_source&&result_cfg==active_config&&result_target==active_target_id&&capture_motion==motion_epoch)begin
    diag_valid<=1;diag_source<=reader_source;diag_reader_reason<=reader_reason;
    diag_fail_mask<={!(confirm_identity&&frontal_compatible),!scale_ok,!roll_ok,!detail_ok,!roi_candidate,!roi_number};
    diag_stage_flags<=roi_stage_flags;diag_diameter<=confirmed_diameter;diag_roll<=confirmed_roll;diag_print_count<=confirmed_count;
    diag_needle_count<=needle_count;diag_needle_score<=needle_score;diag_angle<=needle_angle;diag_mean<=mean_gray;diag_capture_debug<={reader_capture_debug[120:32],mcu_result_crc};
   end else diag_valid<=0;
  end
 end
 assign debug_owner_valid=owner_valid;assign debug_owner_source=owner_source;
 assign debug_roi_armed=roi_armed;assign debug_release=release_valid;
 wire [2:0] next_stride;wire [10:0] next_span,origin_x;wire [9:0] origin_y;
 wire [6:0] next_radius;wire request_bounds;
 meter_roi_window_policy roi_policy(.box_x0(px0),.box_x1(px1),.box_y0(py0),.box_y1(py1),.diameter(pdiam),
  .partial_seen(pair_partial),.crop_x(origin_x),.crop_y(origin_y),.span(next_span),.stride(next_stride),
  .radius(next_radius),.available(request_bounds),.analysis_only());
 // Confirmation uses the SAME frozen stride as capture, including stride2.
 wire [10:0] track_rgeom=roi_stride==1?({1'b0,pdiam}+11'd1)>>1:
                       roi_stride==2?({1'b0,pdiam}+11'd2)>>2:
                       roi_stride==3?({1'b0,pdiam}+11'd3)/11'd6:
                                     ({1'b0,pdiam}+11'd4)>>3;
 wire [6:0] track_radius=track_rgeom>62?7'd62:track_rgeom[6:0];
 wire [11:0] held_crop_right={1'b0,roi_x}+{2'd0,roi_stride,7'd0};
 wire [10:0] held_crop_bottom={1'b0,roi_y}+{1'b0,roi_stride,7'd0};
 // Actual T coverage only; no diameter499 proxy or hint-S partial veto.
 wire track_crop_complete=px0<=px1&&py0<=py1&&px1<=1280&&py1<=720&&
  px0>=roi_x&&py0>=roi_y&&{1'b0,px1}<=held_crop_right&&{1'b0,py1}<=held_crop_bottom;
 wire [31:0] source_delta=owner_source-hint_source;
 task remember_hint;
  begin
   hint_source<=psource;hint_epoch<=pepoch;hint_cfg<=pcfg;hint_lease<=please;
   roi_x<=origin_x;roi_y<=origin_y;roi_stride<=next_stride;roi_radius<=next_radius;
   confirmed_partial<=0;confirmed_crop_complete<=0;
  end
 endtask
 // Reader owns one immutable hint/expected-T/epoch bundle until completion.
 // Its ROI pixels are private; the full-frame lease may be released after
 // TRACK without waiting for hub/needle arithmetic to finish.

 // RAW CORE registers establish protection before CPU/NN completion.
 wire job_frozen=read_job_active&&read_confirmed&&roi_owned_good&&roi_owned_source==read_expected_source;
 assign measurement_fault=roi_result&&reader_reason==21;
 // Coherent owner metadata / existing CORE ARM sync; not a CPU-only reset detector.
 assign source_context_bad=owner_valid&&(read_job_active||geometry_have||display_value_have)&&(owner_epoch!=hint_epoch||owner_cfg!=hint_cfg);
 assign platform_context_bad=(read_job_active||geometry_have||display_value_have)&&!roi_platform_armed;
 reg [31:0] frame_source,frame_epoch,frame_cfg,frame_lease;
 reg [31:0] arm_cycles,read_job_age;
 wire read_watchdog_revoke=read_job_active&&((read_job_age>=2&&roi_ready&&!roi_result&&!reader_result_pending)||
                       read_job_age>=MAX_READ_JOB_CYCLES-1);
 wire [31:0] read_delta=owner_source-hint_source;
 wire owned_frame=owner_valid&&owner_source==frame_source&&owner_epoch==frame_epoch&&owner_cfg==frame_cfg&&owner_lease==frame_lease;
 assign pair_context_good=owned_frame&&psource==frame_source&&pepoch==frame_epoch&&pcfg==frame_cfg&&please==frame_lease;
 // Continuous localisation runs regardless; only parked CNN starts here.
 wire can_prepare_reader=global_lock&&!reacquire_due&&request_bounds&&location_valid&&stationary;
 // Compact passive taps only. Global-MCU live block owns all sinceARM history.
 assign observer_context={13'd0,first_cancel_cause,
  worker_cancel,read_job_active,!owned_frame,!roi_ready,!stationary,!location_valid,!request_bounds,reacquire_due,!global_lock,
  observer_display_fault,stream_fault,!rst_n,(state==DECIDE_NEXT),(pair_done&&pair_valid),owner_valid};

 task release_frame;
  begin release_valid<=1;release_lease<=frame_lease;state<=WAIT_RELEASE;phase_cycles<=0;end
 endtask
 task withdraw_reader;
  input soft_origin;input [3:0] cause_code;
  begin
   if(read_job_active&&first_cancel_cause==0)cancel_cause_event<=cause_code;
   roi_request<=0;roi_cancel<=1;roi_cancel_soft<=soft_origin;read_job_active<=0;read_waiting_T<=0;read_confirmed<=0;
   reader_result_pending<=0;confirm_identity<=0;confirm_pose<=0;observation<=0;
   confirmed_partial<=0;confirmed_crop_complete<=0;
  end
 endtask
 always @(posedge core_clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=WAIT_OWNER;phase_cycles<=0;last_config<=0;last_motion<=0;restart_cancel<=0;
   pair_start<=0;pair_track<=0;scan_is_track<=0;release_valid<=0;release_lease<=0;
   cancel_cause_event<=0;
   roi_request<=0;roi_cancel<=0;roi_cancel_soft<=0;observation<=0;reader_result_pending<=0;confirm_valid<=0;
   location_have<=0;location_partial<=0;location_roll<=0;location_age_cycles<=0;box_x0<=0;box_x1<=0;box_y0<=0;box_y1<=0;
   center_x<=0;center_y<=0;diameter<=0;location_source<=0;location_epoch<=0;pipeline_reason<=1;
   roi_x<=0;roi_y<=0;roi_stride<=3;roi_radius<=0;hint_source<=0;hint_epoch<=0;hint_cfg<=0;hint_lease<=0;
   active_target_id<=0;capture_lower_ms<=0;capture_motion<=0;confirmed_partial<=0;confirmed_crop_complete<=0;
   confirm_identity<=0;confirm_pose<=0;confirm_source<=0;confirm_x<=0;confirm_y<=0;confirm_radius<=0;
   confirmed_count<=0;confirmed_diameter<=0;confirmed_roll<=0;
   confirmed_x0<=0;confirmed_x1<=0;confirmed_y0<=0;confirmed_y1<=0;
   read_job_active<=0;read_waiting_T<=0;read_confirmed<=0;read_expected_source<=0;
   frame_source<=0;frame_epoch<=0;frame_cfg<=0;frame_lease<=0;arm_cycles<=0;read_job_age<=0;
  end else begin
   last_config<=active_config;last_motion<=motion_epoch;pair_start<=0;release_valid<=0;
   cancel_cause_event<=0;
   roi_cancel<=0;roi_cancel_soft<=0;observation<=0;confirm_valid<=0;restart_cancel<=0;
   if(location_age_cycles!=32'hffffffff)location_age_cycles<=location_age_cycles+1'b1;
   if(!read_job_active)read_job_age<=0;
   else if(read_job_age!=32'hffffffff)read_job_age<=read_job_age+1'b1;
   if(location_age_cycles>=MAX_LOCATION_AGE_CYCLES-1)location_have<=0;
   if(state==WAIT_OWNER)phase_cycles<=0;
   else if(phase_cycles!=32'hffffffff)phase_cycles<=phase_cycles+1'b1;
   // A failed ROI may finish before its same-T TRACK. Preserve notification,
   // but never overwrite its source/target/window with a later tracking hint.
   if(roi_result&&read_job_active)reader_result_pending<=1;
   if((roi_result||reader_result_pending)&&read_job_active&&read_confirmed&&(!read_withdraw||job_frozen))begin
    reader_result_pending<=0;read_job_active<=0;read_confirmed<=0;
    if(reader_source==confirm_source&&reader_source==read_expected_source&&
       (!roi_number||confirmed_source==confirm_source)&&result_cfg==hint_cfg&&
       result_cfg==active_config&&result_target==active_target_id&&capture_motion==motion_epoch)begin
     observation<=1;
    end else begin
     if(read_job_active&&first_cancel_cause==0)cancel_cause_event<=4'd13;
     roi_cancel<=1;confirm_identity<=0;confirm_pose<=0;end
   end
   if(measurement_fault||(read_job_active&&(motion_change||!stationary)))withdraw_reader(1'b0,measurement_fault?4'd8:4'd7);
   else if(read_job_active&&read_withdraw&&!job_frozen)withdraw_reader(1'b1,4'd9);
   // Reader expiry/abort can return to IDLE without result_pulse.  Retire
   // that job only after its real req_ready/drained contract, or request its
   // existing cancel/lease-release procedure on the sole2s no-return fault
   // watchdog (not a source-age/read-accuracy or133ms inference gate).
   // A new job is still impossible until reader req_ready returns; no pending
   // pixel return or CDC ownership is silently cleared by this controller.
   if(read_watchdog_revoke)begin
    withdraw_reader(1'b0,4'd1);pipeline_reason<=17;
   end
   if(worker_cancel)begin
    state<=WAIT_OWNER;withdraw_reader(1'b0,phase_timeout?4'd2:stream_fault?4'd4:restart_cancel?4'd3:(context_change||source_context_bad||platform_context_bad)?4'd5:4'd6);location_have<=0;
    pipeline_reason<=phase_timeout?5'd15:5'd1;
   end else case(state)
    WAIT_OWNER:if(owner_valid&&owner_cfg==active_config&&!pair_busy)begin
     frame_source<=owner_source;frame_epoch<=owner_epoch;frame_cfg<=owner_cfg;frame_lease<=owner_lease;
     pair_track<=global_lock&&!reacquire_due;scan_is_track<=global_lock&&!reacquire_due;
     pair_start<=1;state<=SEARCH_WAIT;phase_cycles<=0;pipeline_reason<=global_lock?5'd8:5'd2;
     if(read_job_active&&read_waiting_T&&!read_withdraw)begin
      if(owner_epoch==hint_epoch&&owner_cfg==hint_cfg&&read_delta!=0&&!read_delta[31]&&global_lock&&!reacquire_due)begin
       read_expected_source<=owner_source;read_waiting_T<=0;
      end else if(owner_epoch==hint_epoch&&owner_cfg==hint_cfg&&read_delta!=0&&!read_delta[31]&&reacquire_due)begin
       // A routine recheck may cancel this unconfirmed reader, but it is not
       // failed evidence about earlier completed T observations. Reader still
       // receives the real cancel and must drain its existing claimed lease.
       withdraw_reader(1'b1,4'd12);
      end else withdraw_reader(1'b0,4'd12);
     end
    end
    SEARCH_WAIT:if(pair_done)begin
     if(pair_fault||!pair_valid||!pair_context_good||
        (scan_is_track?!pair_fresh:!pair_margin_valid))begin
      restart_cancel<=1;withdraw_reader(1'b0,4'd3);location_have<=0;pipeline_reason<=3;state<=RESTART;
     end else begin
      // An old SEARCH S is only an internal acquisition hint. Exact displayed
      // geometry requires a measured source age within the same 200ms budget.
      if(page<MAX_LOCATION_AGE_CYCLES)begin
       location_have<=1;location_age_cycles<=page;box_x0<=px0;box_x1<=px1;box_y0<=py0;box_y1<=py1;
       center_x<=pcx;center_y<=pcy;diameter<=pdiam;location_source<=psource;location_epoch<=pepoch;location_partial<=pair_partial;location_roll<=pair_roll_degrees;
      end else location_have<=0;
      if(!scan_is_track)active_target_id<=target_id[15:0];
      if(read_job_active&&!read_waiting_T&&read_expected_source==psource&&!read_withdraw&&scan_is_track)begin
       confirm_valid<=1;confirm_identity<=1;confirm_pose<=controlled_frontal_setup;
       confirmed_partial<=pair_partial;confirmed_crop_complete<=track_crop_complete;
       confirm_source<=psource;confirm_x<=pcx;confirm_y<=pcy;confirm_radius<=track_radius[6:0];
       confirmed_count<=pair_count;confirmed_diameter<=pdiam;confirmed_roll<=pair_roll_degrees;
       confirmed_x0<=px0;confirmed_x1<=px1;confirmed_y0<=py0;confirmed_y1<=py1;
       read_confirmed<=1;
      end
      state<=DECIDE_NEXT;phase_cycles<=0;pipeline_reason<=4;
     end
    end
    DECIDE_NEXT:begin
     if(!owned_frame)begin restart_cancel<=1;withdraw_reader(1'b0,4'd10);state<=RESTART;pipeline_reason<=5;end
     else if(!read_job_active&&can_prepare_reader&&roi_ready)begin
      remember_hint();roi_request<=1;state<=REQUEST_ROI;pipeline_reason<=6;
     end else begin
      // No read ROI, bad optical permit, or a busy reader never blocks TRACK.
      release_frame();pipeline_reason<=request_bounds?5'd12:5'd13;
     end
    end
    REQUEST_ROI:begin
     if(!owned_frame)begin restart_cancel<=1;withdraw_reader(1'b0,4'd10);state<=RESTART;pipeline_reason<=5;end
     else if(!can_prepare_reader)begin
      // Only lost location/recheck permission is soft. Bad crop bounds,
      // stop permission, ownership or reader readiness remains hard.
      withdraw_reader(request_bounds&&stationary&&roi_ready,4'd9);release_frame();pipeline_reason<=12;
     end
     else if(roi_request&&roi_ready)begin
      roi_request<=0;read_job_active<=1;read_waiting_T<=1;read_confirmed<=0;
      reader_result_pending<=0;arm_cycles<=0;read_job_age<=0;state<=WAIT_ARMED;
     end
    end
    WAIT_ARMED:begin
     arm_cycles<=arm_cycles+1'b1;
     if(!owned_frame)begin restart_cancel<=1;withdraw_reader(1'b0,4'd10);state<=RESTART;pipeline_reason<=5;end
     else if(arm_cycles>=MAX_ARM_CYCLES-1)begin
      withdraw_reader(1'b0,4'd11);release_frame();pipeline_reason<=14;
     end else if(read_withdraw)begin
      withdraw_reader(1'b1,4'd9);release_frame();pipeline_reason<=14;
     end else if(roi_armed)begin
      // This lower bound precedes the actual fresh T SOF. It may reject a
      // borderline post-stop capture, never label a pre-stop T as post-stop.
      capture_lower_ms<=now_ms;capture_motion<=motion_epoch;release_frame();pipeline_reason<=7;
     end
    end
    WAIT_RELEASE:if(!owner_valid)begin state<=WAIT_OWNER;phase_cycles<=0;end
    RESTART:state<=WAIT_OWNER;
    default:begin restart_cancel<=1;withdraw_reader(1'b0,4'd3);state<=RESTART;pipeline_reason<=16;end
   endcase
   // These hard causes can coincide with a later soft branch above. They
   // always dominate the guard-only cause tag; ROI cancel/drain is unchanged.
   if(measurement_fault||read_watchdog_revoke||worker_cancel||motion_change||!stationary)roi_cancel_soft<=0;
  end
 end
endmodule
