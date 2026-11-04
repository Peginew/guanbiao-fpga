// Explicit unit conversion ONLY. No needle-angle calibration or new READ gate.
// MCU supplies calibrated PSI_UQ8 for the SAME committed observation. Existing
// guard/LAST transport remains bar_U0.16; primary UI converts that todecimalpsi.
module t06_meter_psi_return_runtime(
 input wire clk,rst_n,start,cancel,calibration_valid,input_valid,
 input wire [15:0] psi_q8,
 output reg busy,done,value_valid,
 output reg [15:0] value_q16,value_bcd,output reg [4:0] reason
);
 reg [1:0] state;
 reg [15:0] binary_shift;
 reg [31:0] multiplicand,accumulator;
 reg [3:0] count;
 // round(0.0689475729167bar/psi *256 *65536) =1156748.
 // Input supported2.5..12psi => product fitsU32. This is a unitconversion,
 // not a claim that the original0..0.51barTEST angular calibration expanded.
 wire [31:0] sum_next=accumulator+(binary_shift[0]?multiplicand:32'd0);
 wire [31:0] rounded=sum_next+32'd32768;
 wire [22:0] product100=({7'd0,value_q16}<<6)+({7'd0,value_q16}<<5)+({7'd0,value_q16}<<2)+23'd32768;
 wire [6:0] hundredths=product100[22:16];
 wire [3:0] bcd_integer=hundredths/7'd100;
 wire [3:0] bcd_tens=(hundredths%7'd100)/7'd10;
 wire [3:0] bcd_ones=hundredths%7'd10;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=0;busy<=0;done<=0;value_valid<=0;value_q16<=0;value_bcd<=0;reason<=0;
   binary_shift<=0;multiplicand<=0;accumulator<=0;count<=0;
  end else begin
   done<=0;
   if(cancel||!calibration_valid)begin state<=0;busy<=0;value_valid<=0;value_q16<=0;value_bcd<=0;reason<=3;end
   else case(state)
    0:if(start)begin
     value_valid<=0;value_q16<=0;value_bcd<=0;
     if(!input_valid||psi_q8<640||psi_q8>3072)begin reason<=1;done<=1;end
     else begin state<=1;busy<=1;reason<=0;binary_shift<=psi_q8;count<=0;accumulator<=0;multiplicand<=32'd1156748;end
    end
    1:begin
     accumulator<=sum_next;binary_shift<={1'b0,binary_shift[15:1]};multiplicand<=multiplicand<<1;
     if(count==15)begin value_q16<=rounded[31:16];state<=2;end
     else count<=count+1'b1;
    end
    2:begin value_bcd<={4'd0,bcd_integer,bcd_tens,bcd_ones};value_valid<=1;done<=1;busy<=0;state<=0;end
    default:state<=0;
   endcase
  end
 end
endmodule
