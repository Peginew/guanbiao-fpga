// Exact shared S32*M31 RNE-even requant; selected S8 orS16 symmetric clamp.
// Derived from the independently checked prior7-clock S8 RNE, not a shift-only approximation.
module strip_requant(input wire clk,rst_n,cancel,in_valid,output wire in_ready,
 input wire signed[31:0]in_acc,input wire[31:0]in_multiplier,input wire[5:0]in_shift,input wire in_wide,
 output wire out_valid,input wire out_ready,output reg signed[15:0]out_q,output wire[3:0]out_error);
 reg[2:0]state;reg[63:0]work;reg[5:0]shift;reg negative,bad,wide;
 reg[15:0]quotient;reg too_wide,increment;
 (* dsp_style="yes" *)wire signed[63:0]product=$signed(in_acc)*$signed({1'b0,in_multiplier[30:0]});
 wire[63:0]j1=shift[0]?{1'b0,work[63:2],(|work[1:0])}:work;
 wire[63:0]j2=shift[1]?{2'b0,j1[63:3],(|j1[2:0])}:j1;
 wire[63:0]j4=shift[0]?{4'b0,work[63:5],(|work[4:0])}:work;
 wire[63:0]j8=shift[1]?{8'b0,j4[63:9],(|j4[8:0])}:j4;
 wire[63:0]j16=shift[0]?{16'b0,work[63:17],(|work[16:0])}:work;
 wire[63:0]j32=shift[1]?{32'b0,j16[63:33],(|j16[32:0])}:j16;
 wire[16:0]rounded={1'b0,quotient}+increment;
 wire[16:0]limit=wide?17'd32767:17'd127;
 wire[15:0]magnitude=too_wide||rounded>limit?limit[15:0]:rounded[15:0];
 assign in_ready=rst_n&&!cancel&&state==0;assign out_valid=rst_n&&!cancel&&state==7;assign out_error=bad?1:0;
 always@(posedge clk or negedge rst_n)begin
  if(!rst_n)begin state<=0;work<=0;shift<=0;negative<=0;bad<=0;wide<=0;quotient<=0;too_wide<=0;increment<=0;out_q<=0;end
  else if(cancel)begin state<=0;bad<=0;out_q<=0;end
  else case(state)
   0:if(in_valid)begin work<=in_multiplier[31]?0:product;shift<=in_shift;wide<=in_wide;bad<=in_multiplier[31];state<=1;end
   1:begin negative<=work[63];work<=work[63]?{(~work[61:0]+62'd1),2'b00}:{work[61:0],2'b00};state<=2;end
   2:begin work<=j2;shift<=shift>>2;state<=3;end
   3:begin work<=j8;shift<=shift>>2;state<=4;end
   4:begin work<=j32;state<=5;end
   5:begin quotient<=work[17:2];too_wide<=|work[63:18];increment<=work[1]&&(work[0]||work[2]);state<=6;end
   6:begin out_q<=bad?0:negative?-$signed(magnitude):$signed(magnitude);state<=7;end
   7:if(out_ready)state<=0;
   default:state<=0;
  endcase
 end
endmodule
