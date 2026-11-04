`timescale 1ns/1ps
module rover_source_fence(
 input wire core_clk,core_rst_n,csi_clk,csi_rst_n,
 input wire request,input wire [31:0] csi_source,input wire csi_source_valid,
 output wire idle,output reg ready,output reg [31:0] source_floor
);
 reg request_toggle,busy,settle;
 (* ASYNC_REG="TRUE" *) reg req_meta,req_sync;
 (* ASYNC_REG="TRUE" *) reg ack_meta,ack_sync;
 reg ack_toggle,latest_valid;reg [31:0] latest_source,held_source;
 assign idle=!busy;
 always @(posedge csi_clk or negedge csi_rst_n)begin
  if(!csi_rst_n)begin req_meta<=0;req_sync<=0;ack_toggle<=0;latest_valid<=0;latest_source<=0;held_source<=0;end
  else begin
   req_meta<=request_toggle;req_sync<=req_meta;
   if(csi_source_valid)begin latest_source<=csi_source;latest_valid<=1;end
   if(req_sync!=ack_toggle&&(latest_valid||csi_source_valid))begin
    held_source<=csi_source_valid?csi_source:latest_source;ack_toggle<=req_sync;
   end
  end
 end
 always @(posedge core_clk or negedge core_rst_n)begin
  if(!core_rst_n)begin request_toggle<=0;busy<=0;settle<=0;ack_meta<=0;ack_sync<=0;ready<=0;source_floor<=0;end
  else begin
   ack_meta<=ack_toggle;ack_sync<=ack_meta;ready<=0;
   if(request&&!busy)begin request_toggle<=!request_toggle;busy<=1;settle<=0;end
   if(busy)begin
    if(!settle&&ack_sync==request_toggle)settle<=1;
    else if(settle)begin source_floor<=held_source;ready<=1;busy<=0;settle<=0;end
   end
  end
 end
endmodule
