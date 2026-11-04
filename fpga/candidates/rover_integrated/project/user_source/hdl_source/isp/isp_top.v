module isp_top #(
    parameter IMG_WIDTH=1280, IMG_HEIGHT=720, ENABLE_MODE_OSD=1
)(
    input I_quality_abort,
    output O_quality_valid,O_quality_good,
    output [31:0] O_quality_frame,
    output [23:0] O_quality_y_sum,
    output [15:0] O_quality_count,O_quality_dark,O_quality_bright,O_quality_global_count,O_quality_global_bright,
    output [11:0] O_quality_r_gain,O_quality_b_gain,
    output O_quality_awb_stable,O_quality_awb_confident,
    input [4:0] cfg_mode, input [1:0] cfg_sat_level,
    input [7:0] cfg_binary_th,
    input [10:0] cfg_edge_th,
    output [4:0] t06_active_mode, output wire [6:0] t06_display_style,
    output t06_error,
    output O_tsof_aligned,
    output [95:0] O_analysis_rgb4,output [31:0] O_motion_gray4,output O_motion_valid,O_motion_sof,O_motion_eol,O_motion_abort,
    input 			axi4s_video_aclk,
    input 			I_rst_n			,
    input 			I_tlast			,
    input 			I_tuser			,
    input [39:0] 	I_tdata			,
    input 			I_tvalid		,
    input [9:0] 	I_tdest			,
    input 			O_tready		,
    output [127:0] 	O_tdata			,
    output 			O_tlast			,
    output 			O_tuser			,
    output 			O_tvalid		,
    output 			I_tready
);
 
wire         m_aixs_tvalid;  //synthesis keep 
  wire [127:0] m_aixs_tdata;  //synthesis keep 
  wire         m_aixs_tuser;  //synthesis keep 
  wire         m_aixs_tlast;  //synthesis keep 
  wire         m_aixs_tready;  //synthesis keep 
  
  wire [ 95:0] m_aixs_tdata_96;  //synthesis keep 

  wire         awb_O_tlast;  //synthesis keep 
  wire         awb_O_tuser;  //synthesis keep 
  wire [ 95:0] awb_O_tdata;  //synthesis keep 
  wire         awb_O_tvalid;  //synthesis keep 
  wire         awb_O_tready;  //synthesis keep 
  // This camera path cannot stall. O_tready is tied high by the board top.
  assign awb_O_tready = 1'b1;

demosaic #(
    .IMG_HEIGHT          (IMG_HEIGHT), // 图像高度
    .IMG_WIDTH           (IMG_WIDTH), // 图像宽度
    .data_complete_delay (50  ),
    .BAYER_MODE          ("BGGR")
)
u_demosaic
(
    .I_clk   			(axi4s_video_aclk)	,   // 时钟信号
    .I_rst_n 			(I_rst_n)	,   // 复位信号，低有效
    .axi4s_video_tdata 	(I_tdata)	,  // AXI4-Stream视频数据
    .axi4s_video_tdest 	(I_tdest)	,
    .axi4s_video_tlast 	(I_tlast)	,  // 行结束信号
    .axi4s_video_tvalid	(I_tvalid)	,  // 数据有效信号
    .axi4s_video_tuser 	(I_tuser)	,  // 帧开始信号
    .axi4s_video_tready	(I_tready)	,  // 从模块准备好接受数据
    .O_tlast  			(m_aixs_tlast)	,  // 输出行结束信号
    .O_tuser  			(m_aixs_tuser)	,  // 输出帧开始信号
    .O_tdata  			(m_aixs_tdata)	,  // 输出数据
    .O_tvalid 			(m_aixs_tvalid)	,  // 输出数据有效信号
    .O_tready   		(m_aixs_tready)	   // 输出数据准备好信号
);
 
data128_96 u_data128_96 (
    .I_tdata(m_aixs_tdata),
    .O_tdata(m_aixs_tdata_96)
);
awb #(
    .IMG_HEIGHT(IMG_HEIGHT),
    .IMG_WIDTH (IMG_WIDTH)
) u_awb (
    .I_quality_abort(I_quality_abort),
    .O_stats_valid(O_quality_valid),.O_stats_good(O_quality_good),.O_stats_frame(O_quality_frame),
    .O_y_sum(O_quality_y_sum),.O_sample_count(O_quality_count),.O_dark_count(O_quality_dark),
    .O_bright_count(O_quality_bright),.O_global_count(O_quality_global_count),.O_global_bright(O_quality_global_bright),
    .O_awb_r_gain(O_quality_r_gain),.O_awb_b_gain(O_quality_b_gain),
    .O_awb_stable(O_quality_awb_stable),.O_awb_confident(O_quality_awb_confident),
    .I_clk   (axi4s_video_aclk),
    .I_rst_n (I_rst_n),
    .I_tlast (m_aixs_tlast),
    .I_tuser (m_aixs_tuser),
    .I_tdata (m_aixs_tdata_96),
    .I_tvalid(m_aixs_tvalid),
    .I_tready(m_aixs_tready),
    .O_tlast (awb_O_tlast ),
    .O_tuser (awb_O_tuser ),
    .O_tdata (awb_O_tdata ),
    .O_tvalid(awb_O_tvalid),
    .O_tready(awb_O_tready)
);
    reg [95:0] t06_input_data;
    reg t06_input_valid, t06_input_frame;
    always @(posedge axi4s_video_aclk or negedge I_rst_n) begin
      if(!I_rst_n) begin t06_input_data<=0; t06_input_valid<=0; t06_input_frame<=0; end
      else begin
        t06_input_data<=awb_O_tdata;
        t06_input_valid<=awb_O_tvalid;
        t06_input_frame<=awb_O_tuser;
      end
    end
    t06_native_bridge #(.WIDTH(IMG_WIDTH),.HEIGHT(IMG_HEIGHT),.ENABLE_MODE_OSD(ENABLE_MODE_OSD)) u_t06 (
        .clk(axi4s_video_aclk),.rst_n(I_rst_n),
        .native_data(t06_input_data),.native_valid(t06_input_valid),
        .native_frame_start(t06_input_frame),
        .cfg_mode(cfg_mode),.cfg_sat_level(cfg_sat_level),.cfg_binary_th(cfg_binary_th),.cfg_edge_th(cfg_edge_th),
        // Native frame preparation pulse for the EXISTING video_in FIFO reset.
        // Do NOT substitute the aligned SOF here: it would erase initial pixels.
        .frame_start_early(O_tuser),
        .data128(O_tdata),.valid128(O_tvalid),
        .sof128(O_tsof_aligned),.eol128(O_tlast),
        .active_mode(t06_active_mode),.error(t06_error),.display_style(t06_display_style),
        .rgb4(O_analysis_rgb4),.gray4(O_motion_gray4),.gray_valid(O_motion_valid),.gray_sof(O_motion_sof),
        .gray_eol(O_motion_eol),.gray_abort(O_motion_abort)
    );
endmodule
