`timescale 1ns/1ps
// Real reader/formatter, explicit completed-live-ROI boundary stimulus. The
// capture/MCU execution is NOT simulated by forcing this boundary bundle.
module tb_staged_reader;
 reg clk=0;always #5 clk=~clk;reg rst=0,request=0,cancel=0;
 wire ready,pulse,number;wire[15:0]q,bcd;wire[8:0]angle;wire[4:0]flags;
 reg livebusy=0,stagepulse=0;reg [31:0] stagecode=0;
 reg [31:0] source=100;reg livepulse=0,psiv=1;reg[15:0]psi=2560;
 t06_meter_roi_reader dut(.csi_clk(clk),.clk(clk),.arst_n(rst),.mcu_clk(clk),.mcu_arst_n(rst),.observer_context(32'd0),
 .mcu_haddr(31'd0),.mcu_htrans(2'd0),.mcu_hwrite(1'b0),.mcu_hsize(3'd2),.mcu_hwdata(32'd0),.mcu_hrdata(),.mcu_hresp(),.mcu_hready(),
 .gray4(32'd0),.gray_valid(1'b0),.gray_sof(1'b0),.gray_eol(1'b0),.frame_error(1'b0),.source_id(32'd0),.source_id_valid(1'b0),.capture_frame_allowed(1'b0),
 .enabled(1'b1),.cancel(cancel),.active_target(16'd1),.active_config(32'd1),.req_valid(request),.req_ready(ready),
 .req_x0(11'd400),.req_y0(10'd100),.req_stride(3'd2),.req_radius(7'd60),.req_hint_source(32'd90),.req_target(16'd1),.req_config(32'd1),
 .confirm_valid(1'b1),.confirm_detector_evidence_ok(1'b1),.confirm_pose_ok(1'b1),.confirm_number_permit(1'b1),
 .confirm_source(source),.confirm_config(32'd1),.confirm_target(16'd1),.confirm_center_x(11'd529),.confirm_center_y(10'd229),.confirm_radius(7'd60),
 .calibration_valid(1'b1),.cal_angle0(9'd142),.cal_angle1(9'd169),.cal_angle2(9'd191),.cal_angle3(9'd231),
 .cal_value0(16'd0),.cal_value1(16'd13763),.cal_value2(16'd20972),.cal_value3(16'd33423),
 .busy(),.capture_armed(),.owned_roi_good(),.owned_roi_source(),.platform_armed(),.hub_x_q4(),.hub_y_q4(),.mcu_result_crc(),
 .result_pulse(pulse),.candidate_valid(),.value_valid(number),.visual_stable(),.reason(),.result_hint_source(),.result_source(),.result_confirmed_source(),.result_config(),
 .result_target(),.result_x0(),.result_y0(),.result_stride(),.hub_x(),.hub_y(),.angle_index(angle),.value_bcd(bcd),.value_q16(q),.result_age_cycles(),.stable_observations(),
 .quality_mean(),.quality_gradient(),.result_needle_score(),.result_needle_count(),.stage_flags(flags),.result_cnn_valid(),.result_cnn_pass(),.result_cnn_margin(),.result_capture_debug());
 integer checks=0,timeout;
 task check;input condition;input[255:0]why;begin if(!condition)begin $display("FAIL STAGED_READER %s state=%0d reason=%0d",why,dut.state,dut.reason);$fatal;end checks=checks+1;end endtask
 task startjob;begin
  @(negedge clk);request=1;while(!ready)@(negedge clk);@(negedge clk);request=0;
  livepulse=1;@(negedge clk);livepulse=0;
 end endtask
 task waitresult;begin timeout=0;while(!pulse&&timeout<40)begin @(negedge clk);timeout=timeout+1;end check(pulse,"reader result pulse");end endtask
 initial begin
  force dut.live_ready=1;force dut.live_busy=livebusy;force dut.live_progress=stagepulse;force dut.live_progress_code=stagecode;force dut.live_result=livepulse;
  force dut.live_token={32'd1,source,32'd1};force dut.live_hint=90;force dut.live_config=1;force dut.live_target=1;
  force dut.live_x=400;force dut.live_y=100;force dut.live_stride=2;force dut.live_radius=60;
  force dut.live_crc_ok=1;force dut.live_bytes=16384;force dut.live_crc=32'h12345678;force dut.live_qgood=1;force dut.live_flags=3;
  force dut.live_code=32'h80000000|(32'd275<<22)|(32'd1024<<11)|32'd1024;
  force dut.live_psi_q8=psi;force dut.live_psi_valid=psiv;
  repeat(5)@(negedge clk);rst=1;repeat(5)@(negedge clk);
  // Early evidence reaches the real reader without a final result/PSI.
  livebusy=1;@(negedge clk);request=1;while(!ready)@(negedge clk);@(negedge clk);request=0;
  stagecode=32'h44000000|(32'd1024<<11)|32'd1024;stagepulse=1;@(negedge clk);stagepulse=0;@(negedge clk);
  check(dut.progress_valid&&!dut.progress_needle_valid&&!pulse&&!number&&!dut.candidate_valid,"hub appears before any final result");
  check(dut.progress_source==100&&dut.progress_hub_x_q4==1024,"stage tied to current ROI metadata");
  stagecode=32'h80000000|(32'd275<<22)|(32'd1024<<11)|32'd1024;stagepulse=1;@(negedge clk);stagepulse=0;@(negedge clk);
  check(dut.progress_valid&&dut.progress_needle_valid&&dut.progress_angle==275&&!pulse&&!number,"needle stage before scalar or RES1");
  stagecode=1;stagepulse=1;@(negedge clk);stagepulse=0;@(negedge clk);
  check(dut.progress_needle_valid&&dut.progress_angle==275,"invalid final-code class cannot erase reliable stage");
  cancel=1;@(negedge clk);check(!dut.progress_valid&&!number,"hard cancel clears held stage");
  cancel=0;livebusy=0;repeat(4)@(negedge clk);
  startjob;waitresult;check(number&&q==45185&&angle==275,"10psi actual angle275 outside oldTEST");check(flags[3:2]==3,"axis and needle retained");
  @(negedge clk);source=101;psiv=0;startjob;waitresult;
  check(!number&&flags[3:2]==3,"geometry survives missing scalar evidence");
  @(negedge clk);source=102;psiv=1;startjob;repeat(5)@(negedge clk);cancel=1;@(negedge clk);check(!number,"cancelled scalar suppressed");
  $display("PASS STAGED_READER checks=%0d actual_reader_formatter_explicit_completed_ROI_frontier",checks);$finish;
 end
 initial begin #100000;$display("FAIL STAGED_READER timeout");$fatal;end
endmodule
