// Bounded local pixel support measurements for an owned128gray ROI.
// No claim of calibrated optical focus,distance,identity or physical stop.
module meter_mcu_quality_crc128(
 input wire clk,rst_n,start,cancel,
 output wire rd_en,output wire [13:0] rd_addr,input wire [7:0] rd_data,
 output reg busy,done,quality_ok,
 output reg [7:0] mean_gray,output reg [13:0] dark_count,bright_count,
 output reg [21:0] gradient_sum,output reg [4:0] reason,
 output reg [31:0] source_crc32,output reg scan_complete
);
 reg [31:0] crc_state;
 function [31:0] crc_byte; input [31:0] c; input [7:0] b; reg [31:0] t; integer i;
 begin t=c^{24'd0,b}; for(i=0;i<8;i=i+1)t=t[0]?(t>>1)^32'hedb88320:t>>1; crc_byte=t; end endfunction
 reg [1:0] state;reg [13:0] address;
 reg [21:0] gray_sum;reg [7:0] previous;reg [7:0] gradient;
 wire in_window=address[6:0]>=8&&address[6:0]<120&&address[13:7]>=8&&address[13:7]<120;
 wire [7:0] adiff=rd_data>=previous?rd_data-previous:previous-rd_data;
 assign rd_en=rst_n&&busy&&state==1;
 assign rd_addr=address;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin crc_state<=32'hffffffff;source_crc32<=0;scan_complete<=0;state<=0;address<=0;gray_sum<=0;previous<=0;gradient<=0;busy<=0;done<=0;quality_ok<=0;mean_gray<=0;dark_count<=0;bright_count<=0;gradient_sum<=0;reason<=0;end
  else begin
   done<=0;
   if(cancel)begin scan_complete<=0;state<=0;busy<=0;quality_ok<=0;reason<=3;end
   else case(state)
    0:if(start)begin crc_state<=32'hffffffff;source_crc32<=0;scan_complete<=0;address<=0;gray_sum<=0;previous<=0;dark_count<=0;bright_count<=0;gradient_sum<=0;busy<=1;quality_ok<=0;reason<=0;state<=1;end
    1:state<=2;
    2:state<=3;
    3:begin
     crc_state<=crc_byte(crc_state,rd_data);
     previous<=rd_data;
     if(in_window)begin
      gray_sum<=gray_sum+rd_data;
      if(rd_data<16)dark_count<=dark_count+1'b1;
      if(rd_data>239)bright_count<=bright_count+1'b1;
      if(address[6:0]>8)gradient_sum<=gradient_sum+adiff;
     end
     if(address==16383)begin
      source_crc32<=~crc_byte(crc_state,rd_data);scan_complete<=1;
      mean_gray<=gray_sum/12544;
      quality_ok<=gray_sum>=401408&&gray_sum<=2809856&&bright_count<=784&&dark_count<=4181&&gradient_sum>=49728;
      reason<=gray_sum<401408?1:gray_sum>2809856||bright_count>784?2:dark_count>4181||gradient_sum<49728?4:0;
      busy<=0;done<=1;state<=0;
     end else begin address<=address+1'b1;state<=1;end
    end
   endcase
  end
 end
endmodule
