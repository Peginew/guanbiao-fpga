// One debouncedpress cycles0..19. Saturationgain comes fromindependentSWcfg.
// K4 / KEY3 / C7: active-low button, R73 external 10k pull-up to 3.3V.
// One event per press; requires a debounced release before the next event.
// Runs in the camera byte clock domain; cfg_mode is therefore not an async bus.
module t06_mode_control #(
 parameter [4:0] BOOT_MODE=0,
 parameter integer DEBOUNCE_CYCLES=2070000 // 20ms at 103.5MHz; time follows CSI clock
)(
 input clk,rst_n, input key_n,
 output reg [4:0] mode
);
 localparam CW=(DEBOUNCE_CYCLES<=1)?1:$clog2(DEBOUNCE_CYCLES);
 (* ASYNC_REG="TRUE" *) reg sync0,sync1;
 reg [CW-1:0] count;
 reg pressed;
 wire key_pressed=~sync1;
 always @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin sync0<=1'b1;sync1<=1'b1;end
  else begin sync0<=key_n;sync1<=sync0;end
 end
 always @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin count<=0;pressed<=0;mode<=BOOT_MODE<20?BOOT_MODE:5'd0;end
  else if(key_pressed==pressed) count<=0;
  else if(count==DEBOUNCE_CYCLES-1) begin
   count<=0;pressed<=key_pressed;
   if(key_pressed) mode<=mode==19?5'd0:mode+1'b1;
  end else count<=count+1'b1;
 end
endmodule
