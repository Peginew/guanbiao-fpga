// Runtime visual-indication map for explicitly confirmed raw128profiles only.
// Caller must keep all anchor fields stable forconfig and cancel on withdrawal.
// No extrapolation,full instrument range or physical pressure authority.
module t06_meter_scale_runtime(
 input wire clk,rst_n,start,cancel,calibration_valid,
 input wire [8:0] angle,cal_angle0,cal_angle1,cal_angle2,cal_angle3,
 input wire [15:0] cal_value0,cal_value1,cal_value2,cal_value3,
 output reg busy,done,value_valid,output reg [15:0] value_q16,value_bcd,
 output reg [4:0] reason
);
 reg [1:0] state;reg [8:0] delta_angle;reg [6:0] denominator,remainder;
 reg [15:0] base,delta_value;reg [22:0] dividend,quotient;reg [4:0] bit_index;
 wire anchors_ok=cal_angle0<cal_angle1&&cal_angle1<cal_angle2&&cal_angle2<cal_angle3&&cal_angle3<=359&&
  cal_angle1-cal_angle0<=127&&cal_angle2-cal_angle1<=127&&cal_angle3-cal_angle2<=127&&
  cal_value0<=cal_value1&&cal_value1<=cal_value2&&cal_value2<=cal_value3&&cal_value3<=16'd33423;
 wire [7:0] trial={remainder,dividend[22]};
 wire subtract=trial>={1'b0,denominator};wire [22:0] next_quotient={quotient[21:0],subtract};
 wire [22:0] product100=({7'd0,value_q16}<<6)+({7'd0,value_q16}<<5)+({7'd0,value_q16}<<2)+23'd32768;
 wire [6:0] hundredths=product100[22:16];
 wire [3:0] bcd_integer=hundredths/7'd100;
 wire [3:0] bcd_tens=(hundredths%7'd100)/7'd10;
 wire [3:0] bcd_ones=hundredths%7'd10;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin state<=0;busy<=0;done<=0;value_valid<=0;value_q16<=0;value_bcd<=0;reason<=0;
   delta_angle<=0;denominator<=1;remainder<=0;base<=0;delta_value<=0;dividend<=0;quotient<=0;bit_index<=0;end
  else begin
   done<=0;
   if(cancel||!calibration_valid)begin state<=0;busy<=0;value_valid<=0;value_q16<=0;value_bcd<=0;reason<=3;end
   else case(state)
    0:if(start)begin
     value_valid<=0;value_q16<=0;value_bcd<=0;
     if(!anchors_ok||angle<cal_angle0||angle>cal_angle3)begin reason<=1;done<=1;end
     else begin busy<=1;state<=1;reason<=0;
      if(angle<=cal_angle1)begin base<=cal_value0;delta_value<=cal_value1-cal_value0;delta_angle<=angle-cal_angle0;denominator<=cal_angle1-cal_angle0;end
      else if(angle<=cal_angle2)begin base<=cal_value1;delta_value<=cal_value2-cal_value1;delta_angle<=angle-cal_angle1;denominator<=cal_angle2-cal_angle1;end
      else begin base<=cal_value2;delta_value<=cal_value3-cal_value2;delta_angle<=angle-cal_angle2;denominator<=cal_angle3-cal_angle2;end
     end
    end
    1:begin dividend<=delta_angle*delta_value+(denominator>>1);quotient<=0;remainder<=0;bit_index<=0;state<=2;end
    2:begin
     dividend<={dividend[21:0],1'b0};quotient<=next_quotient;remainder<=subtract?trial-denominator:trial;
     if(bit_index==22)begin value_q16<=base+next_quotient;state<=3;end else bit_index<=bit_index+1'b1;
    end
    3:begin
     value_bcd<={4'd0,bcd_integer,bcd_tens,bcd_ones};
     value_valid<=1;done<=1;busy<=0;state<=0;
    end
   endcase
  end
 end
endmodule
