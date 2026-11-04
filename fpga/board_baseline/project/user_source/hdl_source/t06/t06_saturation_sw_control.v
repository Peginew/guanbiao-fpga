// Two physicalDIPbits, wholebus qualification, no newclock/pinmapping here.
// 00/01/10/11 => 0.5x/1.0x/1.5x/2.0x in the displayfilter.
// Firstsynchronizerstage is the ONLY asynchronous-input endpoint. Bothbits
// must have the same observedcode for DEBOUNCE_CYCLES before level changes.
// The consumer must latch level only at its acceptedSOF.
module t06_saturation_sw_control #(
 parameter integer DEBOUNCE_CYCLES=2070000 // ~20ms @ CSI103.52MHz
)(input clk,rst_n,input [1:0] sw_async,output reg [1:0] level);
 localparam CW=(DEBOUNCE_CYCLES<=1)?1:$clog2(DEBOUNCE_CYCLES);
 (* ASYNC_REG="TRUE" *) reg [1:0] sync0,sync1;
 reg [1:0] candidate;
 reg [CW-1:0] count;
 always@(posedge clk or negedge rst_n)begin
  if(!rst_n)begin sync0<=2'd2;sync1<=2'd2;end
  else begin sync0<=sw_async;sync1<=sync0;end
 end
 always@(posedge clk or negedge rst_n)begin
  if(!rst_n)begin candidate<=2'd2;count<=0;level<=2'd2;end
  else if(sync1!=candidate)begin
   candidate<=sync1;
   if(DEBOUNCE_CYCLES<=1)begin level<=sync1;count<=0;end
   else count<=1; // the first observation already belongs to the stable run
  end else if(candidate!=level)begin
   if(DEBOUNCE_CYCLES<=1 || count==DEBOUNCE_CYCLES-1)begin
    level<=candidate;count<=0;
   end else count<=count+1'b1;
  end else count<=0;
 end
endmodule
