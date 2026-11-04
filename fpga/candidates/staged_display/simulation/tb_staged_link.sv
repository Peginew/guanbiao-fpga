`timescale 1ns/1ps
// Real production visual->link->OSD/pressure path. CNN and accepted TRACK-T
// are explicit stimulus frontiers; no camera/NN accuracy or elapsed seconds
// are claimed. Raster coordinate injection tests the actual cross/line drawer.
module tb_staged_link;
 reg clk=0,rst=0,mcu_rst=0,vs=0,de=0,fault=0;always #5 clk=~clk;
 reg stage_have=0,stage_pulse=0,stage_needle=0,confirm=0,confirmed=0;
 reg job=1,phase_timeout=0,watchdog_cancel=0,hard_restart=0,lock=1;
 reg [31:0] stage_source=100,expect_source=100,confirm_source=100,cfg=1,motion=1;
 reg [15:0] target=7;reg [8:0] stage_angle=0;
 reg [10:0] stage_hx=1024,stage_hy=1024,test_x=0;reg [9:0] test_y=0;
 reg [30:0] bus_addr=0;reg [1:0] bus_trans=0;wire [31:0] bus_data;wire [1:0] bus_resp;wire bus_ready;reg final_result=0;
 wire [23:0] rgb;wire[3:0] flags;wire[251:0] payload;wire psi_valid;
 t06_meter_pair_link #(.STATIC_FRONTAL_BENCH(1),.REFERENCE_DEBOUNCE_CYCLES(5)) dut(
 .csi_clk(clk),.hdmi_clk(clk),.arst_n(rst),.mcu_clk(clk),.mcu_arst_n(mcu_rst),
 .mcu_haddr(bus_addr),.mcu_htrans(bus_trans),.mcu_hwrite(1'b0),.mcu_hsize(3'd2),.mcu_hwdata(32'd0),.mcu_hrdata(bus_data),.mcu_hresp(bus_resp),.mcu_hready(bus_ready),
 .gray4(32'd0),.gray_valid(1'b0),.gray_sof(1'b0),.gray_eol(1'b0),.frame_error(1'b0),.source_id(32'd0),.source_valid(1'b0),
 .vs(vs),.de(de),.rgb(24'd0),.preset_sw(2'd0),.display_id_valid(1'b1),.display_source_id(stage_source),
 .display_good(1'b1),.display_fault(fault),.analysis_fault(fault),
 .out_rgb(rgb),.ui_flags(flags),.ui_payload(payload),.ui_psi_valid(psi_valid));
 integer checks=0;reg [31:0] cause_read1,cause_read2;
 task ck(input bit yes,input string why);begin checks=checks+1;if(!yes)$fatal(1,"STAGED_LINK_FAIL %s time=%0t",why,$time);end endtask
 task tick(input integer n);begin repeat(n)@(negedge clk);#1;end endtask
 task frame;begin de=0;vs=1;tick(3);vs=0;de=1;tick(12);end endtask
 task early(input bit needle,input [8:0] angle);begin stage_have=1;stage_needle=needle;stage_angle=angle;stage_pulse=1;tick(1);stage_pulse=0;tick(3);end endtask
 task read_cause(output [31:0] value);integer n;begin
 @(negedge clk);bus_addr='h208;bus_trans=2;@(negedge clk);bus_trans=0;n=0;
 while(!bus_ready&&n<20)begin @(negedge clk);n=n+1;end
 ck(bus_ready&&bus_resp==0,"passive208 read completes without owner");value=bus_data;@(negedge clk);
 end endtask
 task reset_all;begin rst=0;mcu_rst=0;final_result=0;stage_have=0;stage_pulse=0;stage_needle=0;confirm=0;confirmed=0;
  job=1;phase_timeout=0;watchdog_cancel=0;hard_restart=0;lock=1;fault=0;target=7;cfg=1;motion=1;
  stage_source=100;expect_source=100;confirm_source=100;stage_hx=1024;stage_hy=1024;vs=0;de=0;
  tick(4);rst=1;mcu_rst=1;tick(12);end endtask
 initial begin
  // Force only locator/reader accepted evidence and their frozen owner context.
  // The production geometry cache, native mapping, hard-revoke, link snapshot,
  // OSD source qualification, finite direction line and pressure path run.
  force dut.pipeline.state=0;force dut.pipeline.owner_valid=0;
  force dut.pipeline.source_context_bad=0;force dut.pipeline.platform_context_bad=0;
  force dut.pipeline.restart_cancel=hard_restart;force dut.pipeline.phase_timeout=phase_timeout;
  force dut.pipeline.roi_cancel=watchdog_cancel;force dut.pipeline.pipeline_reason=17;
  force dut.pipeline.active_target_id=target;force dut.pipeline.active_config=cfg;force dut.pipeline.last_config=1;
  force dut.pipeline.motion_epoch=motion;force dut.pipeline.last_motion=1;
  force dut.pipeline.global_lock=lock;force dut.pipeline.location_have=1;force dut.pipeline.location_age_cycles=0;
  force dut.pipeline.center_x=641;force dut.pipeline.center_y=361;force dut.pipeline.diameter=368;force dut.pipeline.location_roll=0;
  force dut.pipeline.box_x0=457;force dut.pipeline.box_x1=825;force dut.pipeline.box_y0=177;force dut.pipeline.box_y1=545;
  force dut.pipeline.location_source=100;
  force dut.pipeline.read_job_active=job;force dut.pipeline.read_confirmed=confirmed;
  force dut.pipeline.read_expected_source=expect_source;force dut.pipeline.hint_cfg=1;force dut.pipeline.capture_motion=1;
  force dut.pipeline.confirm_identity=1;force dut.pipeline.confirm_valid=confirm;force dut.pipeline.confirm_source=confirm_source;
  force dut.pipeline.confirm_x=641;force dut.pipeline.confirm_y=361;force dut.pipeline.confirm_radius=60;
  force dut.pipeline.confirmed_diameter=368;force dut.pipeline.confirmed_roll=0;
  force dut.pipeline.confirmed_x0=457;force dut.pipeline.confirmed_x1=825;force dut.pipeline.confirmed_y0=177;force dut.pipeline.confirmed_y1=545;
  force dut.pipeline.roi_owned_good=1;force dut.pipeline.roi_owned_source=expect_source;
  force dut.pipeline.progress_have=stage_have;force dut.pipeline.progress_pulse=stage_pulse;
  force dut.pipeline.progress_needle=stage_needle;force dut.pipeline.progress_hx=stage_hx;force dut.pipeline.progress_hy=stage_hy;
  force dut.pipeline.progress_x=448;force dut.pipeline.progress_y=168;force dut.pipeline.progress_stride=3;force dut.pipeline.progress_radius=60;
  force dut.pipeline.progress_source=stage_source;force dut.pipeline.progress_config=1;force dut.pipeline.progress_target=7;
  force dut.pipeline.progress_angle=stage_angle;
  force dut.pipeline.roi_result=final_result;force dut.pipeline.observation=0;
  force dut.osd.x=test_x;force dut.osd.y=test_y;
  reset_all();job=0;phase_timeout=1;tick(3);ck(dut.pipeline.first_cancel_cause==0,"no activejob cannot create cancellation history");reset_all();
  early(0,0);ck(!dut.geometry_valid&&!dut.pipeline.geometry_have,"hub waits only for same-T confirmation, not scalar");
  confirmed=1;confirm=1;tick(1);confirm=0;tick(3);
  ck(dut.geometry_valid&&dut.geometry_source==100&&!dut.geometry_needle_valid,"held early hub publishes when matching T arrives");
  ck(dut.native_hub_x==641&&dut.native_hub_y==361,"stride3 block-center mapping stays exact");
  ck(!dut.observation&&!dut.vu&&!dut.vv&&!psi_valid,"early hub never grants currentREAD or PSI");
  frame();ck(flags[1]&&!flags[2]&&payload[65:57]==511,"actual OSD qualifies axis without scalar or direction");
  test_x=643;test_y=361;#1;ck(dut.osd.cross_ink&&rgb==24'h00ffff,"actual link RGB paints verified hub cross");
  early(1,0);frame();test_x=663;test_y=361;#1;
  ck(dut.geometry_valid&&dut.geometry_needle_valid&&dut.geometry_needle_angle==0,"needle independently joins same source package");
  ck(dut.osd.needle_ink&&!dut.osd.cross_ink&&rgb==24'h00ffff,"actual finite direction line paints away from cross");
  ck(!dut.vv&&!flags[2]&&!psi_valid&&!dut.segment_valid,"no PSI or number sevenseg manufactured");
  phase_timeout=1;tick(3);ck(dut.geometry_valid&&!dut.display_hard_revoke&&!dut.vv,"phase deadline cancels CURRENT but retains display geometry");
  ck(dut.pipeline.first_cancel_cause==2,"phase withdraw captured as passive cause2");
  read_cause(cause_read1);read_cause(cause_read2);ck(cause_read1==2&&cause_read2==2,"two settled reads208 match persistent cause");
  phase_timeout=0;watchdog_cancel=1;tick(3);frame();
  ck(dut.geometry_valid&&flags[1]&&!flags[2]&&!dut.display_hard_revoke&&!dut.vv,"pure reader watchdog17 keeps axis and needle, never CURRENTREAD");
  ck(dut.pipeline.first_cancel_cause==2,"later watchdog cannot overwrite firstcause");
  rst=0;tick(3);ck(dut.pipeline.first_cancel_cause==2,"video reset does not clear global firstcause");rst=1;tick(6);
  reset_all();confirmed=1;early(1,0);
  watchdog_cancel=0;
  stage_source=101;confirm_source=101;expect_source=101;stage_hx=1040;early(0,0);
  ck(dut.geometry_source==100&&dut.geometry_needle_valid&&dut.native_hub_x==641,"new hub-only never pairs new hub with old needle/source");
  early(1,90);tick(2);
  ck(dut.geometry_source==101&&dut.geometry_needle_angle==90&&dut.native_hub_x==644,"new complete pointer replaces entire package");
  stage_source=102;stage_hx=1300;early(1,180);
  ck(dut.geometry_source==101&&dut.geometry_needle_angle==90,"wrong-source message cannot replace frozen package");
  target=8;#1;ck(dut.display_hard_revoke&&!dut.geometry_valid,"target conflict immediately revokes");tick(2);ck(!dut.pipeline.geometry_have,"target conflict clears package");
  reset_all();confirmed=1;early(1,0);cfg=2;#1;ck(dut.display_hard_revoke&&!dut.geometry_valid,"config change revokes geometry");
  reset_all();confirmed=1;early(1,0);motion=2;#1;ck(dut.display_hard_revoke&&!dut.geometry_valid,"motion epoch revokes geometry");
  reset_all();confirmed=1;early(1,0);hard_restart=1;#1;ck(dut.display_hard_revoke&&!dut.geometry_valid,"failed SEARCH restart revokes geometry");
  reset_all();confirmed=1;early(1,0);fault=1;#1;ck(dut.display_hard_revoke&&!dut.geometry_valid,"real stream fault revokes geometry");
  reset_all();confirmed=1;phase_timeout=1;
  force dut.pipeline.measurement_fault=1;force dut.pipeline.read_watchdog_revoke=1;
  tick(3);ck(dut.pipeline.first_cancel_cause==2,"same-cycle measurement thenwatchdog thenphase records last call cause2");
  release dut.pipeline.measurement_fault;release dut.pipeline.read_watchdog_revoke;phase_timeout=0;
  reset_all();confirmed=1;final_result=1;tick(3);final_result=0;
  ck(dut.pipeline.first_cancel_cause==13,"direct final metadata rejection cause13 is recorded");
  reset_all();
  force dut.pipeline.owner_valid=1;force dut.pipeline.owner_epoch=1;force dut.pipeline.owner_cfg=1;
  force dut.pipeline.owner_source=200;force dut.pipeline.hint_epoch=1;force dut.pipeline.hint_source=100;
  force dut.pipeline.read_waiting_T=1;force dut.pipeline.reacquire_due=1;force dut.pipeline.pair_busy=0;
  tick(3);ck(dut.pipeline.first_cancel_cause==12,"unconfirmed routine recheck captured as cause12");
  $display("PASS STAGED_LINK checks=%0d real_visual_link_osd_RGB_no_final_no_pressure explicit_evidence_and_raster_frontiers",checks);$finish;
 end
 initial begin #200000;$fatal(1,"staged link timeout");end
endmodule
