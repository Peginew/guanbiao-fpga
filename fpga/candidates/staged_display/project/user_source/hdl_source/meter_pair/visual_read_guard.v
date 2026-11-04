`timescale 1ns/1ps
// All signals are in the analysis clock domain. This module grants no motion.
// stationary must come from matching STOP/DONE feedback or an explicit fixed-
// camera test permit. capture_epoch is latched at sensor SOF, never at completion.
// Global SEARCH results are hints only; READ requires a new local-confirmed ROI.
module visual_read_guard #(
 // Compatibility parameter only; current owned parked evidence has noTTL.
 parameter integer MAX_AGE_MS=500,
 parameter integer POSITION_TOL=6,RADIUS_TOL=2,ANGLE_TOL=3
)(
 input wire clk,rst_n,enabled,cancel,stream_fault,stationary,
 // Soft CURRENT withdrawal preserves completed same-owner stability history.
 // The parent still cancels/drains a new ROI when its own contract requires it.
 input wire soft_withdraw,
 input wire [31:0] now_ms,motion_epoch,active_config,
 input wire [15:0] active_target,
 input wire calibration_valid,
 input wire observation,
 input wire local_confirm,identity_ok,pose_ok,focus_ok,exposure_ok,roi_good,needle_ok,number_valid,
 input wire [31:0] capture_ms,capture_epoch,detector_source,reader_source,observation_config,
 input wire [15:0] observation_target,
 input wire [10:0] center_x,
 input wire [9:0] center_y,
 input wire [8:0] radius,
 input wire [8:0] angle,
 input wire [15:0] number_q16,number_bcd,
 output reg value_update,value_valid,
 output reg [15:0] value_q16,value_bcd,value_target,
 output reg [31:0] value_source,
 output reg [1:0] position_observations,needle_observations,
 output reg [4:0] reason
);
 reg have_previous,watermark_valid,previous_stationary;
 reg [31:0] source_watermark,previous_epoch,previous_config,shadow_epoch,shadow_config;
 reg [15:0] previous_target,shadow_target;
 reg [10:0] previous_x;
 reg [9:0] previous_y;
 reg [8:0] previous_radius;
 reg [8:0] previous_angle;
 reg [31:0] stop_ms;
 wire [31:0] source_delta=detector_source-source_watermark;
 wire [31:0] after_stop_ms=capture_ms-stop_ms;
 wire owner_changed=shadow_epoch!=motion_epoch||shadow_config!=active_config||shadow_target!=active_target;
 wire same_owner=previous_epoch==capture_epoch&&previous_config==observation_config&&previous_target==observation_target;
 // A failed quality/read attempt never resets the stream's anti-replay floor.
 wire source_new=(!watermark_valid)||(source_delta!=0&&!source_delta[31]);
 wire [10:0] dx=center_x>=previous_x?center_x-previous_x:previous_x-center_x;
 wire [9:0] dy=center_y>=previous_y?center_y-previous_y:previous_y-center_y;
 wire [8:0] dr=radius>=previous_radius?radius-previous_radius:previous_radius-radius;
 wire [8:0] da0=angle>=previous_angle?angle-previous_angle:previous_angle-angle;
 wire [8:0] da=da0>180?360-da0:da0;
 // Each test uses its own window anchor. Adjacent small drifts must not add up
 // to an apparently stable window whose total displacement exceeds tolerance.
 wire position_step=have_previous&&same_owner&&dx<=POSITION_TOL&&dy<=POSITION_TOL&&dr<=RADIUS_TOL;
 wire needle_step=have_previous&&same_owner&&da<=ANGLE_TOL;
 wire [1:0] next_position=position_step?(position_observations==3?2'd3:position_observations+1'b1):2'd1;
 wire [1:0] next_needle=needle_step?(needle_observations==3?2'd3:needle_observations+1'b1):2'd1;
 wire bcd_ok=number_bcd[15:12]<=9&&number_bcd[11:8]<=9&&number_bcd[7:4]<=9&&number_bcd[3:0]<=9;
 task withdraw_current;
  input [4:0] why;
  begin
   value_update<=value_valid;value_valid<=0;value_q16<=0;value_bcd<=0;value_source<=0;value_target<=0;
   reason<=why;
  end
 endtask
 task withdraw;
  input [4:0] why;
  begin
   withdraw_current(why);
   have_previous<=0;position_observations<=0;needle_observations<=0;
  end
 endtask
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   value_update<=0;value_valid<=0;value_q16<=0;value_bcd<=0;value_source<=0;value_target<=0;
   position_observations<=0;needle_observations<=0;reason<=1;have_previous<=0;
   source_watermark<=0;watermark_valid<=0;previous_stationary<=0;stop_ms<=0;
   previous_epoch<=0;previous_config<=0;previous_target<=0;
   previous_x<=0;previous_y<=0;previous_radius<=0;previous_angle<=0;
   shadow_epoch<=0;shadow_config<=0;shadow_target<=0;
  end else begin
   value_update<=0;
   shadow_epoch<=motion_epoch;shadow_config<=active_config;shadow_target<=active_target;
   previous_stationary<=stationary;
   if(stationary&&!previous_stationary)stop_ms<=now_ms;
   if(owner_changed)watermark_valid<=0;
   else if(observation&&enabled&&!cancel&&!stream_fault&&stationary&&
           capture_epoch==motion_epoch&&observation_config==active_config&&observation_target==active_target&&
           detector_source==reader_source&&source_new)begin
    source_watermark<=detector_source;watermark_valid<=1;
   end
   if(!enabled||cancel)withdraw(1);
   else if(!stationary)withdraw(2);
   else if(!previous_stationary)withdraw(2);
   else if(stream_fault)withdraw(3);
   else if(owner_changed)withdraw(4);
   else if(!calibration_valid)withdraw(12);
   else if(observation)begin
    if(capture_epoch!=motion_epoch||observation_config!=active_config||observation_target!=active_target)withdraw(4);
    // Actual source capture must follow STOP. Processing latency itself
    // does not invalidate a still-owned stationary observation.
    else if(after_stop_ms==0||after_stop_ms[31])withdraw(5);
    else if(detector_source!=reader_source||!source_new)withdraw(6);
    else if(!local_confirm||!identity_ok)withdraw(7);
    else if(!focus_ok||!exposure_ok||!roi_good)withdraw(8);
    else if(!pose_ok||center_x>=1280||center_y>=720||radius==0||angle>=360)withdraw(9);
    else if(!needle_ok||!number_valid)withdraw(10);
    else if(!bcd_ok)withdraw(13);
    else begin
     have_previous<=1;previous_epoch<=capture_epoch;
     previous_config<=observation_config;previous_target<=observation_target;
     if(!position_step)begin previous_x<=center_x;previous_y<=center_y;previous_radius<=radius;end
     if(!needle_step)previous_angle<=angle;
     position_observations<=next_position;needle_observations<=next_needle;
     if(next_position==3&&next_needle==3&&!soft_withdraw)begin
      value_update<=1;value_valid<=1;value_q16<=number_q16;value_bcd<=number_bcd;
      value_source<=detector_source;value_target<=observation_target;reason<=0;
     end else begin
      withdraw_current(soft_withdraw?5'd14:5'd11);
     end
    end
   end else if(soft_withdraw)withdraw_current(14);
  end
 end
endmodule
