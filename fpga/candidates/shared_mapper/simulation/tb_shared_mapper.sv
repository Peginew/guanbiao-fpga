`timescale 1ns/1ps
// Real reader/formatter, explicit completed-live-ROI boundary stimulus. The
// capture/MCU execution is NOT simulated by forcing this boundary bundle.
module tb_shared_mapper;
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

 reg [10:0] fx=0,fhx=0,fhy=0,px=0,phx=0,phy=0;reg [9:0] fy=0,py=0;reg [2:0] st=1,mode=2;
 reg [31:0] finalcode=0;integer checks=0,k,i,j,expected_x,expected_y;reg [12:0] saved_x,saved_y;
 task ck(input bit yes,input string why);begin checks=checks+1;if(!yes)$fatal(1,"SHARED_MAPPER_FAIL %s state%0d stride%0d q%0d time%0t",why,dut.state,st,j,$time);end endtask
 function integer reference(input integer x0,input integer q4,input integer stride);
  reg [16:0] sum;begin sum=(x0<<4)+q4*stride+((stride-1)<<3);reference=((sum+17'd8)>>4);end
 endfunction
 task tick;begin @(negedge clk);#1;end endtask
 initial begin
  force dut.state=mode;force dut.owner_target=1;force dut.owner_config=1;force dut.live_ready=1;force dut.live_busy=1;
  force dut.live_progress=stagepulse;force dut.live_progress_code=stagecode;force dut.live_result=livepulse;
  force dut.live_token={32'd1,source,32'd1};force dut.live_hint=90;force dut.live_config=1;force dut.live_target=1;
  force dut.live_x=px;force dut.live_y=py;force dut.live_stride=st;force dut.live_radius=60;
  force dut.live_crc_ok=1;force dut.live_bytes=16384;force dut.live_crc=32'h12345678;force dut.live_qgood=1;force dut.live_flags=3;
  force dut.live_code=finalcode;force dut.live_psi_q8=0;force dut.live_psi_valid=0;
  force dut.result_x0=fx;force dut.result_y0=fy;force dut.result_stride=st;force dut.hub_x_q4=fhx;force dut.hub_y_q4=fhy;
  repeat(5)tick();rst=1;repeat(5)tick();
  force dut.progress_valid=0;force dut.progress_needle_valid=0;
  // Every supported Q4 coordinate and fractional tie, each stride1..4,
  // frame-adjacent and maximum unsigned window origin. Reference preserves
  // original17bit Q4 sum,+8 and>>4. No clipping/negative reinterpretation.
  for(k=1;k<=4;k=k+1)for(i=0;i<3;i=i+1)for(j=0;j<=2032;j=j+1)begin
   st=k;fx=i==0?0:i==1?767:2047;fy=i==0?0:i==1?207:1023;fhx=j;fhy=2032-j;
   px=i==0?128:i==1?511:2047;py=i==0?64:i==1?333:1023;phx=2032-j;phy=j;
   mode=2;stagepulse=0;#1;
   ck(dut.native_hub_x==reference(fx,fhx,st)&&dut.native_hub_y==reference(fy,fhy,st),"final original arithmetic");
   mode=1;stagecode=32'h44000000|(phx<<11)|phy;stagepulse=1;#1;
   ck(dut.map_progress&&dut.native_hub_x==reference(px,phx,st)&&dut.native_hub_y==reference(py,phy,st),"early same mapper original arithmetic");
  end
  stagepulse=0;release dut.progress_valid;release dut.progress_needle_valid;
  rst=0;tick();rst=1;repeat(4)tick();
  mode=1;st=4;px=764;py=204;phx=2032;phy=0;stagecode=32'h44000000|(phx<<11)|phy;stagepulse=1;tick();stagepulse=0;tick();
  saved_x=reference(px,phx,st);saved_y=reference(py,phy,st);
  ck(dut.progress_valid&&!dut.progress_needle_valid&&dut.progress_native_x==saved_x&&dut.progress_native_y==saved_y,"actual early native cache edge");
  // TRACK can arrive after CONFIRM/PUBLISH/IDLE: cache must retain the
  // original early code/window while final registers and live bus change.
  for(i=0;i<3;i=i+1)begin mode=i==0?2:i==1?4:0;fx=77+i;fy=55+i;fhx=0;fhy=0;px=3;py=4;stagecode=0;tick();
   ck(dut.progress_native_x==saved_x&&dut.progress_native_y==saved_y&&dut.progress_valid,"late TRACK cache independent of final and live buses");end
  // Full follows hub; later HUB_ONLY cannot mix a new hub into old needle.
  mode=1;stagecode=32'h80000000|(32'd90<<22)|(32'd1024<<11)|32'd1024;stagepulse=1;tick();stagepulse=0;tick();
  saved_x=dut.progress_native_x;saved_y=dut.progress_native_y;
  ck(dut.progress_needle_valid&&dut.progress_angle==90,"full native package accepted");
  stagecode=32'h44000000|(32'd64<<11)|32'd64;stagepulse=1;tick();stagepulse=0;tick();
  ck(dut.progress_needle_valid&&dut.progress_native_x==saved_x&&dut.progress_native_y==saved_y,"hub-only preserves complete needle package");
  // Invalid coordinate never produces a new native package.
  stagecode=32'h80000000|(32'd90<<22)|(32'd2047<<11)|32'd1024;stagepulse=1;tick();stagepulse=0;tick();
  ck(dut.progress_native_x==saved_x&&dut.progress_native_y==saved_y,"invalid q4 rejected before mapping cache");
  // Kill clears validity; stale data may remain but cannot authorize display.
  cancel=1;tick();ck(!dut.progress_valid,"cancel withdraws native package validity");cancel=0;
  // Same accept edge as final result (stronger than HQUIET legal ordering).
  // Next CONFIRM must use final code while early cache keeps its own values.
  mode=1;stagepulse=0;tick();
  release dut.state;release dut.result_x0;release dut.result_y0;release dut.result_stride;release dut.hub_x_q4;release dut.hub_y_q4;
  force dut.state=1;
  st=3;px=448;py=168;stagecode=32'h44000000|(32'd1024<<11)|32'd1024;
  finalcode=32'h80000000|(32'd275<<22)|(32'd1008<<11)|32'd1008;
  stagepulse=1;livepulse=1;tick();stagepulse=0;livepulse=0;release dut.state;#1;
  ck(dut.progress_native_x==641&&dut.progress_native_y==361,"simultaneous early capture keeps incoming code");
  // State was held WAIT only at the edge; force intended next CONFIRM to
  // avoid relying on force-release register procedural simulator semantics.
  force dut.state=2;#1;
  ck(dut.native_hub_x==638&&dut.native_hub_y==358&&dut.progress_native_x==641,"final CONFIRM uses final registers not early cache");
  release dut.state;
  $display("PASS SHARED_MAPPER checks=%0d exact_supported_Q4_s1to4_unsigned_bounds_stage_cache_final_selection",checks);$finish;
 end
 initial begin #1000000;$fatal(1,"shared mapper timeout");end
endmodule
