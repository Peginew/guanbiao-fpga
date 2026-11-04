// Unsigned restoring divider; one request per frame, 32 clocks per quotient.
// Denominator zero returns all ones; the caller rejects untrusted summaries.
module t06_serial_divider(
 input clk,rst_n,start,
 input [31:0] numerator,
 input [23:0] denominator,
 output reg busy,done,
 output reg [31:0] quotient
);
 reg [31:0] work;
 reg [23:0] den;
 reg [24:0] rem;
 reg [5:0] left;
 wire [24:0] trial={rem[23:0],work[31]};
 wire fits=trial>={1'b0,den};
 always @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin busy<=0;done<=0;quotient<=0;work<=0;den<=0;rem<=0;left<=0;end
  else begin
   done<=0;
   if(start&&!busy) begin
    if(denominator==0) begin quotient<=32'hffffffff;done<=1;end
    else begin work<=numerator;den<=denominator;rem<=0;left<=32;busy<=1;end
   end else if(busy) begin
    rem<=fits?(trial-{1'b0,den}):trial;
    work<={work[30:0],fits};left<=left-1'b1;
    if(left==1) begin quotient<={work[30:0],fits};busy<=0;done<=1;end
   end
  end
 end
endmodule
