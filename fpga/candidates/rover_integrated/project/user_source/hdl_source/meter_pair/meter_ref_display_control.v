// Manual reference display only. Never authorizes a reader or vehicle action.
// Physical SW3 is bit0; SW4 is bit1. Values are decimal BCD psi, not bar.
// All logic uses the existing HDMI clock; switches are data, never clocks.
module meter_ref_display_control #(
 parameter integer ENABLE_REFERENCE=1,
 parameter integer DEBOUNCE_CYCLES=1500000, //20ms at the existing75MHz HDMI clock
 parameter integer MAX_SOURCE_AGE=12,
 // Existing now_ms is a floor-quantized millisecond counter. 3001 avoids
 // granting before three real seconds at its millisecond boundary.
 parameter integer STABLE_WAIT_MS=3001,
 parameter integer POSITION_TOLERANCE=4,
 // Match the existing locator's 200ms maximum publication age. This is a
 // watchdog for missing fresh observations, not a new CNN deadline.
 parameter integer MAX_FRESH_GAP_MS=200
)(
 input wire clk,rst_n,vs,
 input wire [1:0] preset_sw,
 input wire location_valid,box_legal,
 input wire [31:0] location_source_id,target_id,
 input wire [31:0] display_source_id,
 input wire display_good,display_fault,hard_revoke,
 input wire location_lock,
 input wire [10:0] center_x,
 input wire [9:0] center_y,
 input wire [11:0] now_ms,
 output reg [1:0] mode,
 output wire [15:0] value_bcd,
 output wire value_valid,
 output reg value_update,
 output reg config_changed
);
 localparam CW=DEBOUNCE_CYCLES<=1?1:$clog2(DEBOUNCE_CYCLES);
 (* ASYNC_REG="TRUE" *) reg [1:0] switch_sync0,switch_sync1;
 reg [1:0] switch_candidate,switch_debounced;
 reg [CW-1:0] stable_count;
 reg vs_prev,eligible;
 reg [31:0] owner_target;
 wire [1:0] switch_input=ENABLE_REFERENCE?preset_sw:2'b00;
 wire boundary=vs&&!vs_prev;
 wire [31:0] source_age=display_source_id-location_source_id;
 wire candidate_ok=location_valid&&box_legal&&!source_age[31]&&source_age<=MAX_SOURCE_AGE;
 wire healthy=display_good&&!display_fault&&!hard_revoke;
 localparam GW=MAX_FRESH_GAP_MS<2?1:$clog2(MAX_FRESH_GAP_MS+1);
 reg anchor_active,stable_ready,source_seen,confirmation_needed;
 reg [10:0] anchor_x;reg [9:0] anchor_y;
 reg [11:0] stable_start_ms;
 reg [GW-1:0] last_fresh_ms;
 reg [31:0] last_source;
 wire [10:0] anchor_dx=center_x>=anchor_x?center_x-anchor_x:anchor_x-center_x;
 wire [9:0] anchor_dy=center_y>=anchor_y?center_y-anchor_y:anchor_y-center_y;
 wire anchor_close=anchor_dx<=POSITION_TOLERANCE&&anchor_dy<=POSITION_TOLERANCE;
 wire [11:0] elapsed_ms=now_ms-stable_start_ms;
 wire [GW-1:0] fresh_age_ms=now_ms[GW-1:0]-last_fresh_ms;
 wire fresh_gap=anchor_active&&fresh_age_ms>=MAX_FRESH_GAP_MS;
 wire [31:0] source_delta=location_source_id-last_source;
 wire source_forward=!source_seen||(!source_delta[31]&&source_delta!=0);
 wire owner_changed=target_id!=owner_target;
 wire stable_reset=display_fault||hard_revoke||owner_changed;
 wire fresh_observation=candidate_ok&&healthy&&location_lock&&!stable_reset&&source_forward;
 wire stability_grant=fresh_observation&&anchor_active&&!fresh_gap&&anchor_close&&
                      !stable_ready&&elapsed_ms>=STABLE_WAIT_MS;
 wire confirmation_grant=fresh_observation&&confirmation_needed&&stable_ready&&
                         anchor_active&&!fresh_gap&&anchor_close;
 assign value_bcd=mode==1?16'h0250:mode==2?16'h0800:mode==3?16'h1200:16'h0000;
 assign value_valid=ENABLE_REFERENCE&&(mode!=0)&&eligible&&candidate_ok&&healthy&&
                    !stable_reset&&location_lock&&!confirmation_needed&&anchor_active&&stable_ready&&anchor_close&&!fresh_gap;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   anchor_active<=0;stable_ready<=0;source_seen<=0;confirmation_needed<=1;anchor_x<=0;anchor_y<=0;
   stable_start_ms<=0;last_fresh_ms<=0;last_source<=0;
  end else if(stable_reset)begin
   anchor_active<=0;stable_ready<=0;source_seen<=0;confirmation_needed<=1;
  end else begin
   // Planned same-target SEARCH also lowers raw lock. Preserve the bounded
   // position history, but require a new source before showing again. Keep
   // completed readiness latched across the 12-bit millisecond wrap.
   if(!location_lock)confirmation_needed<=1;
   if(fresh_gap)begin anchor_active<=0;stable_ready<=0;confirmation_needed<=1;end
   if(fresh_observation)begin
    confirmation_needed<=0;
    source_seen<=1;last_source<=location_source_id;last_fresh_ms<=now_ms[GW-1:0];
    if(!anchor_active||fresh_gap||!anchor_close)begin
     anchor_active<=1;stable_ready<=0;anchor_x<=center_x;anchor_y<=center_y;
     stable_start_ms<=now_ms;
    end else if(stability_grant)stable_ready<=1;
   end
  end
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin switch_sync0<=0;switch_sync1<=0;end
  else begin switch_sync0<=switch_input;switch_sync1<=switch_sync0;end
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   switch_candidate<=0;switch_debounced<=0;stable_count<=0;
  end else if(switch_sync1!=switch_candidate)begin
   switch_candidate<=switch_sync1;stable_count<=0;
  end else if(switch_debounced!=switch_candidate)begin
   if(DEBOUNCE_CYCLES<=1||stable_count==DEBOUNCE_CYCLES-1)begin
    switch_debounced<=switch_candidate;stable_count<=0;
   end else stable_count<=stable_count+1'b1;
  end else stable_count<=0;
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   vs_prev<=0;mode<=0;eligible<=0;owner_target<=0;value_update<=0;config_changed<=0;
  end else begin
   vs_prev<=vs;value_update<=0;config_changed<=0;
   // Mode and target ownership still change only at VS. A temporary source
   // or display-health gap must not latch an otherwise healthy REF off for
   // the rest of the raster. Re-admit only the same owner, with every original
   // locator/age/health check satisfied. This never authorizes a real READ.
   if(!candidate_ok||!healthy||!location_lock||target_id!=owner_target)eligible<=0;
   else if(!eligible)begin
    eligible<=1;
    // The seven-segment consumer cancels its pending packet on withdrawal.
    // Publish the reference again when validity returns, rather than waiting
    // for the next VS packet.
    value_update<=1;
   end
   // First completion of the stable window must republish the packet, too.
   if(stability_grant||confirmation_grant)value_update<=1;
   if(boundary)begin
    mode<=switch_debounced;
    config_changed<=mode!=switch_debounced;
    owner_target<=target_id;
    eligible<=candidate_ok&&healthy&&location_lock;
    value_update<=1;
   end
  end
 end
endmodule
