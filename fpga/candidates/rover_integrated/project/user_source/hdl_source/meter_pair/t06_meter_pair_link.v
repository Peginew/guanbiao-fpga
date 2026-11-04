// Explicit stationary/frontal FIXTURE candidate, not autonomous rover firmware.
// Default permits are off. The isolated board-cost top must explicitly opt in;
// a production rover must supply real STOP/DONE and calibrated setup inputs.
module t06_meter_pair_link #(
 parameter PAIR_FILE="C:/Users/Edward/Desktop/FPGA/Stable3s_Rover_Merged_20261104/fpga/project/user_source/hdl_source/meter_pair/pair_base_rom.mem",TRIG_FILE="C:/Users/Edward/Desktop/FPGA/Stable3s_Rover_Merged_20261104/fpga/project/user_source/hdl_source/meter_pair/needle_trig128.hex",
 parameter STATIC_FRONTAL_BENCH=0,
 parameter ENABLE_REFERENCE=1,REFERENCE_DEBOUNCE_CYCLES=1500000,
 parameter ENABLE_ROVER_UART=0
)(
 input wire csi_clk,hdmi_clk,arst_n,
 input wire mcu_clk,mcu_arst_n,
 input wire [30:0] mcu_haddr,input wire [1:0] mcu_htrans,input wire mcu_hwrite,
 input wire [2:0] mcu_hsize,input wire [31:0] mcu_hwdata,
 output wire [31:0] mcu_hrdata,output wire [1:0] mcu_hresp,output wire mcu_hready,

 input wire [31:0] gray4,input wire gray_valid,gray_sof,gray_eol,frame_error,
 input wire [31:0] source_id,input wire source_valid,
 input wire vs,de,input wire [23:0] rgb,
 input wire [1:0] preset_sw,
 input wire display_id_valid,input wire [31:0] display_source_id,
 input wire display_good,display_fault,
 input wire analysis_fault,
 output wire [23:0] out_rgb,output wire out_vs,out_de,
 output wire [7:0] segment_n,digit_select_n,
 output wire [251:0] ui_payload,output wire [71:0] ui_debug,
 output wire [3:0] ui_flags,output wire ui_estimated,
 output wire [31:0] ui_age_loc,ui_age_geo,ui_age_read,
 output wire [15:0] ui_psi,output wire ui_psi_valid,
 output wire [31:0] ui_psi_source,output wire ui_hard_fault,
 output wire [1:0] ui_ref_mode,output wire ui_ref_valid,
 output wire [15:0] ui_ref_psi,
 input wire rover_rx,output wire rover_tx
);
 wire rst_n;
 t06_reset_release release_hdmi(.clk(hdmi_clk),.arst_n(arst_n),.rst_n(rst_n));
 wire csi_rst_n;
 t06_reset_release release_csi(.clk(csi_clk),.arst_n(arst_n),.rst_n(csi_rst_n));
 // Only the private analysis branch is registered; source identity moves with it.
 reg [31:0] ga,sa;reg gv,gs,ge,gf,sv;
 always @(posedge csi_clk or negedge csi_rst_n)begin
  if(!csi_rst_n)begin ga<=0;sa<=0;gv<=0;gs<=0;ge<=0;gf<=0;sv<=0;end
  else begin ga<=gray4;sa<=source_id;gv<=gray_valid;gs<=gray_sof;ge<=gray_eol;gf<=frame_error;sv<=source_valid;end
 end
 reg [16:0] divider;reg [31:0] now_ms;
 always @(posedge hdmi_clk or negedge rst_n)begin
  if(!rst_n)begin divider<=0;now_ms<=0;end
  else if(divider==74999)begin divider<=0;now_ms<=now_ms+1'b1;end
  else divider<=divider+1'b1;
 end
 wire rover_stationary,rover_cancel,rover_reader_revoke,rover_task_active;wire [31:0] rover_motion_epoch;
 // Vehicle permits own only an accepted rover task. With no task, retain the
 // trained standalone manual/AUTO path and its explicit bench assumptions.
 // Keep one retirement beat for that task's final cancel/revoke pulse.
 reg rover_task_was_active;
 always @(posedge hdmi_clk or negedge rst_n)begin
  if(!rst_n)rover_task_was_active<=0;else rover_task_was_active<=rover_task_active;
 end
 wire rover_task_scope=ENABLE_ROVER_UART&&(rover_task_active||rover_task_was_active);
 wire pipeline_stationary=rover_task_scope?rover_stationary:(STATIC_FRONTAL_BENCH!=0);
 wire [31:0] pipeline_motion_epoch=rover_task_scope?rover_motion_epoch:32'd1;
 wire vu,vv,loc,lock;wire [15:0] q16,bcd,vt;wire [31:0] vsource,lsource,lepoch,target;
 // Only these LAST-success signals drive displays. vu/vv remain truecontrol
 // evidence and are never replaced by cached display validity.
 wire display_value_update,display_value_valid,display_hard_revoke;wire [15:0] display_value_bcd,display_value_q16;wire [31:0] display_value_source;
 wire [10:0] x0,x1,cx;wire [9:0] y0,y1,cy,diam;
 wire location_partial,locator_observation_update;wire[1:0]locator_observation_kind;
 wire[31:0]locator_observation_source,locator_observation_age_cycles;wire[5:0]locator_observation_error;
 wire [3:0] state;wire [4:0] reason,rreason,greason;wire [7:0] print_count;
 wire [15:0] nscore;wire [5:0] ncount;wire [8:0] angle;
 wire readable;wire [31:0] rsource,confirmed_source;wire observation;
 wire geometry_valid;wire [10:0] native_hub_x;wire [9:0] native_hub_y;wire [31:0] geometry_source;
 wire [43:0] geometry_box_payload;
 wire geometry_held_only;
 wire geometry_needle_valid;wire [8:0] geometry_needle_angle;
 wire [120:0] diag_capture_debug;
 wire diag_valid;wire [31:0] diag_source;wire [4:0] diag_reader_reason,diag_stage_flags;
 wire [5:0] diag_fail_mask;wire [9:0] diag_diameter;wire signed [4:0] diag_roll;wire [7:0] diag_print_count;
 t06_meter_visual_pipeline #(.PAIR_FILE(PAIR_FILE),.TRIG_FILE(TRIG_FILE),
  .MAX_PHASE_CYCLES(1800000000),.MAX_READ_JOB_CYCLES(1500000000)) pipeline(
  .mcu_clk(mcu_clk),.mcu_arst_n(mcu_arst_n),.mcu_haddr(mcu_haddr),.mcu_htrans(mcu_htrans),
  .mcu_hwrite(mcu_hwrite),.mcu_hsize(mcu_hsize),.mcu_hwdata(mcu_hwdata),
  .mcu_hrdata(mcu_hrdata),.mcu_hresp(mcu_hresp),.mcu_hready(mcu_hready),
  .core_clk(hdmi_clk),.csi_clk(csi_clk),.arst_n(arst_n),
  .enabled(1'b1),.cancel(rover_task_scope&&rover_cancel),.reader_revoke(rover_task_scope&&rover_reader_revoke),.stream_fault(analysis_fault),
  .observer_display_fault(display_fault&&!analysis_fault),
  .gray4(ga),.gray_valid(gv),.gray_sof(gs),.gray_eol(ge),.frame_error(gf),
  .source_valid(sv),.source_id(sa),.source_epoch(32'd1),.cfg_revision(32'd1),
  .now_ms(now_ms),.motion_epoch(pipeline_motion_epoch),.active_config(32'd1),
  // UART mode supplies real estimated vehicle state; optical/calibration permits
  // remain explicit limited bench assumptions, never field-validation evidence.
  .stationary(pipeline_stationary),.controlled_frontal_setup(STATIC_FRONTAL_BENCH!=0),
  .focus_setup_permit(STATIC_FRONTAL_BENCH!=0),.calibration_valid(STATIC_FRONTAL_BENCH!=0),
  .value_update(vu),.value_valid(vv),.value_q16(q16),.value_bcd(bcd),.value_source(vsource),.value_target(vt),
  .display_value_update(display_value_update),.display_value_valid(display_value_valid),.display_hard_revoke(display_hard_revoke),
  .display_value_bcd(display_value_bcd),.display_value_q16(display_value_q16),.display_value_source(display_value_source),
  .location_valid(loc),.box_x0(x0),.box_x1(x1),.box_y0(y0),.box_y1(y1),.center_x(cx),.center_y(cy),.diameter(diam),
  .location_source(lsource),.location_epoch(lepoch),.global_lock(lock),.target_id(target),
  .location_partial(location_partial),.locator_observation_update(locator_observation_update),
  .locator_observation_kind(locator_observation_kind),.locator_observation_source(locator_observation_source),
  .locator_observation_age_cycles(locator_observation_age_cycles),.locator_observation_error(locator_observation_error),
  .pipeline_state(state),.pipeline_reason(reason),.read_reason(greason),.reader_reason(rreason),.printed_count(print_count),
  .needle_score(nscore),.needle_count(ncount),.needle_angle(angle),.image_readability_candidate(readable),
  .reader_source(rsource),.confirmed_source(confirmed_source),.reader_observation(observation),
  .geometry_valid(geometry_valid),.native_hub_x(native_hub_x),.native_hub_y(native_hub_y),.geometry_source(geometry_source),
  .geometry_box_payload(geometry_box_payload),
  .geometry_held_only(geometry_held_only),
  .geometry_needle_valid(geometry_needle_valid),.geometry_needle_angle(geometry_needle_angle),
  .diag_valid(diag_valid),.diag_source(diag_source),.diag_reader_reason(diag_reader_reason),.diag_fail_mask(diag_fail_mask),
  .diag_stage_flags(diag_stage_flags),.diag_diameter(diag_diameter),.diag_roll(diag_roll),.diag_print_count(diag_print_count),
  .diag_needle_count(),.diag_needle_score(),.diag_angle(),.diag_mean(),.diag_capture_debug(diag_capture_debug),
  .debug_owner_valid(),.debug_roi_armed(),.debug_release(),.debug_owner_source());
 wire psi_update,psi_valid;wire [15:0] psi_hundredths,psi_bcd;wire [31:0] psi_source;
 wire pressure_revoke=display_fault||display_hard_revoke;
 t06_ui_pressure_display pressure_display(.clk(hdmi_clk),.rst_n(rst_n),
  .value_update(display_value_update),.value_valid(display_value_valid),.revoke(pressure_revoke),
  .bar_q16(display_value_q16),.source_id(display_value_source),
  .psi_update(psi_update),.psi_valid(psi_valid),.psi_hundredths(psi_hundredths),.psi_bcd(psi_bcd),.psi_source(psi_source));
 assign ui_psi=psi_hundredths;assign ui_psi_valid=psi_valid;
 assign ui_psi_source=psi_source;assign ui_hard_fault=pressure_revoke;
 // Manual REF is an independent display value; it never changes READ evidence.
 // Preserve the already-reviewed helper's locator/age/health/owner contract.
 wire [1:0] reference_mode;wire [15:0] reference_bcd;
 wire reference_valid,reference_update,reference_config_changed;
 meter_ref_display_control #(.ENABLE_REFERENCE(ENABLE_REFERENCE),.DEBOUNCE_CYCLES(REFERENCE_DEBOUNCE_CYCLES)) reference_control(
  .clk(hdmi_clk),.rst_n(rst_n),.vs(vs),.preset_sw(preset_sw),
  .location_valid(loc),.box_legal(x0<x1&&y0<y1&&x1<=1280&&y1<=720),
  .location_source_id(lsource),.target_id(target),.display_source_id(display_source_id),
  .display_good(display_good),.display_fault(display_fault),.hard_revoke(1'b0),
  .location_lock(lock),.center_x(cx),.center_y(cy),.now_ms(now_ms[11:0]),
  .mode(reference_mode),.value_bcd(reference_bcd),.value_valid(reference_valid),
  .value_update(reference_update),.config_changed(reference_config_changed));
 wire reference_selected=ENABLE_REFERENCE&&(reference_mode!=0);
 wire segment_valid=reference_selected?reference_valid:psi_valid;
 wire segment_update=reference_selected?reference_update:(psi_update||reference_config_changed);
 wire [15:0] segment_bcd=reference_selected?reference_bcd:psi_bcd;
 wire segment_cancel=display_fault||(reference_selected?!reference_valid:(display_hard_revoke||!psi_valid));
 assign ui_ref_mode=reference_mode;assign ui_ref_valid=reference_valid;
 assign ui_ref_psi=reference_mode==1?16'd250:reference_mode==2?16'd800:reference_mode==3?16'd1200:16'd0;
 generate if(ENABLE_ROVER_UART)begin:g_rover_uart
  wire fence_request,fence_idle,fence_ready;wire [31:0] fence_source;
  wire link_up;
  rover_source_fence u_source_fence(.core_clk(hdmi_clk),.core_rst_n(rst_n),
   .csi_clk(csi_clk),.csi_rst_n(csi_rst_n),.request(fence_request),
   .csi_source(source_id),.csi_source_valid(source_valid),
   .idle(fence_idle),.ready(fence_ready),.source_floor(fence_source));
  rover_uart_link u_rover_uart(.clk(hdmi_clk),.rst_n(rst_n),.now_ms(now_ms),
   .uart_rx(rover_rx),.uart_tx(rover_tx),
   .healthy(!analysis_fault&&!display_fault),.location_valid(loc),.location_lock(lock),.readable(readable),
   .pipeline_state(state),.read_reason(greason),
   .camera_update(display_id_valid),.camera_source(display_source_id),.camera_good(display_good&&!display_fault),
   .observation_update(locator_observation_update),.observation_kind(locator_observation_kind),
   .observation_source(locator_observation_source),.observation_age_cycles(locator_observation_age_cycles),
   .box_left(x0),.box_right(x1),.box_top(y0),.box_bottom(y1),.box_partial(location_partial),.box_credible(loc&&lock),
   .current_read_update(vu),.current_read_valid(vv),.raw_bar_q16(q16),.current_read_source(vsource),
   .ref_mode(reference_mode),.ref_valid(reference_valid),.ref_psi100(ui_ref_psi),
   .fence_idle(fence_idle),.fence_ready(fence_ready),.fence_source(fence_source),.fence_request(fence_request),
   .link_up(link_up),.task_active(rover_task_active),.stationary_permit(rover_stationary),
   .motion_epoch(rover_motion_epoch),.analysis_cancel(rover_cancel),.reader_revoke(rover_reader_revoke));
 end else begin:g_no_rover_uart
  assign rover_tx=1'b1;assign rover_stationary=1'b0;assign rover_motion_epoch=32'd1;assign rover_cancel=1'b0;assign rover_reader_revoke=1'b0;assign rover_task_active=1'b0;
 end endgenerate
 t06_meter_sevenseg #(.SCAN_DIV(9375),.BLANK_CYCLES(375),.SETUP_CYCLES(75),.EXPIRE_CYCLES(0)) digits(
  .clk(hdmi_clk),.rst_n(rst_n),.cancel(segment_cancel),.value_update(segment_update),.value_valid(segment_valid),
  .value_bcd({16'hffff,segment_bcd}),.decimal_mask(8'h20),.digit_select_n(digit_select_n),.segment_n(segment_n),.showing_value(),.bcd_fault());
 // Same clock for analysis + OSD: one atomic snapshot, no extra mailbox or PLL.
 // The previously unused score upper byte carries the live pipeline reason.
 wire [251:0] payload={loc,x0,{1'b0,y0},x1,{1'b0,y1},cx,{1'b0,cy},lsource,target[15:0],{3'd0,reason,print_count},
                      geometry_valid,geometry_source,native_hub_x,{1'b0,native_hub_y},geometry_needle_valid?geometry_needle_angle:9'd511,display_value_valid,display_value_bcd,display_value_source,{3'd0,greason}};
 wire [71:0] debug_payload={diag_valid,diag_source,diag_reader_reason,diag_fail_mask,diag_stage_flags,diag_diameter,diag_roll,diag_print_count};
 // Preserve the proven additional complete pixel stage, including source tags.
 reg [23:0] pixel_rgb;reg pixel_vs,pixel_de,pixel_id_valid,pixel_good,pixel_fault;
 reg [31:0] pixel_id;reg [251:0] pixel_payload;
 reg [71:0] pixel_debug_payload;reg [120:0] pixel_capture_debug;
 reg [43:0] pixel_geometry_box;
 reg pixel_geometry_held_only;
 always @(posedge hdmi_clk or negedge rst_n)begin
  if(!rst_n)begin pixel_rgb<=0;pixel_vs<=0;pixel_de<=0;pixel_id_valid<=0;pixel_good<=0;pixel_fault<=1;pixel_id<=0;pixel_payload<=0;pixel_debug_payload<=0;pixel_capture_debug<=0;pixel_geometry_box<=0;pixel_geometry_held_only<=0;end
  else begin pixel_rgb<=rgb;pixel_vs<=vs;pixel_de<=de;pixel_id_valid<=display_id_valid;pixel_good<=display_good;
   pixel_fault<=display_fault;pixel_id<=display_source_id;pixel_payload<=payload;pixel_debug_payload<=debug_payload;pixel_capture_debug<=diag_capture_debug;pixel_geometry_box<=geometry_box_payload;pixel_geometry_held_only<=geometry_held_only;end
 end
 assign out_vs=pixel_vs;assign out_de=pixel_de;
 t06_meter_pair_bench_osd #(.ENABLE_CAPTURE_DIAGNOSTICS(0),.HOLD_RESULTS(1),.SEPARATE_GEOMETRY_BOX(1),.TRIG_FILE(TRIG_FILE),.HELD_ONLY_ENABLE(1),.DRAW_TEXT(0)) osd(.clk(hdmi_clk),.rst_n(rst_n),.vs(pixel_vs),.de(pixel_de),.rgb(pixel_rgb),
  .geometry_box_payload(pixel_geometry_box),
  .geometry_held_only(pixel_geometry_held_only),
  .update(1'b1),.payload(pixel_payload),.debug_payload(pixel_debug_payload),.capture_debug_payload(pixel_capture_debug),.revoke(display_fault||display_hard_revoke),
  .display_id_valid(pixel_id_valid),.display_source_id(pixel_id),.display_good(pixel_good),.display_fault(pixel_fault|display_fault),.out_rgb(out_rgb),
   .qualified_payload(ui_payload),.qualified_debug(ui_debug),.qualified_flags(ui_flags),
   .qualified_estimated(ui_estimated),.age_loc(ui_age_loc),.age_geo(ui_age_geo),.age_read(ui_age_read));
endmodule
