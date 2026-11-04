`timescale 1ns/1ps
// 3.3V UART 8N1. Only the first RX synchronizer stage is an asynchronous endpoint.
module rover_uart_phy #(parameter integer CLK_HZ=75000000, BAUD=115200)(
 input wire clk,rst_n,rx,output wire tx,
 input wire [7:0] tx_data,input wire tx_valid,output wire tx_ready,
 output reg [7:0] rx_data,output reg rx_valid,rx_error
);
 localparam integer DIV=(CLK_HZ+BAUD/2)/BAUD;
 localparam integer CW=$clog2(DIV+1);
 (* ASYNC_REG="TRUE" *) reg rx_meta;
 (* ASYNC_REG="TRUE" *) reg rx_sync;
 always @(posedge clk or negedge rst_n)
  if(!rst_n)begin rx_meta<=1;rx_sync<=1;end
  else begin rx_meta<=rx;rx_sync<=rx_meta;end
 reg [CW-1:0] tx_count;reg [9:0] tx_bits;reg [3:0] tx_index;reg tx_busy;
 assign tx_ready=!tx_busy;assign tx=tx_busy?tx_bits[tx_index]:1'b1;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin tx_count<=0;tx_bits<=10'h3ff;tx_index<=0;tx_busy<=0;end
  else if(!tx_busy)begin
   if(tx_valid)begin tx_bits<={1'b1,tx_data,1'b0};tx_index<=0;tx_count<=DIV-1;tx_busy<=1;end
  end else if(tx_count!=0)tx_count<=tx_count-1'b1;
  else if(tx_index==9)tx_busy<=0;
  else begin tx_index<=tx_index+1'b1;tx_count<=DIV-1;end
 end
 reg [2:0] rx_state;reg [CW-1:0] rx_count;reg [2:0] rx_index;reg [7:0] rx_bits;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin rx_state<=0;rx_count<=0;rx_index<=0;rx_bits<=0;rx_data<=0;rx_valid<=0;rx_error<=0;end
  else begin
   rx_valid<=0;rx_error<=0;
   case(rx_state)
    0:if(!rx_sync)begin rx_state<=1;rx_count<=DIV/2-1;end
    1:if(rx_count!=0)rx_count<=rx_count-1'b1;
      else if(rx_sync)rx_state<=0;
      else begin rx_state<=2;rx_count<=DIV-1;rx_index<=0;end
    2:if(rx_count!=0)rx_count<=rx_count-1'b1;
      else begin rx_bits[rx_index]<=rx_sync;rx_count<=DIV-1;
       if(rx_index==7)rx_state<=3;else rx_index<=rx_index+1'b1;end
    3:if(rx_count!=0)rx_count<=rx_count-1'b1;
      else if(rx_sync)begin rx_state<=0;rx_data<=rx_bits;rx_valid<=1;end
      else begin rx_state<=4;rx_error<=1;end
    4:if(rx_sync)rx_state<=0; // a break/bad stop cannot become a false new start
    default:rx_state<=0;
   endcase
  end
 end
endmodule
