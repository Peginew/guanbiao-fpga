// Read-only compact CORE32 in the original one-shot held96 protocol. No ROI/capture/permit control output.
// HCLK ARM delay triggers once; no CPU read can trigger or clear this mailbox.
module meter_mcu_roi_observer #(
 parameter ARM_DELAY_CYCLES=50000000
)(
 input wire s_clk,d_clk,arst_n,armed,
 input wire [31:0] s_word,
 output reg [31:0] d_seq,output reg [95:0] d_snapshot
);
 localparam TW=ARM_DELAY_CYCLES<=1?1:$clog2(ARM_DELAY_CYCLES);
 (* ASYNC_REG="TRUE" *)reg [1:0] s_reset,d_reset;
 always @(posedge s_clk or negedge arst_n)
  if(!arst_n)s_reset<=0;else s_reset<={s_reset[0],1'b1};
 always @(posedge d_clk or negedge arst_n)
  if(!arst_n)d_reset<=0;else d_reset<={d_reset[0],1'b1};
 wire srst=s_reset[1],drst=d_reset[1];
 reg d_request,d_ack,s_result;
 (* ASYNC_REG="TRUE" *)reg [1:0] request_sync,ack_sync,result_sync;
 reg request_seen,result_seen;
 reg [95:0] s_hold;
 localparam S_WAIT=0,S_SETTLE=1,S_ACK=2,S_ACK_SETTLE=3,S_DONE=4;
 reg [2:0] s_state;
 always @(posedge s_clk or negedge srst)begin
  if(!srst)begin
   request_sync<=0;ack_sync<=0;request_seen<=0;s_hold<=0;s_result<=0;s_state<=S_WAIT;
  end else begin
   request_sync<={request_sync[0],d_request};ack_sync<={ack_sync[0],d_ack};
   case(s_state)
    S_WAIT:if(request_sync[1]!=request_seen)s_state<=S_SETTLE;
    S_SETTLE:begin
     // Same held96 bundle and notification/settle/ACK protocol.
     // Upper64 are constant zero and synthesize away; no binary bit CDC.
     s_hold<={64'd0,s_word};
     request_seen<=request_sync[1];s_result<=~s_result;s_state<=S_ACK;
    end
    S_ACK:if(ack_sync[1]==s_result)s_state<=S_ACK_SETTLE;
    S_ACK_SETTLE:s_state<=S_DONE;
    S_DONE:begin end
    default:s_state<=S_DONE;
   endcase
  end
 end
 localparam D_ARM=0,D_DELAY=1,D_RESULT=2,D_SETTLE=3,D_DONE=4;
 reg [2:0] d_state;reg [TW-1:0] delay_count;
 always @(posedge d_clk or negedge drst)begin
  if(!drst)begin
   d_state<=D_ARM;delay_count<=0;d_request<=0;d_ack<=0;result_sync<=0;result_seen<=0;
   d_seq<=0;d_snapshot<=0;
  end else begin
   result_sync<={result_sync[0],s_result};
   case(d_state)
    D_ARM:if(armed)begin delay_count<=0;d_state<=D_DELAY;end
    D_DELAY:if(delay_count==ARM_DELAY_CYCLES-1)begin
     d_request<=~d_request;d_state<=D_RESULT;
    end else delay_count<=delay_count+1'b1;
    D_RESULT:if(result_sync[1]!=result_seen)d_state<=D_SETTLE;
    D_SETTLE:begin
     // One full HCLK after2sync result notification, whole held96 has settled.
     // Publish data+seq atomically and freeze even aftervideo cancel/reset.
     d_snapshot<=s_hold;d_seq<=32'd1;
     result_seen<=result_sync[1];d_ack<=result_sync[1];d_state<=D_DONE;
    end
    D_DONE:begin end
    default:d_state<=D_DONE;
   endcase
  end
 end
endmodule
