// Display-only conversion from unsigned Q0.16 bar to integer hundredths psi.
// 1 bar = 14.503774 psi. Do not change the existing TEST calibration domain.
// round(q16 * 95051933 / 2^32) agrees with exact decimal conversion at every
// one of the 65536 Q0.16 input codes (independently exhaustively checked).
// Serial Horner constant multiplication: 16 clocks; no multiplier or divider.
// Display validity/source/owner MUST travel separately with the accepted input.
module t06_ui_barq16_psi100 (
 input wire clk,rst_n,start,
 input wire [15:0] bar_q16,
 output reg busy,done,
 output reg [15:0] psi_hundredths
);
 reg [15:0] binary_shift;
 reg [42:0] accumulator;
 reg [3:0] count;
 wire [42:0] addend=binary_shift[15]?43'd95051933:43'd0;
 wire [42:0] step=(accumulator<<1)+addend;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin busy<=0;done<=0;psi_hundredths<=0;binary_shift<=0;accumulator<=0;count<=0;end
  else begin
   done<=0;
   if(!busy)begin
    if(start)begin busy<=1;binary_shift<=bar_q16;accumulator<=0;count<=0;end
   end else begin
    accumulator<=step;binary_shift<={binary_shift[14:0],1'b0};
    if(count==15)begin
     psi_hundredths<={5'd0,step[42:32]}+{15'd0,step[31]};
     busy<=0;done<=1;
    end else count<=count+1'b1;
   end
  end
 end
endmodule
