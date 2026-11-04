// IPUG034 v1.0 PDF8: sys_rst_n resets PLL and all memory-controller logic.
// Run from live 100 MHz reference: DDR user clock may stop during reset.
// All video clients, command FIFO, bank ownership and telemetry share
// session_allowed through their reset trees.
module t06_ddr_recovery #(
 parameter HOLD_CYCLES=1024,         // must be >= 8 reference clocks
 parameter CALIB_STABLE_CYCLES=16   // must be >= 2 reference clocks
)(
 input wire clk,rst_n,calibrated,recover_request,
 output wire core_rst_n, output wire session_allowed,
 output reg fault_seen
);
 localparam W=(HOLD_CYCLES<2)?1:$clog2(HOLD_CYCLES);
 localparam Q=(CALIB_STABLE_CYCLES<2)?1:$clog2(CALIB_STABLE_CYCLES);
 localparam HOLD_RESET=2'd0,WAIT_CALIB=2'd1,RUN=2'd2;
 (* ASYNC_REG="TRUE" *) reg [1:0] calib_sync;
 (* ASYNC_REG="TRUE" *) reg [1:0] request_sync;
 reg [1:0] state;
 reg [W-1:0] count;
 reg [Q-1:0] stable_count;
 reg saw_calib_low;
 reg calibration_still_valid;
 // Remember even a short calibration-low pulse. A raw asynchronous client
 // reset alone would lose the transaction ledger without resetting the MC.
 // Once RUN has seen a loss, this flag cannot re-arm until RUN is abandoned.
 always @(posedge clk or negedge rst_n or negedge calibrated)begin
  if(!rst_n || !calibrated)calibration_still_valid<=0;
  else if(state!=RUN)calibration_still_valid<=1;
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin calib_sync<=0;request_sync<=0;end
  else begin
   calib_sync<={calib_sync[0],calibrated};
   request_sync<={request_sync[0],recover_request};
  end
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=HOLD_RESET;count<=HOLD_CYCLES-1;stable_count<=0;
   saw_calib_low<=0;fault_seen<=0;
  end else case(state)
   HOLD_RESET:begin
    stable_count<=0;
    if(count!=0)count<=count-1'b1;
    // Ignore synchronizer reset zeros: wait four reference cycles before
    // accepting evidence that the physical controller's calibration is low.
    if(count<=HOLD_CYCLES-5 && !calib_sync[1])saw_calib_low<=1;
    if(count==0 && saw_calib_low)state<=WAIT_CALIB;
   end
   WAIT_CALIB:begin
    // The asynchronous session reset acknowledges a held request even when
    // the DDR user clock stops; observe it low before reopening traffic.
    if(!calib_sync[1] || !calibration_still_valid || request_sync[1])stable_count<=0;
    else if(stable_count==CALIB_STABLE_CYCLES-1)begin
     state<=RUN;stable_count<=0;
    end else stable_count<=stable_count+1'b1;
   end
   RUN:begin
    if(request_sync[1] || !calib_sync[1] || !calibration_still_valid)begin
     state<=HOLD_RESET;count<=HOLD_CYCLES-1;stable_count<=0;
     saw_calib_low<=0;fault_seen<=1;
    end
   end
   default:begin
    state<=HOLD_RESET;count<=HOLD_CYCLES-1;stable_count<=0;
    saw_calib_low<=0;fault_seen<=1;
   end
  endcase
 end
 assign core_rst_n=rst_n && state!=HOLD_RESET;
 // A held calibration loss asserts client reset immediately and always causes
 // full MC reset. Release waits for fresh stable calibration and local pipes.
 assign session_allowed=rst_n && state==RUN && calibration_still_valid &&
                        calib_sync[1] && !request_sync[1];
endmodule
