// The vendor byte-aligner error is not CSI payload CRC/ECC verification.
// RAW errors can lead the packed SOF. Quarantine both neighboring packed
// frame intervals rather than assigning an uncertain event to one frame.
module t06_rx_fault_guard(
 input wire clk,rst_n,packed_sof,lane_error,
 output wire frame_error,output reg error_seen,
 output reg [15:0] error_events
);
 reg [1:0] quarantine;
 reg error_prev;
 always @(posedge clk or negedge rst_n) begin
  if(!rst_n)begin quarantine<=0;error_seen<=0;error_events<=0;error_prev<=0;end
  else begin
   error_prev<=lane_error;
   if(lane_error)begin
    quarantine<=2;error_seen<=1;
    if(!error_prev)error_events<=error_events+1'b1;
   end else if(packed_sof && quarantine!=0)quarantine<=quarantine-1'b1;
  end
 end
 assign frame_error=lane_error || quarantine!=0;
endmodule
