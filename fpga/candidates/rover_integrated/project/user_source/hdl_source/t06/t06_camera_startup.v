// Nominal 24 MHz reference; present PLL is 23.809524 MHz (conservative delays).
// Hold XSHUTDN low for 2 ms, then wait 10 ms before I2C initialization.
// Board rails still need physical validation; this module has no rail-good input.
module t06_camera_startup #(
 parameter integer CLOCK_HZ=24000000
)(input clk, input rst_n, output reg camera_reset_n, output reg i2c_ready);
 localparam integer HOLD_CYCLES=(CLOCK_HZ+499)/500;
 localparam integer WAIT_CYCLES=(CLOCK_HZ+99)/100;
 localparam integer CW=(WAIT_CYCLES<2)?1:$clog2(WAIT_CYCLES);
 reg [CW-1:0] count;
 always @(posedge clk or negedge rst_n) begin
  if(!rst_n)begin count<=0;camera_reset_n<=0;i2c_ready<=0;end
  else if(!camera_reset_n)begin
   if(count==HOLD_CYCLES-1)begin count<=0;camera_reset_n<=1;end
   else count<=count+1'b1;
  end else if(!i2c_ready)begin
   if(count==WAIT_CYCLES-1)begin count<=0;i2c_ready<=1;end
   else count<=count+1'b1;
  end
 end
endmodule
