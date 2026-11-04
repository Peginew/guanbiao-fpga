module video_in #(
 parameter FRAME_WORDS=172800
)(
 input wire I_rst_n,
 input wire I_camera_clk,I_camera_frame_start,I_camera_valid,
 input wire [127:0] I_camera_data,
 input wire I_mipi_rx_error,I_ddr_clk,I_display_pause,I_video_out_rd_busy,
 output wire O_video_in_wr_busy,
 output wire [1:0] O_video_out_rp,
 output reg O_ddr_user_wr_en,
 output reg [24:0] O_ddr_user_addr,
 output wire [127:0] O_ddr_user_wr_data,
 input wire I_ddr_user_ready,
 input wire [1:0] I_write_bank,
 output wire O_frame_boundary,O_frame_good,
 output reg [2:0] O_capture_error
);
 localparam CW=$clog2(FRAME_WORDS+2);
 reg [1:0] c_reset,d_reset;
 always @(posedge I_camera_clk or negedge I_rst_n)
  if(!I_rst_n)c_reset<=0;else c_reset<={c_reset[0],1'b1};
 always @(posedge I_ddr_clk or negedge I_rst_n)
  if(!I_rst_n)d_reset<=0;else d_reset<={d_reset[0],1'b1};
 wire crst=c_reset[1],drst=d_reset[1];
 reg S_camera_frame_start_extend;
 reg [3:0] extend_count;
 // The boundary event has one more settling stage than its stable metadata.
 // This tolerates a one-DDR-cycle difference in synchronizer observation.
 (* ASYNC_REG="TRUE" *) reg [3:0] fs_sync;
 (* ASYNC_REG="TRUE" *) reg [1:0] good_sync;
 reg [CW-1:0] camera_words,write_words;
 reg camera_bad,previous_good,camera_seen;
 wire fifo_full,fifo_empty;
 wire [8:0] S_fifo_rd_num;
 reg [4:0] setup_count;
 reg S_ddr_wr_valid;
 reg [7:0] burst_count;
 wire S_frame_start=fs_sync[2] & !fs_sync[3];
 wire S_fifo_rst=!I_rst_n | !drst | fs_sync[3];
 wire S_fifo_rd_en=S_ddr_wr_valid && I_ddr_user_ready && !fifo_empty &&
                      !S_fifo_rst && !S_frame_start;
 assign O_frame_boundary=S_frame_start;
 // A user write already in the one-cycle output stage is accepted this edge.
 // The downstream command FIFO preserves write-before-read ordering.
 assign O_frame_good=good_sync[1] &&
   (write_words==FRAME_WORDS || (write_words==FRAME_WORDS-1 && O_ddr_user_wr_en));
 assign O_video_in_wr_busy=S_ddr_wr_valid | O_ddr_user_wr_en | (setup_count!=0);
 assign O_video_out_rp=I_write_bank; // retained compatibility/debug port, not a published frame
 // Match vendor FIFO async assertion/two-clock release, plus one guard clock.
 // Never use the DDR-domain reset level as a camera-domain data enable.
 (* ASYNC_REG="TRUE" *) reg [2:0] fifo_write_release;
 always @(posedge I_camera_clk or posedge S_fifo_rst)
  if(S_fifo_rst)fifo_write_release<=0;
  else fifo_write_release<={fifo_write_release[1:0],1'b1};
 wire camera_we=crst && I_camera_valid && fifo_write_release[2] && !fifo_full && camera_words<FRAME_WORDS;
 w128_d512_fifo U_w128_d512_fifo(
  .rst(S_fifo_rst),.clkw(I_camera_clk),.we(camera_we),.di(I_camera_data),
  .full_flag(fifo_full),.afull(),.wrusedw(),.clkr(I_ddr_clk),.re(S_fifo_rd_en),
  .dout(O_ddr_user_wr_data),.rdusedw(S_fifo_rd_num),.valid(),.empty_flag(fifo_empty),.aempty());
 always @(posedge I_camera_clk or negedge crst)begin
  if(!crst)begin
   S_camera_frame_start_extend<=0;extend_count<=0;camera_words<=0;
   camera_bad<=0;previous_good<=0;camera_seen<=0;O_capture_error<=0;
  end else if(crst)begin
   if(I_camera_frame_start)begin
    S_camera_frame_start_extend<=1;extend_count<=0;
    previous_good<=camera_seen && camera_words==FRAME_WORDS && !camera_bad && !I_mipi_rx_error;
    if(camera_seen && camera_words!=FRAME_WORDS)O_capture_error[2]<=1;
    camera_seen<=1;camera_words<=0;camera_bad<=0;
   end else begin
    if(S_camera_frame_start_extend)begin
     if(extend_count==7)S_camera_frame_start_extend<=0;
     else extend_count<=extend_count+1'b1;
    end
    if(I_camera_valid)begin
     if(camera_words<FRAME_WORDS+1)camera_words<=camera_words+1'b1;
     if(fifo_full)begin camera_bad<=1;O_capture_error[0]<=1;end
     if(!fifo_write_release[2] || camera_words>=FRAME_WORDS)begin camera_bad<=1;O_capture_error[1]<=1;end
    end
    if(I_mipi_rx_error)camera_bad<=1;
   end
  end
 end
 always @(posedge I_ddr_clk or negedge I_rst_n)begin
  if(!I_rst_n)begin fs_sync<=0;good_sync<=0;end
  else begin fs_sync<={fs_sync[2:0],S_camera_frame_start_extend};good_sync<={good_sync[0],previous_good};end
 end
 function [24:0] base(input [1:0] b);
  case(b)0:base=25'd0;1:base=25'd7000000;2:base=25'd14000000;3:base=25'd21000000;endcase
 endfunction
 always @(posedge I_ddr_clk or negedge I_rst_n)begin
  if(!I_rst_n)begin
   setup_count<=0;S_ddr_wr_valid<=0;burst_count<=0;write_words<=0;
   O_ddr_user_wr_en<=0;O_ddr_user_addr<=0;
  end else if(!drst)O_ddr_user_wr_en<=0;
  else begin
   O_ddr_user_wr_en<=S_fifo_rd_en;
   if(O_ddr_user_wr_en)begin write_words<=write_words+1'b1;O_ddr_user_addr<=O_ddr_user_addr+25'd8;end
   if(S_frame_start)begin
    setup_count<=17;S_ddr_wr_valid<=0;burst_count<=0;write_words<=0;
   end else if(setup_count!=0)begin
    setup_count<=setup_count-1'b1;
    // The manager allocated the new bank on the frame-boundary edge.
    // Old output-stage command has left before changing its address.
    if(setup_count==16)O_ddr_user_addr<=base(I_write_bank);
   end else if(S_ddr_wr_valid)begin
    if(S_fifo_rd_en)begin
     if(burst_count==239)begin S_ddr_wr_valid<=0;burst_count<=0;end
     else burst_count<=burst_count+1'b1;
    end
   end else if(S_fifo_rd_num>=240 && !I_video_out_rd_busy && !S_fifo_rst &&
                !O_ddr_user_wr_en && write_words<FRAME_WORDS && !I_display_pause)begin
    S_ddr_wr_valid<=1;burst_count<=0;
   end
  end
 end
endmodule
