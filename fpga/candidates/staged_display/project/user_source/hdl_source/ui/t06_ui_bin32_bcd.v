// Shared display formatter. One accepted request, 32 update clocks, then done.
// Decimal BCD is least-significant digit first: digit 0 occupies bits [3:0].
// Ten digits cover the entire unsigned 32-bit range, including 4294967295.
// Start while busy is intentionally ignored; no input must remain stable.
module t06_ui_bin32_bcd (
 input wire clk,rst_n,start,
 input wire [31:0] value,
 output reg busy,done,
 output reg [39:0] bcd
);
 reg [31:0] binary_shift;
 reg [39:0] decimal_shift;
 reg [5:0] count;
 reg [39:0] corrected;
 integer i;
 wire [39:0] shifted={corrected[38:0],binary_shift[31]};
 always @* begin
  corrected=decimal_shift;
  for(i=0;i<10;i=i+1)
   if(decimal_shift[4*i +:4]>=4'd5)
    corrected[4*i +:4]=decimal_shift[4*i +:4]+4'd3;
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   busy<=0;done<=0;bcd<=0;binary_shift<=0;decimal_shift<=0;count<=0;
  end else begin
   done<=0;
   if(!busy)begin
    if(start)begin busy<=1;binary_shift<=value;decimal_shift<=0;count<=0;end
   end else begin
    binary_shift<={binary_shift[30:0],1'b0};
    decimal_shift<=shifted;
    if(count==31)begin bcd<=shifted;busy<=0;done<=1;end
    else count<=count+1'b1;
   end
  end
 end
endmodule
