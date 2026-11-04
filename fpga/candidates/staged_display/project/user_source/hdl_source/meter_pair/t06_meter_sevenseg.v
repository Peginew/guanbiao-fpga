// Board S0..S7 order is physical left-to-right;S0 drives the high BCD nibble.
// Common-anode digit+segment outputs are both active low. CE only,no new clock.
// A logical1 decimal_mask[n] illuminates DP at physical digit Sn.
module t06_meter_sevenseg #(
 parameter integer SCAN_DIV=12500,
 // Zero disables automatic display expiry; explicit cancel/invalid packet still blanks immediately.
 parameter integer EXPIRE_CYCLES=30000000,
 // At100MHz/production scan:5us all-off,then1us segment setup.
 // Conservative design margin,not a measured transistor turnoff guarantee.
 // Small simulation dividers retain1+1cycle timing unless overridden.
 parameter integer BLANK_CYCLES=(SCAN_DIV>1000?500:1),
 parameter integer SETUP_CYCLES=(SCAN_DIV>1000?100:1)
)(
 input wire clk,input wire rst_n,input wire cancel,
 input wire value_update,input wire value_valid,
 input wire [31:0] value_bcd,input wire [7:0] decimal_mask,
 output wire [7:0] digit_select_n,output wire [7:0] segment_n,
 output reg showing_value,output reg bcd_fault
);
 reg [31:0] pending_bcd,active_bcd;
 reg [7:0] pending_decimal,active_decimal;
 reg pending_valid;
 reg [31:0] age;
 reg [15:0] divider;
 reg [2:0] digit;
 reg [1:0] phase;
 reg [7:0] sel_q,seg_q;
 wire bcd_legal =
  (value_bcd[3:0]<=9||value_bcd[3:0]==15)&&
  (value_bcd[7:4]<=9||value_bcd[7:4]==15)&&
  (value_bcd[11:8]<=9||value_bcd[11:8]==15)&&
  (value_bcd[15:12]<=9||value_bcd[15:12]==15)&&
  (value_bcd[19:16]<=9||value_bcd[19:16]==15)&&
  (value_bcd[23:20]<=9||value_bcd[23:20]==15)&&
  (value_bcd[27:24]<=9||value_bcd[27:24]==15)&&
  (value_bcd[31:28]<=9||value_bcd[31:28]==15);
 wire input_revoke=value_update&&(!value_valid||!bcd_legal);
 wire expired=(EXPIRE_CYCLES>0)&&(pending_valid||showing_value)&&(age>=EXPIRE_CYCLES-1)&&!value_update;
 wire immediate_revoke=cancel||input_revoke||expired;
 wire [3:0] nibble=active_bcd[31-digit*4 -:4];
 function [7:0] decode;
  input [3:0] n;
  begin case(n)
   0:decode=8'hc0;1:decode=8'hf9;2:decode=8'ha4;3:decode=8'hb0;
   4:decode=8'h99;5:decode=8'h92;6:decode=8'h82;7:decode=8'hf8;
   8:decode=8'h80;9:decode=8'h90;15:decode=8'hff;
   default:decode=8'hbf;
  endcase end
 endfunction
 // Immediate withdraw even if revoke arrives between scan slots.
 assign digit_select_n=(!rst_n||immediate_revoke)?8'hff:sel_q;
 assign segment_n=(!rst_n||immediate_revoke)?8'hff:seg_q;
 always @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin
   pending_bcd<=32'hffffffff;active_bcd<=32'hffffffff;
   pending_decimal<=0;active_decimal<=0;pending_valid<=0;
   showing_value<=0;bcd_fault<=0;age<=0;divider<=0;digit<=7;phase<=3;
   sel_q<=8'hff;seg_q<=8'hff;
  end else begin
   bcd_fault<=0;
   if(value_update&&value_valid&&bcd_legal) begin
    pending_bcd<=value_bcd;pending_decimal<=decimal_mask;
    pending_valid<=1;age<=0;
   end else if(pending_valid||showing_value) begin
    if(EXPIRE_CYCLES>0&&age<EXPIRE_CYCLES)age<=age+1'b1;
   end
   if(immediate_revoke) begin
    pending_valid<=0;showing_value<=0;active_decimal<=0;
    sel_q<=8'hff;seg_q<=8'hff;
    // Restart at an all-digit frame boundary;do not revive an old packet.
    divider<=0;digit<=7;phase<=3;
    if(value_update&&value_valid&&!bcd_legal)bcd_fault<=1;
   end else begin
    if(divider==SCAN_DIV-1) begin
     divider<=0;sel_q<=8'hff;seg_q<=8'hff;
     digit<=digit+1'b1;phase<=0;
     if(digit==7) begin
      // Complete bundle commits only before physical S0,not halfway through8digits.
      active_bcd<=pending_bcd;active_decimal<=pending_decimal;
      showing_value<=pending_valid;
     end
    end else begin
     divider<=divider+1'b1;
     case(phase)
      0:if(divider==BLANK_CYCLES-1)begin
       if(showing_value)begin
        seg_q<=decode(nibble)&((active_decimal[digit]&&nibble!=15)?8'h7f:8'hff);
       end else seg_q<=8'hbf; // '-' on every digit while invalid
       phase<=1;
      end
      1:if(divider==BLANK_CYCLES+SETUP_CYCLES-1)begin sel_q<=~(8'b1<<digit);phase<=3;end
      default:begin end
     endcase
    end
   end
  end
 end
endmodule
