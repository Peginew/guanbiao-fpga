module video_out #(
 parameter FRAME_WORDS=172800,
 // 2^24 cycles = about 125.8 ms at the configured 133.333 MHz DDR user clock.
 // This is a no-response-progress bound, not a frame-length acceptance rule.
 parameter READ_TIMEOUT_CYCLES=16777216
)(
 input wire I_rst_n,I_ddr_clk,
 output wire O_video_out_rd_busy,
 input wire I_video_in_wr_busy,
 input wire [1:0] I_video_out_rp,
 output wire O_ddr_user_rd_en,
 output reg [24:0] O_ddr_user_addr,
 input wire I_ddr_user_ready,I_ddr_user_rd_valid,
 input wire [127:0] I_ddr_user_rd_data,
 input wire I_dsi_clk,I_video_vsync,I_video_rd_en,
 output reg [23:0] O_vdieo_data,
 input wire I_frame_valid,
 output wire O_frame_acquire,
 output reg [2:0] O_read_error,
 output reg O_monitor_pixel_good,O_monitor_frame_bad,
 output reg O_recovery_request
);
 localparam CW=$clog2(FRAME_WORDS+1);
 reg [1:0] d_reset,p_reset;
 always @(posedge I_ddr_clk or negedge I_rst_n)
  if(!I_rst_n)d_reset<=0;else d_reset<={d_reset[0],1'b1};
 always @(posedge I_dsi_clk or negedge I_rst_n)
  if(!I_rst_n)p_reset<=0;else p_reset<={p_reset[0],1'b1};
 (* ASYNC_REG="TRUE" *) reg [2:0] vs_sync;
 always @(posedge I_ddr_clk or negedge I_rst_n)
  if(!I_rst_n)vs_sync<=0;else vs_sync<={vs_sync[1:0],I_video_vsync};
 wire S_video_frame_start=vs_sync[1] && !vs_sync[2];
 reg S_fifo_rst,S_ddr_rd_valid,frame_live;
 reg [2:0] state;
 reg [4:0] guard_count;
 reg [9:0] outstanding;
 localparam TW=(READ_TIMEOUT_CYCLES<2)?1:$clog2(READ_TIMEOUT_CYCLES);
 reg [TW-1:0] no_return_count;
 reg [CW-1:0] issued;
 reg [7:0] burst_count;
 wire [8:0] S_fifo_wr_num;
 wire fifo_full,S_fifo_emtpy;
 wire [127:0] S_fifo_rd_data;
 wire [10:0] reserved_words={2'b00,S_fifo_wr_num}+{1'b0,outstanding};
 wire S_ddr_rd_trig=state==0 && frame_live && !S_video_frame_start && !O_recovery_request &&
   !S_ddr_rd_valid && !I_video_in_wr_busy && reserved_words<=270 && issued<FRAME_WORDS && d_reset[1];
 assign O_ddr_user_rd_en=S_ddr_rd_valid && I_ddr_user_ready && state==0 && !S_video_frame_start && !O_recovery_request;
 assign O_video_out_rd_busy=S_ddr_rd_trig | S_ddr_rd_valid;
 assign O_frame_acquire=state==3 && guard_count==0 && !S_video_frame_start;
 function [24:0] base(input [1:0] b);
  case(b)0:base=25'd0;1:base=25'd7000000;2:base=25'd14000000;3:base=25'd21000000;endcase
 endfunction
 // Hold the request until the shared DDR session reset acknowledges it.
 // Never clear outstanding on timeout or at a video boundary. Late responses
 // still discharge it while the reference-domain controller resets the whole
 // physical MC, command FIFO, clients and bank-ownership session.
 always @(posedge I_ddr_clk or negedge I_rst_n)begin
  if(!I_rst_n)begin no_return_count<=0;O_recovery_request<=0;end
  else if(d_reset[1] && !O_recovery_request)begin
   if(I_ddr_user_rd_valid && outstanding==0 && !O_ddr_user_rd_en)
    O_recovery_request<=1;
   if(outstanding==0 || I_ddr_user_rd_valid)no_return_count<=0;
   else if(no_return_count==READ_TIMEOUT_CYCLES-1)O_recovery_request<=1;
   else no_return_count<=no_return_count+1'b1;
  end
 end
 always @(posedge I_ddr_clk or negedge I_rst_n)begin
  if(!I_rst_n)begin
   S_fifo_rst<=1;S_ddr_rd_valid<=0;frame_live<=0;state<=1;guard_count<=0;
   outstanding<=0;issued<=0;burst_count<=0;O_ddr_user_addr<=0;O_read_error[2:1]<=0;
  end else if(d_reset[1])begin
   case({O_ddr_user_rd_en,I_ddr_user_rd_valid})
    2'b10:outstanding<=outstanding+1'b1;
    2'b01:if(outstanding!=0)outstanding<=outstanding-1'b1;else O_read_error[2]<=1;
    default:outstanding<=outstanding;
   endcase
   if(I_ddr_user_rd_valid && !S_fifo_rst && fifo_full)O_read_error[1]<=1;
   if(O_recovery_request)begin
    state<=1;frame_live<=0;S_fifo_rst<=1;S_ddr_rd_valid<=0;burst_count<=0;
   end else if(S_video_frame_start)begin
    state<=1;frame_live<=0;S_fifo_rst<=1;S_ddr_rd_valid<=0;burst_count<=0;
   end else case(state)
    1:if(outstanding==0 && !I_ddr_user_rd_valid)begin state<=2;guard_count<=16;end
    2:if(guard_count==0)begin S_fifo_rst<=0;state<=3;guard_count<=4;end
      else guard_count<=guard_count-1'b1;
    3:if(guard_count==0)begin
       state<=0;frame_live<=I_frame_valid;O_ddr_user_addr<=base(I_video_out_rp);issued<=0;
      end else guard_count<=guard_count-1'b1;
    0:begin
     if(O_ddr_user_rd_en)begin
      issued<=issued+1'b1;O_ddr_user_addr<=O_ddr_user_addr+25'd8;
      if(burst_count==239)begin S_ddr_rd_valid<=0;burst_count<=0;end
      else burst_count<=burst_count+1'b1;
     end else if(S_ddr_rd_trig)begin S_ddr_rd_valid<=1;burst_count<=0;end
    end
    default:state<=1;
   endcase
  end
 end
 reg [3:0] S_fifo_rd_cnt,S_fifo_rd_cnt_1d;
 reg S_video_rd_en_1d,vs_prev,frame_bad;
 reg [127:0] S_fifo_rd_data_1d;
 (* ASYNC_REG="TRUE" *) reg [1:0] live_sync;
 wire wants_word=I_video_rd_en && (S_fifo_rd_cnt==0 || S_fifo_rd_cnt==5 || S_fifo_rd_cnt==10);
 (* ASYNC_REG="TRUE" *) reg [2:0] fifo_read_release;
 wire fifo_async_reset=S_fifo_rst | !I_rst_n;
 always @(posedge I_dsi_clk or posedge fifo_async_reset)
  if(fifo_async_reset)fifo_read_release<=0;
  else fifo_read_release<={fifo_read_release[1:0],1'b1};
 wire S_fifo_rd_en=fifo_read_release[2] && wants_word && !frame_bad && live_sync[1] && !S_fifo_emtpy && p_reset[1];
 w128_d512_fifo U_w128_d512_fifo(
  .rst(S_fifo_rst | !I_rst_n),.clkw(I_ddr_clk),
  .we(I_ddr_user_rd_valid && !S_fifo_rst && frame_live && state==0 && !fifo_full),
  .di(I_ddr_user_rd_data),.wrusedw(S_fifo_wr_num),.afull(),.full_flag(fifo_full),
  .clkr(I_dsi_clk),.re(S_fifo_rd_en),.dout(S_fifo_rd_data),.rdusedw(),.valid(),
  .empty_flag(S_fifo_emtpy),.aempty());
 always @(posedge I_dsi_clk or negedge p_reset[1])begin
  if(!p_reset[1])begin
   S_fifo_rd_cnt<=0;S_fifo_rd_cnt_1d<=0;S_video_rd_en_1d<=0;S_fifo_rd_data_1d<=0;
   live_sync<=0;vs_prev<=0;frame_bad<=1;O_read_error[0]<=0;
  end else begin
   live_sync<={live_sync[0],frame_live};vs_prev<=I_video_vsync;
   S_fifo_rd_cnt<=I_video_rd_en ? S_fifo_rd_cnt+1'b1 : 4'd0;
   S_fifo_rd_cnt_1d<=S_fifo_rd_cnt;S_video_rd_en_1d<=I_video_rd_en;S_fifo_rd_data_1d<=S_fifo_rd_data;
   if(I_video_vsync && !vs_prev)frame_bad<=0;
   else if(I_video_rd_en && (!live_sync[1] || (wants_word && (S_fifo_emtpy || !fifo_read_release[2]))))begin
    frame_bad<=1;
    if(live_sync[1])O_read_error[0]<=1;
   end
  end
 end
 // Keep the baseline 128-bit to 24-bit ordering and one pixel-clock latency.
 // After starvation, blank the remainder of this frame; do not shift late data.
 always @(posedge I_dsi_clk or negedge p_reset[1])begin
  if(!p_reset[1])O_vdieo_data<=0;
  else if(S_video_rd_en_1d && !frame_bad && live_sync[1])begin
   case(S_fifo_rd_cnt_1d)
    0:O_vdieo_data<=S_fifo_rd_data[127:104];
    1:O_vdieo_data<=S_fifo_rd_data[103:80];
    2:O_vdieo_data<=S_fifo_rd_data[79:56];
    3:O_vdieo_data<=S_fifo_rd_data[55:32];
    4:O_vdieo_data<=S_fifo_rd_data[31:8];
    5:O_vdieo_data<={S_fifo_rd_data_1d[7:0],S_fifo_rd_data[127:112]};
    6:O_vdieo_data<=S_fifo_rd_data[111:88];
    7:O_vdieo_data<=S_fifo_rd_data[87:64];
    8:O_vdieo_data<=S_fifo_rd_data[63:40];
    9:O_vdieo_data<=S_fifo_rd_data[39:16];
    10:O_vdieo_data<={S_fifo_rd_data_1d[15:0],S_fifo_rd_data[127:120]};
    11:O_vdieo_data<=S_fifo_rd_data[119:96];
    12:O_vdieo_data<=S_fifo_rd_data[95:72];
    13:O_vdieo_data<=S_fifo_rd_data[71:48];
    14:O_vdieo_data<=S_fifo_rd_data[47:24];
    15:O_vdieo_data<=S_fifo_rd_data[23:0];
   endcase
  end else O_vdieo_data<=0;
 end

 // Read-only observation aliases: exactly the old output RGB gate and edge.
 // These registers do not feed any old data/control/reset/DDR signal.
 always @(posedge I_dsi_clk or negedge p_reset[1]) begin
  if(!p_reset[1])begin O_monitor_pixel_good<=0;O_monitor_frame_bad<=1;end
  else begin
   O_monitor_pixel_good<=S_video_rd_en_1d && !frame_bad && live_sync[1];
   O_monitor_frame_bad<=frame_bad;
  end
 end
endmodule
