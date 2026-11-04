

module design_top_wrapper #(
    parameter T06_DIAG_OSD = 1,
    parameter T06_ENABLE_AUTO_EXPOSURE = 1,
    parameter [4:0] T06_BOOT_MODE = 5'd0,
    parameter [7:0] T06_BINARY_THRESHOLD = 8'd128,
    parameter [10:0] T06_EDGE_THRESHOLD = 11'd80
)(

    input wire        I_sys_clk,
    input wire        I_hdmi_hpd_en_sense, // B17: passive sense of shared HPD/EN node; NEVER drive
    input wire        I_rst_n,
      
    output wire       O_cam_scl,
    inout  wire       IO_cam_sda,
    output wire       O_cam_24m,
    output wire       O_cam_rst,
      
    input wire [1:0] I_preset_sw, // SW3/E11 bit0, SW4/D11 bit1; display-only REF
    input wire [1:0] I_saturation_sw, // OnlyFPGAinput; pinsassignedby schematicreview
    input wire       I_mode_key_n, // K4 / KEY3 / C7, R73 external 10k pull-up to 3.3V

 //   output wire       O_screen_pwm,
    output wire       O_tmds_ch0_p,
    output wire       O_tmds_ch1_p,
    output wire       O_tmds_ch2_p,
    output wire       O_tmds_clk_p,

    inout wire        IO_rx_clk_pad_n, 
    inout wire        IO_rx_clk_pad_p, 
    inout wire[3:0]   IO_rx_data_pad_n,
    inout wire[3:0]   IO_rx_data_pad_p,

    output wire[12:0] ddr_addr,
    output wire[ 1:0] ddr_ba,
    output wire[ 0:0] ddr_cke,
    output wire[ 0:0] ddr_odt,
    output wire[ 0:0] ddr_cs_n,
    output wire       ddr_ras_n,
    output wire       ddr_cas_n,
    output wire       ddr_we_n,
    output wire[ 0:0] ddr_ck_p,
    output wire[ 0:0] ddr_ck_n,
    inout wire[1:0]   ddr_dm,
    inout wire[15:0]  ddr_dq,
    inout wire[1:0]   ddr_dqs_p,
    inout wire[1:0]   ddr_dqs_n,
    output wire[7:0] O_meter_segment_n,
    output wire[7:0] O_meter_digit_n   
);


    wire        	S_100m_clk;
    wire        	S_24m_clk;
    wire        	S_aux_50m_clk;
	wire        	S_10m_clk;
		
	wire        	S_pll_lock;
    wire        	S_rst_n;
	wire S_cam_pwdnb;
	wire S_cam_i2c_ready;
	(* keep = "true" *) wire [15:0] S_cam_sensor_id;
	(* keep = "true" *) wire        S_cam_sensor_id_ok;
	(* keep = "true" *) wire        S_cam_i2c_error;
	
    wire S_rx_frame_error;
    wire S_quality_valid,S_quality_good,S_quality_awb_stable,S_quality_awb_confident;
    wire [31:0] S_quality_frame;
    wire [23:0] S_quality_y_sum;
    wire [15:0] S_quality_count,S_quality_dark,S_quality_bright,S_quality_global_count,S_quality_global_bright;
    wire [11:0] S_quality_r_gain,S_quality_b_gain;
    wire [3:0] S_aq_state;
    wire S_aq_stable,S_aq_fault,S_aq_stats_busy,S_aq_awb_stable,S_aq_awb_confident;
    wire [31:0] S_aq_dropped,S_aq_last_frame;
    wire [23:0] S_aq_last_y;
    wire [15:0] S_aq_last_count,S_aq_last_dark,S_aq_last_bright;
    wire [11:0] S_aq_r_gain,S_aq_b_gain;
    wire [23:0] S_quality_rgb;
    wire [167:0] S_aq_hdmi_payload;
    wire S_aq_hdmi_valid,S_aq_telemetry_busy;
    wire [31:0] S_aq_telemetry_dropped;
    reg [17:0] S_aq_telemetry_tick;
	wire [15:0] 	S_ae;
    wire [15:0] 	S_ag;
    wire 			S_cam_cfg_done;
    wire 			S_ae_cfg_done;
    wire 			S_ae_req; 
	
	wire        	S_csi_rx_clk;  
    wire        	S_hs_rx_valid;  
    wire[15:0]  	S_hs_rx_data;   
	wire[1:0]   	S_lane_error;
	
	wire        	S_csi_frame_start;       
	wire        	S_csi_frame_end;         
	wire        	S_csi_valid;             
	wire[31:0]  	S_csi_data;  
		
	wire        	S_raw10_frame_start; 
	wire        	S_raw10_frame_end;   
	wire        	S_raw10_valid;       
	wire [39:0] 	S_raw10_data;
		
	wire 			S_axis_tlast;  
	wire 			S_axis_tuser;  
	wire [39:0]		S_axis_tdata;  
	wire 			S_axis_tvalid; 
	
	wire [39:0]		S_raw_tdata ;
	wire			S_raw_tlast ;
	wire 			S_raw_tvalid;
	wire 			S_raw_tuser ;
	
	wire			S_ISP_O_tready;
	wire [127:0]	S_ISP_O_tdata ;
	wire 			S_ISP_O_tlast ;
	wire 			S_ISP_O_tuser ;
	wire 			S_ISP_O_tvalid; 
	

    wire S_fb_boundary,S_fb_good,S_fb_acquire,S_fb_latest_valid,S_fb_read_valid;
    wire        S_ddr_clk;
    wire        S_hdmi_pixel_clk;
    wire        S_hdmi_serial_clk;
    wire        S_hdmi_rst_n;
    wire        S_video_out_rst_n;


    wire        S_vi_128b_frame_start;
    wire        S_vi_128b_valid;      
    wire[127:0] S_vi_128b_data;    
    
    wire        S_video_out_rd_busy;
    wire        S_video_in_wr_busy; 
    wire[1:0]   S_video_out_rp;     

    wire        S_ddr_user_wr_en;       
    wire        S_ddr_user_rd_en;       
    wire[24:0]  S_ddr_user_addr;        
    wire[127:0] S_ddr_user_wr_data;     
    wire        S_ddr_user_ready;       
    wire        S_ddr_user_rd_valid;    
    wire[127:0] S_ddr_user_rd_data;     

    wire        S_vi_ddr_wr_en;   
    wire[24:0]  S_vi_ddr_wr_addr; 
    wire[127:0] S_vi_ddr_wr_data;
    wire        S_vi_ddr_wr_ready;

    wire        S_vo_ddr_rd_en;   
    wire[24:0]  S_vo_ddr_rd_addr; 
    wire        S_vo_ddr_rd_ready;
    wire        S_vo_dbg_fifo_rst;
    wire        S_vo_dbg_ddr_rd_valid;
    wire        S_vo_dbg_fifo_rd_en;
    wire        S_vo_dbg_fifo_empty;

    wire        S_init_calib_complete; 
    wire[24:0]  S_mc_app_addr;          
    wire[2:0]   S_mc_app_cmd;           
    wire        S_mc_app_en;            
    wire[127:0] S_mc_app_wdf_data;      
    wire        S_mc_app_wdf_end;       
    wire[31:0]  S_mc_app_wdf_mask;      
    wire        S_mc_app_wdf_wren;      
    wire[127:0] S_mc_app_rd_data;       
    wire        S_mc_app_rd_data_end;   
    wire        S_mc_app_rd_data_valid; 
    wire        S_mc_app_rdy;           
    wire        S_mc_app_wdf_rdy;       
    wire        S_mc_dbg_fifo_afull;
    wire        S_mc_dbg_app_rdy;
    wire        S_mc_dbg_wdf_rdy;
    wire        S_mc_dbg_cmd_pop;

    wire        S_hdmi_vsync;
    wire        S_hdmi_hsync;
    wire        S_hdmi_de;
    wire        S_hdmi_user;
    wire        S_hdmi_last;
    wire        S_video_out_vsync;
    wire        S_hdmi_window_rd_en;
    wire        S_hdmi_out_vsync;
    wire        S_hdmi_out_hsync;
    wire        S_hdmi_out_de;
    wire[23:0]  S_hdmi_out_data;


    // LF14 passive telemetry wires, all result buses below are HDMI-domain.
    wire S_lf_read_good,S_lf_read_bad;
    reg [6:0] S_lf_good_pipe,S_lf_bad_pipe;
    wire [23:0] S_lf_rgb;
    wire [31:0] S_motion_gray4,S_motion_source_id;
    wire [95:0] S_analysis_rgb4;
    wire S_analysis_valid;wire [15:0] S_analysis_rgb_sig,S_analysis_gray_sig;
    wire S_motion_gray_valid,S_motion_gray_sof,S_motion_gray_eol,S_motion_abort,S_motion_source_valid;
    wire [23:0] S_motion_rgb;
    wire [2:0] S_motion_state;wire S_motion_stable,S_motion_valid;
    wire [13:0] S_motion_changed;wire [15:0] S_motion_events;
    wire [7:0] S_motion_xmin,S_motion_xmax;wire [6:0] S_motion_ymin,S_motion_ymax;
    wire [1:0] S_lf_status;
    wire S_lf_measure,S_lf_source_fault,S_lf_display_fault,S_lf_current_bad;
    wire [31:0] S_lf_id,S_lf_capture_us,S_lf_display_us,S_lf_latency_us;
    wire [31:0] S_lf_new,S_lf_repeat,S_lf_skip,S_lf_invalid,S_lf_stale,S_lf_partial;
    wire [31:0] S_lf_captured,S_lf_committed,S_lf_dropped,S_lf_metadata_bad;

    wire[23:0]  S_video_rd_data;
    reg         S_dbg_raw_seen;
    reg         S_dbg_isp_seen;
    reg         S_dbg_ddr_wr_seen;
    reg         S_dbg_ddr_rd_seen;
    reg         S_dbg_cam_cfg_seen;
    reg         S_dbg_hs_seen;
    reg         S_dbg_csi_seen;
    reg         S_dbg_raw10_seen;
    reg         S_dbg_isp_fs_seen;
    reg         S_dbg_isp_valid_seen;
    reg         S_dbg_ddr_req_seen;
    reg         S_dbg_ddr_ready_seen;
    reg [1:0]   S_dbg_raw_seen_sync;
    reg [1:0]   S_dbg_isp_seen_sync;
    reg [1:0]   S_dbg_ddr_wr_seen_sync;
    reg [1:0]   S_dbg_ddr_rd_seen_sync;
    reg [1:0]   S_dbg_cam_cfg_seen_sync;
    reg [1:0]   S_dbg_hs_seen_sync;
    reg [1:0]   S_dbg_csi_seen_sync;
    reg [1:0]   S_dbg_raw10_seen_sync;
    reg [1:0]   S_dbg_isp_fs_seen_sync;
    reg [1:0]   S_dbg_isp_valid_seen_sync;
    reg [1:0]   S_dbg_ddr_req_seen_sync;
    reg [1:0]   S_dbg_ddr_ready_seen_sync;
    reg         S_dbg_video_nonzero_seen;
    reg         S_dbg_rd_req_seen;
    reg         S_dbg_rd_valid_seen;
    reg         S_dbg_rd_nonzero_seen;
    reg [1:0]   S_dbg_rd_req_seen_sync;
    reg [1:0]   S_dbg_rd_valid_seen_sync;
    reg [1:0]   S_dbg_rd_nonzero_seen_sync;
    reg         S_dbg_mc_init_seen;
    reg         S_dbg_mc_app_rdy_seen;
    reg         S_dbg_mc_wdf_rdy_seen;
    reg         S_dbg_mc_cmd_pop_seen;
    reg [1:0]   S_dbg_mc_init_seen_sync;
    reg [1:0]   S_dbg_mc_app_rdy_seen_sync;
    reg [1:0]   S_dbg_mc_wdf_rdy_seen_sync;
    reg [1:0]   S_dbg_mc_cmd_pop_seen_sync;
    wire[3:0]   S_hdmi_debug_status;
    wire        S_lane_error_any;


//    assign O_screen_pwm = 1'b1;
    assign S_video_out_vsync = ~S_hdmi_vsync;
	
	
    assign S_rst_n = S_pll_lock & I_rst_n;
    // Each fabric domain releases reset on its own clock. DDR traffic waits
    // for calibration; HDMI timing can start independently and show black.
    wire S_cam_rst_n,S_rx_rst_n,S_lp_rst_n,S_ddr_core_rst_n,S_ddr_run_rst_n;
    wire S_ddr_ip_rst_n,S_ddr_session_allowed,S_ddr_recovery_seen;
    wire S_ddr_read_recovery_request;
    t06_ddr_recovery u_ddr_recovery(.clk(S_100m_clk),.rst_n(S_lp_rst_n),
      .calibrated(S_init_calib_complete),.recover_request(S_ddr_read_recovery_request),
      .core_rst_n(S_ddr_ip_rst_n),
      .session_allowed(S_ddr_session_allowed),.fault_seen(S_ddr_recovery_seen));
    t06_reset_release u_cam_reset(.clk(S_24m_clk),.arst_n(S_rst_n),.rst_n(S_cam_rst_n));
    t06_reset_release u_rx_reset(.clk(S_csi_rx_clk),.arst_n(S_rst_n),.rst_n(S_rx_rst_n));
    t06_reset_release u_lp_reset(.clk(S_100m_clk),.arst_n(S_rst_n),.rst_n(S_lp_rst_n));
    t06_reset_release u_ddr_reset(.clk(S_ddr_clk),.arst_n(S_rst_n),.rst_n(S_ddr_core_rst_n));
    t06_reset_release u_ddr_run_reset(.clk(S_ddr_clk),.arst_n(S_rst_n & S_ddr_session_allowed),.rst_n(S_ddr_run_rst_n));
    t06_reset_release u_hdmi_reset(.clk(S_hdmi_pixel_clk),.arst_n(S_rst_n),.rst_n(S_hdmi_rst_n));

    always @(posedge S_csi_rx_clk or negedge S_rx_rst_n) begin
        if(!S_rx_rst_n)
            S_dbg_raw_seen <= 1'b0;
        else if(S_raw10_frame_start | S_axis_tvalid)
            S_dbg_raw_seen <= 1'b1;
    end

    always @(posedge S_csi_rx_clk or negedge S_rx_rst_n) begin
        if(!S_rx_rst_n)
            S_dbg_isp_seen <= 1'b0;
        else if(S_ISP_O_tuser | S_ISP_O_tvalid)
            S_dbg_isp_seen <= 1'b1;
    end

    always @(posedge S_ddr_clk or negedge S_ddr_core_rst_n) begin
        if(!S_ddr_core_rst_n)
            S_dbg_ddr_wr_seen <= 1'b0;
        else if(S_vi_ddr_wr_en)
            S_dbg_ddr_wr_seen <= 1'b1;
    end

    always @(posedge S_ddr_clk or negedge S_ddr_core_rst_n) begin
        if(!S_ddr_core_rst_n)
            S_dbg_ddr_rd_seen <= 1'b0;
        else if(S_ddr_user_rd_valid)
            S_dbg_ddr_rd_seen <= 1'b1;
    end

    always @(posedge S_24m_clk or negedge S_cam_rst_n) begin
        if(!S_cam_rst_n)
            S_dbg_cam_cfg_seen <= 1'b0;
        else if(S_cam_cfg_done)
            S_dbg_cam_cfg_seen <= 1'b1;
    end

    always @(posedge S_csi_rx_clk or negedge S_rx_rst_n) begin
        if(!S_rx_rst_n)
            S_dbg_hs_seen <= 1'b0;
        else if(S_hs_rx_valid)
            S_dbg_hs_seen <= 1'b1;
    end

    always @(posedge S_csi_rx_clk or negedge S_rx_rst_n) begin
        if(!S_rx_rst_n)
            S_dbg_csi_seen <= 1'b0;
        else if(S_csi_frame_start | S_csi_valid)
            S_dbg_csi_seen <= 1'b1;
    end

    always @(posedge S_csi_rx_clk or negedge S_rx_rst_n) begin
        if(!S_rx_rst_n)
            S_dbg_raw10_seen <= 1'b0;
        else if(S_raw10_frame_start | S_raw10_valid)
            S_dbg_raw10_seen <= 1'b1;
    end

    always @(posedge S_csi_rx_clk or negedge S_rx_rst_n) begin
        if(!S_rx_rst_n)
            S_dbg_isp_fs_seen <= 1'b0;
        else if(S_ISP_O_tuser)
            S_dbg_isp_fs_seen <= 1'b1;
    end

    always @(posedge S_csi_rx_clk or negedge S_rx_rst_n) begin
        if(!S_rx_rst_n)
            S_dbg_isp_valid_seen <= 1'b0;
        else if(S_ISP_O_tvalid)
            S_dbg_isp_valid_seen <= 1'b1;
    end

    always @(posedge S_ddr_clk or negedge S_ddr_core_rst_n) begin
        if(!S_ddr_core_rst_n)
            S_dbg_ddr_req_seen <= 1'b0;
        else if(S_vi_ddr_wr_en)
            S_dbg_ddr_req_seen <= 1'b1;
    end

    always @(posedge S_ddr_clk or negedge S_ddr_core_rst_n) begin
        if(!S_ddr_core_rst_n)
            S_dbg_ddr_ready_seen <= 1'b0;
        else if(S_ddr_user_ready)
            S_dbg_ddr_ready_seen <= 1'b1;
    end

    always @(posedge S_ddr_clk or negedge S_video_out_rst_n) begin
        if(!S_video_out_rst_n)
            S_dbg_rd_req_seen <= 1'b0;
        else if(S_fb_acquire)
            S_dbg_rd_req_seen <= 1'b0;
        else if(S_vo_ddr_rd_en)
            S_dbg_rd_req_seen <= 1'b1;
    end

    always @(posedge S_ddr_clk or negedge S_video_out_rst_n) begin
        if(!S_video_out_rst_n)
            S_dbg_rd_valid_seen <= 1'b0;
        else if(S_fb_acquire)
            S_dbg_rd_valid_seen <= 1'b0;
        else if(S_ddr_user_rd_valid)
            S_dbg_rd_valid_seen <= 1'b1;
    end

    always @(posedge S_hdmi_pixel_clk or negedge S_hdmi_rst_n) begin
        if(!S_hdmi_rst_n)
            S_dbg_rd_nonzero_seen <= 1'b0;
        else if(S_video_out_vsync)
            S_dbg_rd_nonzero_seen <= 1'b0;
        else if(S_hdmi_window_rd_en && (S_video_rd_data != 24'd0))
            S_dbg_rd_nonzero_seen <= 1'b1;
    end

    always @(posedge S_ddr_clk or negedge S_ddr_core_rst_n) begin
        if(!S_ddr_core_rst_n)
            S_dbg_mc_init_seen <= 1'b0;
        else if(S_init_calib_complete)
            S_dbg_mc_init_seen <= 1'b1;
    end

    always @(posedge S_ddr_clk or negedge S_ddr_core_rst_n) begin
        if(!S_ddr_core_rst_n)
            S_dbg_mc_app_rdy_seen <= 1'b0;
        else if(S_mc_dbg_app_rdy)
            S_dbg_mc_app_rdy_seen <= 1'b1;
    end

    always @(posedge S_ddr_clk or negedge S_ddr_core_rst_n) begin
        if(!S_ddr_core_rst_n)
            S_dbg_mc_wdf_rdy_seen <= 1'b0;
        else if(S_mc_dbg_wdf_rdy)
            S_dbg_mc_wdf_rdy_seen <= 1'b1;
    end

    always @(posedge S_ddr_clk or negedge S_ddr_core_rst_n) begin
        if(!S_ddr_core_rst_n)
            S_dbg_mc_cmd_pop_seen <= 1'b0;
        else if(S_mc_dbg_cmd_pop)
            S_dbg_mc_cmd_pop_seen <= 1'b1;
    end

    always @(posedge S_hdmi_pixel_clk or negedge S_hdmi_rst_n) begin
        if(!S_hdmi_rst_n) begin
            S_dbg_cam_cfg_seen_sync <= 2'b00;
            S_dbg_hs_seen_sync      <= 2'b00;
            S_dbg_csi_seen_sync     <= 2'b00;
            S_dbg_raw10_seen_sync   <= 2'b00;
            S_dbg_raw_seen_sync    <= 2'b00;
            S_dbg_isp_seen_sync    <= 2'b00;
            S_dbg_ddr_wr_seen_sync <= 2'b00;
            S_dbg_ddr_rd_seen_sync <= 2'b00;
            S_dbg_isp_fs_seen_sync  <= 2'b00;
            S_dbg_isp_valid_seen_sync <= 2'b00;
            S_dbg_ddr_req_seen_sync <= 2'b00;
            S_dbg_ddr_ready_seen_sync <= 2'b00;
            S_dbg_video_nonzero_seen <= 1'b0;
            S_dbg_rd_req_seen_sync <= 2'b00;
            S_dbg_rd_valid_seen_sync <= 2'b00;
            S_dbg_rd_nonzero_seen_sync <= 2'b00;
            S_dbg_mc_init_seen_sync <= 2'b00;
            S_dbg_mc_app_rdy_seen_sync <= 2'b00;
            S_dbg_mc_wdf_rdy_seen_sync <= 2'b00;
            S_dbg_mc_cmd_pop_seen_sync <= 2'b00;
        end
        else begin
            S_dbg_cam_cfg_seen_sync <= {S_dbg_cam_cfg_seen_sync[0], S_dbg_cam_cfg_seen};
            S_dbg_hs_seen_sync      <= {S_dbg_hs_seen_sync[0],      S_dbg_hs_seen};
            S_dbg_csi_seen_sync     <= {S_dbg_csi_seen_sync[0],     S_dbg_csi_seen};
            S_dbg_raw10_seen_sync   <= {S_dbg_raw10_seen_sync[0],   S_dbg_raw10_seen};
            S_dbg_raw_seen_sync    <= {S_dbg_raw_seen_sync[0],    S_dbg_raw_seen};
            S_dbg_isp_seen_sync    <= {S_dbg_isp_seen_sync[0],    S_dbg_isp_seen};
            S_dbg_ddr_wr_seen_sync <= {S_dbg_ddr_wr_seen_sync[0], S_dbg_ddr_wr_seen};
            S_dbg_ddr_rd_seen_sync <= {S_dbg_ddr_rd_seen_sync[0], S_dbg_ddr_rd_seen};
            S_dbg_isp_fs_seen_sync  <= {S_dbg_isp_fs_seen_sync[0],  S_dbg_isp_fs_seen};
            S_dbg_isp_valid_seen_sync <= {S_dbg_isp_valid_seen_sync[0], S_dbg_isp_valid_seen};
            S_dbg_ddr_req_seen_sync <= {S_dbg_ddr_req_seen_sync[0], S_dbg_ddr_req_seen};
            S_dbg_ddr_ready_seen_sync <= {S_dbg_ddr_ready_seen_sync[0], S_dbg_ddr_ready_seen};
            S_dbg_rd_req_seen_sync <= {S_dbg_rd_req_seen_sync[0], S_dbg_rd_req_seen};
            S_dbg_rd_valid_seen_sync <= {S_dbg_rd_valid_seen_sync[0], S_dbg_rd_valid_seen};
            S_dbg_rd_nonzero_seen_sync <= {S_dbg_rd_nonzero_seen_sync[0], S_dbg_rd_nonzero_seen};
            S_dbg_mc_init_seen_sync <= {S_dbg_mc_init_seen_sync[0], S_dbg_mc_init_seen};
            S_dbg_mc_app_rdy_seen_sync <= {S_dbg_mc_app_rdy_seen_sync[0], S_dbg_mc_app_rdy_seen};
            S_dbg_mc_wdf_rdy_seen_sync <= {S_dbg_mc_wdf_rdy_seen_sync[0], S_dbg_mc_wdf_rdy_seen};
            S_dbg_mc_cmd_pop_seen_sync <= {S_dbg_mc_cmd_pop_seen_sync[0], S_dbg_mc_cmd_pop_seen};
            if(S_hdmi_window_rd_en && (S_video_rd_data != 24'd0))
                S_dbg_video_nonzero_seen <= 1'b1;
        end
    end

    assign S_lane_error_any = |S_lane_error;

    assign S_vo_dbg_fifo_rst = 1'b0;
    assign S_vo_dbg_ddr_rd_valid = 1'b0;
    assign S_vo_dbg_fifo_rd_en = 1'b0;
    assign S_vo_dbg_fifo_empty = 1'b0;
    assign S_mc_dbg_fifo_afull = 1'b0;
    assign S_mc_dbg_app_rdy = 1'b0;
    assign S_mc_dbg_wdf_rdy = 1'b0;
    assign S_mc_dbg_cmd_pop = 1'b0;

    assign S_hdmi_debug_status = {
        (|S_ddr_user_rd_data),
        S_ddr_user_rd_valid,
        S_vo_ddr_rd_en,
        S_vi_ddr_wr_en
    };
	
	// SC520CS上电后先保持PWDNB/XSHUTDN为低，再释放并等待内部上电完成，
	// 避免PLL刚锁定就开始I2C初始化而造成寄存器偶发写入失败。
    t06_camera_startup u_camera_startup(
        .clk(S_24m_clk),.rst_n(S_cam_rst_n),
        .camera_reset_n(S_cam_pwdnb),.i2c_ready(S_cam_i2c_ready));

	assign O_cam_rst 	= S_cam_pwdnb;
    assign O_cam_24m 	= S_24m_clk;
	
	
	
	
    PLL u_PLL(
        .refclk      ( I_sys_clk         ),
        .reset    	 ( ~I_rst_n          ),
        
        .clk0_out    ( S_100m_clk        ),
        .clk1_out    ( S_24m_clk         ),

        .clk4_out    ( S_hdmi_pixel_clk  ),
        .clk5_out    ( S_hdmi_serial_clk ),

        .lock        ( S_pll_lock        )

    );


	

  
  t06_auto_exposure #(.ENABLE_AUTO(T06_ENABLE_AUTO_EXPOSURE)) u_auto_exposure (
      .I_src_clk(S_csi_rx_clk),.I_dst_clk(S_24m_clk),.I_arst_n(S_rst_n),
      .I_stats_valid(S_quality_valid),.I_stats_good(S_quality_good),.I_frame_id(S_quality_frame),
      .I_y_sum(S_quality_y_sum),.I_sample_count(S_quality_count),.I_dark_count(S_quality_dark),
      .I_bright_count(S_quality_bright),.I_global_count(S_quality_global_count),.I_global_bright(S_quality_global_bright),
      .I_awb_stable(S_quality_awb_stable),.I_awb_confident(S_quality_awb_confident),
      .I_awb_r_gain(S_quality_r_gain),.I_awb_b_gain(S_quality_b_gain),
      .I_cam_cfg_done(S_cam_cfg_done),.I_ae_cfg_done(S_ae_cfg_done),.I_iic_error(S_cam_i2c_error),
      .O_ae_req(S_ae_req),.O_ae(S_ae),.O_ag(S_ag),.O_state(S_aq_state),.O_stable(S_aq_stable),.O_fault(S_aq_fault),
      .O_stats_busy(S_aq_stats_busy),.O_stats_dropped(S_aq_dropped),.O_last_frame_id(S_aq_last_frame),
      .O_last_y_sum(S_aq_last_y),.O_last_sample_count(S_aq_last_count),.O_last_dark_count(S_aq_last_dark),
      .O_last_bright_count(S_aq_last_bright),.O_last_awb_stable(S_aq_awb_stable),.O_last_awb_confident(S_aq_awb_confident),
      .O_last_awb_r_gain(S_aq_r_gain),.O_last_awb_b_gain(S_aq_b_gain)
  );
  // Latest controller telemetry, not an identifier-matched reading of the displayed frame.
  always @(posedge S_24m_clk or negedge S_cam_rst_n)
    if(!S_cam_rst_n) S_aq_telemetry_tick<=0; else S_aq_telemetry_tick<=S_aq_telemetry_tick+1'b1;
  t06_quality_mailbox #(.WIDTH(168)) u_quality_display_mailbox (
    .I_arst_n(S_rst_n),.I_src_clk(S_24m_clk),
    .I_src_valid((S_aq_telemetry_tick==0)&&!S_aq_telemetry_busy),
    .I_src_payload({S_aq_state,S_aq_stable,S_aq_fault,S_aq_awb_stable,S_aq_awb_confident,
       S_ae,S_ag,S_aq_r_gain,S_aq_b_gain,S_aq_last_y,S_aq_last_count,S_aq_last_frame,S_aq_last_dark,S_aq_last_bright}),
    .O_src_busy(S_aq_telemetry_busy),.O_src_dropped(S_aq_telemetry_dropped),
    .I_dst_clk(S_hdmi_pixel_clk),.O_dst_valid(S_aq_hdmi_valid),.O_dst_payload(S_aq_hdmi_payload)
  );
  
    // SC520CS原厂真实HD模式：1280x720@60、RAW10、2-Lane、828 Mbps/Lane。
    // 当前寄存器表已关闭Slave/FSIN等待，Sensor以free-run方式连续输出。
    uicfgcs520 #(
      .CLK_DIV(239) // 23.809524MHz / 240 = 99.20635kHz, below Standard-mode 100kHz maximum
  ) u_uicfgcs520 (
      .I_clk(S_24m_clk),  //系统时钟输入
      .I_rst_n(S_cam_i2c_ready), // SC520CS power-up delay completed
      .I_ae_req(S_ae_req),
      .I_ae(S_ae),
      .I_ag(S_ag),
      .O_cam_scl(O_cam_scl),  //I2C总线，SCL时钟
      .IO_cam_sda(IO_cam_sda),  //I2C总线，SDA数据
      .O_cfg_done(S_cam_cfg_done),  //摄像头寄存器初始化完成
      .O_ae_cfg_done(S_ae_cfg_done),  //AE配置完成
      .O_sensor_id(S_cam_sensor_id),
      .O_sensor_id_ok(S_cam_sensor_id_ok),
      .O_iic_error(S_cam_i2c_error)
  );
	
    mipi_dphy_rx_ph1p_mipiio_wrapper#(
        .DPHY_RX_LOCATION      ( "DPHY0" ),
        .HS_EQUALIZER          ( "3dB"   ),// 828 Mbps/Lane接收均衡
        .HS_VGA_GAIN           ( "8dB" ),//"-3dB","-1.5dB","0dB","1.5dB","3dB","4.5dB","6dB","7.5dB"
        .LANE_NUM              ( 2       ),
        .BYTE_NUM              ( 1       )
    )u_mipi_dphy_rx_ph1p_mipiio_wrapper(
        .I_lp_clk              ( S_100m_clk       ),
        .I_rst                 ( ~S_lp_rst_n         ),

        .I_clk_lane_in_delay   ( 6'd0             ),
        .I_data_lane0_in_delay ( 6'd0             ),
        .I_data_lane1_in_delay ( 6'd0             ),
        .I_data_lane2_in_delay ( 6'd0             ),
        .I_data_lane3_in_delay ( 6'd0             ),

        .I_lane_invert         ( 2'b00          ),
     
        .O_hs_rx_clk           ( S_csi_rx_clk     ),
        .O_hs_rx_valid         ( S_hs_rx_valid    ),
        .O_hs_rx_data          ( S_hs_rx_data     ),
      
        .O_lp_rx_lane0_p       (  ),
        .O_lp_rx_lane0_n       (  ),
      
        .I_lp_tx_en            ( 1'b0             ),
        .I_lp_tx_lane0_p       ( 1'b1             ),
        .I_lp_tx_lane0_n       ( 1'b1             ),
      
        .O_lane_match_error    (                  ),
        .O_lane_error          ( S_lane_error     ),
      
        .IO_rx_clk_pad_n       ( IO_rx_clk_pad_n  ),
        .IO_rx_clk_pad_p       ( IO_rx_clk_pad_p  ),
        .IO_rx_data_pad_n      ( IO_rx_data_pad_n ),
        .IO_rx_data_pad_p      ( IO_rx_data_pad_p )
    );
	
	
 //  cwc cwc_inst
 //(
 //    .probe0(S_hs_rx_valid),
 //    .probe1(S_hs_rx_data),
 //    .probe2(S_lane_error),
 //    .clk(S_csi_rx_clk)
 //);

 //csi 解码为RAW数据
csi_unpacket_2lane u_csi_unpacket(
.I_clk                 ( S_csi_rx_clk       ),
.I_rst_n               ( S_rx_rst_n        	),
.I_hs_valid            ( S_hs_rx_valid     ),
.I_hs_data             ( S_hs_rx_data      ),

.O_csi_frame_start     ( S_csi_frame_start ),
.O_csi_frame_end       ( S_csi_frame_end   ),
.O_csi_valid           ( S_csi_valid       ),
.O_csi_data            ( S_csi_data        )
);


//解码为RAW8
raw10_unpacket_2lane u_raw10_unpacket (
.I_clk  (S_csi_rx_clk),
.I_rst_n(S_rx_rst_n),
.I_camera_black_level(10'd0),

.I_csi_frame_start(S_csi_frame_start),
.I_csi_frame_end  (S_csi_frame_end),
.I_csi_valid      (S_csi_valid),
.I_csi_data       (S_csi_data),

.O_raw10_frame_start(S_raw10_frame_start),
.O_raw10_frame_end  (S_raw10_frame_end),
.O_raw10_valid      (S_raw10_valid),
.O_raw10_data       (S_raw10_data)
  );


//将数据转为stream流
uial2axis #(
.IMG_WIDTH(1280),
.IMG_HEIGHT(720),
.INPUT_DATA_WIDTH(40)
) 
u_uial2axis (
.I_native_clk(S_csi_rx_clk),
.I_rst_n     (S_rx_rst_n),
.I_data      (S_raw10_data       ),
.I_data_valid(S_raw10_valid      ),
.I_data_start(S_raw10_frame_start),
.I_data_end  (S_raw10_frame_end  ),
.axis_tvalid (S_axis_tvalid),
.axis_tdata  (S_axis_tdata ),
.axis_tuser  (S_axis_tuser ),
.axis_tlast  (S_axis_tlast )
);
	

// 原厂HD模式直接输出1280x720 RAW10，不再进行FPGA固定窗口裁剪。
assign S_raw_tdata  = S_axis_tdata;
assign S_raw_tlast  = S_axis_tlast;
assign S_raw_tvalid = S_axis_tvalid;
assign S_raw_tuser  = S_axis_tuser;


//cwc1 cwc1_Inst
//  (
//      .probe0(S_axis_tuser),
//      .probe1(S_axis_tvalid),
//      .probe2(S_axis_tlast),
//      .probe3(S_axis_tdata),
//      .probe4(S_ISP_O_tuser),
//      .probe5(S_ISP_O_tvalid),
//      .probe6(S_ISP_O_tlast),
//      .probe7(S_ISP_O_tdata),
//      .probe8 (S_raw_tdata ),
//      .probe9 (S_raw_tlast ),
//      .probe10(S_raw_tvalid),
//      .probe11(S_raw_tuser ),
//      .clk(S_csi_rx_clk)
//  );


    // T06 release is synchronized to the real CSI byte clock, not HDMI clock.
    (* ASYNC_REG="TRUE" *) reg [1:0] S_t06_reset_sync;
    wire S_t06_rst_n = S_t06_reset_sync[1];
    wire [4:0] S_t06_mode;
    wire [1:0] S_t06_sat_level;
    (* keep="true" *) wire [4:0] S_t06_active_mode;
    (* keep="true" *) wire S_t06_error;
    (* keep="true" *) wire S_t06_sof_aligned;
    always @(posedge S_csi_rx_clk or negedge S_rx_rst_n) begin
        if(!S_rx_rst_n) S_t06_reset_sync<=2'b00;
        else S_t06_reset_sync<={S_t06_reset_sync[0],1'b1};
    end
    t06_mode_control #(.BOOT_MODE(T06_BOOT_MODE)) u_t06_mode (
        .clk(S_csi_rx_clk),.rst_n(S_t06_rst_n),
        .key_n(I_mode_key_n),.mode(S_t06_mode)
    );
    t06_saturation_sw_control u_saturation_sw(
        .clk(S_csi_rx_clk),.rst_n(S_t06_rst_n),.sw_async(I_saturation_sw),.level(S_t06_sat_level)
    );
    assign S_ISP_O_tready = 1'b1; // native camera-to-DDR path has no ready return

//ISP算法顶层模块
wire [6:0] S_t06_display_style;
isp_top u_isp_top (
 .t06_display_style(S_t06_display_style),
.I_quality_abort(S_rx_frame_error),
.O_quality_valid(S_quality_valid),.O_quality_good(S_quality_good),.O_quality_frame(S_quality_frame),
.O_quality_y_sum(S_quality_y_sum),.O_quality_count(S_quality_count),.O_quality_dark(S_quality_dark),
.O_quality_bright(S_quality_bright),.O_quality_global_count(S_quality_global_count),.O_quality_global_bright(S_quality_global_bright),
.O_quality_r_gain(S_quality_r_gain),.O_quality_b_gain(S_quality_b_gain),
.O_quality_awb_stable(S_quality_awb_stable),.O_quality_awb_confident(S_quality_awb_confident),
.cfg_mode        (S_t06_mode),
.cfg_sat_level   (S_t06_sat_level),
.cfg_binary_th   (T06_BINARY_THRESHOLD),
.cfg_edge_th     (T06_EDGE_THRESHOLD),
.t06_active_mode (S_t06_active_mode),
.t06_error       (S_t06_error),
.O_tsof_aligned  (S_t06_sof_aligned),
.O_analysis_rgb4(S_analysis_rgb4),.O_motion_gray4(S_motion_gray4),.O_motion_valid(S_motion_gray_valid),
.O_motion_sof(S_motion_gray_sof),.O_motion_eol(S_motion_gray_eol),.O_motion_abort(S_motion_abort),
.axi4s_video_aclk(S_csi_rx_clk),
.I_rst_n         (S_t06_rst_n),
.I_tlast         (S_raw_tlast	),
.I_tuser         (S_raw_tuser	),
.I_tdata         (S_raw_tdata	),
.I_tvalid        (S_raw_tvalid	),
.I_tdest         (10'd0),
.O_tready        (S_ISP_O_tready),
.O_tdata         (S_ISP_O_tdata ),
.O_tlast         (S_ISP_O_tlast ),
.O_tuser         (S_ISP_O_tuser ),
.O_tvalid        (S_ISP_O_tvalid),
.I_tready        ()
  );


    // Frame ownership and completion are transferred in the DDR clock domain.
    wire [1:0] S_fb_write_bank,S_fb_read_bank;
    wire [2:0] S_fb_capture_error,S_fb_read_error;
    wire [15:0] S_fb_committed,S_fb_dropped;
    t06_frame_manager u_frame_manager(
        .clk(S_ddr_clk),.rst_n(S_ddr_run_rst_n),.camera_boundary(S_fb_boundary),.camera_good(S_fb_good),
        .display_acquire(S_fb_acquire),.write_bank(S_fb_write_bank),
        .latest_bank(S_video_out_rp),.latest_valid(S_fb_latest_valid),
        .read_bank(S_fb_read_bank),.read_valid(S_fb_read_valid),
        .committed_frames(S_fb_committed),.dropped_frames(S_fb_dropped));

    wire S_rx_error_seen;
    wire [15:0] S_rx_error_events;
    t06_rx_fault_guard u_rx_fault_guard(.clk(S_csi_rx_clk),.rst_n(S_rx_rst_n),
      .packed_sof(S_ISP_O_tuser),.lane_error(S_lane_error_any),
      .frame_error(S_rx_frame_error),.error_seen(S_rx_error_seen),.error_events(S_rx_error_events));
    video_in u_video_in(
        .I_write_bank(S_fb_write_bank),.O_frame_boundary(S_fb_boundary),.O_frame_good(S_fb_good),
        .O_capture_error(S_fb_capture_error),
        .I_rst_n              (  S_ddr_run_rst_n             ),

        .I_camera_clk         ( S_csi_rx_clk          ),
        .I_camera_frame_start ( S_ISP_O_tuser  ),
        .I_camera_valid       ( S_ISP_O_tvalid ),
        .I_camera_data        ( S_ISP_O_tdata  ),
        .I_mipi_rx_error      ( S_rx_frame_error ),

        .I_ddr_clk            ( S_ddr_clk             ),
		.I_display_pause      ( 1'b0                  ),
        .I_video_out_rd_busy  ( S_video_out_rd_busy   ),
        .O_video_in_wr_busy   ( S_video_in_wr_busy    ),
        .O_video_out_rp       (                       ),

        .O_ddr_user_wr_en     ( S_vi_ddr_wr_en        ),
        .O_ddr_user_addr      ( S_vi_ddr_wr_addr      ),
        .O_ddr_user_wr_data   ( S_vi_ddr_wr_data      ),
        .I_ddr_user_ready     ( S_ddr_user_ready      )
    );



    assign S_ddr_user_wr_en    = S_vi_ddr_wr_en;

    assign S_ddr_user_rd_en    = S_vo_ddr_rd_en;

    assign S_ddr_user_addr     = S_vi_ddr_wr_en ? S_vi_ddr_wr_addr :
                                 S_vo_ddr_rd_en ? S_vo_ddr_rd_addr : 'd0;

    assign S_ddr_user_wr_data  = S_vi_ddr_wr_data;


    assign S_video_out_rst_n = S_ddr_run_rst_n;

    video_out u_video_out(
        .O_recovery_request(S_ddr_read_recovery_request),
        .I_frame_valid(S_fb_latest_valid),.O_frame_acquire(S_fb_acquire),.O_read_error(S_fb_read_error),
        .O_monitor_pixel_good(S_lf_read_good),.O_monitor_frame_bad(S_lf_read_bad),
        .I_rst_n             ( S_video_out_rst_n    ),
        .I_ddr_clk           ( S_ddr_clk            ),
 
        .O_video_out_rd_busy ( S_video_out_rd_busy  ),
        .I_video_in_wr_busy  ( S_video_in_wr_busy   ),
        .I_video_out_rp      ( S_video_out_rp       ),
 
        .O_ddr_user_rd_en    ( S_vo_ddr_rd_en       ),
        .O_ddr_user_addr     ( S_vo_ddr_rd_addr     ),
        .I_ddr_user_ready    ( S_ddr_user_ready     ),
        .I_ddr_user_rd_valid ( S_ddr_user_rd_valid  ),
        .I_ddr_user_rd_data  ( S_ddr_user_rd_data   ),

        .I_dsi_clk           ( S_hdmi_pixel_clk     ),
        .I_video_vsync       ( S_video_out_vsync    ),
        .I_video_rd_en       ( S_hdmi_window_rd_en  ),
        .O_vdieo_data        ( S_video_rd_data      )
    );



    mc_to_user_interface u_mc_to_user_interface(
        .I_clk                   ( S_ddr_clk               ),
        .I_rst_n                 ( S_ddr_run_rst_n                 ),

        .I_ddr_user_wr_en        ( S_ddr_user_wr_en        ),
        .I_ddr_user_rd_en        ( S_ddr_user_rd_en        ),
        .I_ddr_user_addr         ( S_ddr_user_addr         ),
        .I_ddr_user_wr_data      ( S_ddr_user_wr_data      ),
        .O_ddr_user_ready        ( S_ddr_user_ready        ),
        .O_ddr_user_rd_valid     ( S_ddr_user_rd_valid     ),
        .O_ddr_user_rd_data      ( S_ddr_user_rd_data      ),
            
        .O_mc_app_en             ( S_mc_app_en             ),
        .O_mc_app_addr           ( S_mc_app_addr           ),
        .O_mc_app_cmd            ( S_mc_app_cmd            ),
        .I_mc_app_rdy            ( S_mc_app_rdy            ),
        .O_mc_app_wdf_wren       ( S_mc_app_wdf_wren       ),
        .O_mc_app_wdf_data       ( S_mc_app_wdf_data       ),
        .O_mc_app_wdf_end        ( S_mc_app_wdf_end        ),
        .O_mc_app_wdf_mask       ( S_mc_app_wdf_mask       ),
        .I_mc_app_wdf_rdy        ( S_mc_app_wdf_rdy        ),
        .I_mc_app_rd_data        ( S_mc_app_rd_data        ),
        .I_mc_app_rd_data_end    ( S_mc_app_rd_data_end    ),
        .I_mc_app_rd_data_valid  ( S_mc_app_rd_data_valid  )
    );



    // DDR IP Design.xml PH1P_REF_CLK=100 MHz, DDR_SPEED=1066 MT/s.
    ph1p35_324_ddr_wrapper u_ph1p35_324_ddr_wrapper(
        .I_sys_clk              ( S_100m_clk             ),
        .I_sys_rst_n            ( S_ddr_ip_rst_n                ),

        .O_ddr_clk              ( S_ddr_clk              ),
        .O_init_calib_complete  ( S_init_calib_complete  ),
        .I_mc_app_addr          ( S_mc_app_addr          ),
        .I_mc_app_cmd           ( S_mc_app_cmd           ),
        .I_mc_app_en            ( S_mc_app_en            ),
        .I_mc_app_wdf_data      ( S_mc_app_wdf_data      ),
        .I_mc_app_wdf_end       ( S_mc_app_wdf_end       ),
        .I_mc_app_wdf_mask      ( S_mc_app_wdf_mask[15:0]),
        .I_mc_app_wdf_wren      ( S_mc_app_wdf_wren      ),
        .O_mc_app_rd_data       ( S_mc_app_rd_data       ),
        .O_mc_app_rd_data_end   ( S_mc_app_rd_data_end   ),
        .O_mc_app_rd_data_valid ( S_mc_app_rd_data_valid ),
        .O_mc_app_rdy           ( S_mc_app_rdy           ),
        .O_mc_app_wdf_rdy       ( S_mc_app_wdf_rdy       ),

        .ddr_addr               ( ddr_addr               ),
        .ddr_ba                 ( ddr_ba                 ),
        .ddr_cke                ( ddr_cke                ),
        .ddr_odt                ( ddr_odt                ),
        .ddr_cs_n               ( ddr_cs_n               ),
        .ddr_ras_n              ( ddr_ras_n              ),
        .ddr_cas_n              ( ddr_cas_n              ),
        .ddr_we_n               ( ddr_we_n               ),
        .ddr_ck_p               ( ddr_ck_p               ),
        .ddr_ck_n               ( ddr_ck_n               ),
        .ddr_dm                 ( ddr_dm                 ),
        .ddr_dq                 ( ddr_dq                 ),
        .ddr_dqs_p              ( ddr_dqs_p              ),
        .ddr_dqs_n              ( ddr_dqs_n              )
    );



    uivtc #(
        .H_ActiveSize ( 1280 ),
        .H_FrameSize  ( 1650 ),
        .H_SyncStart  ( 1390 ),
        .H_SyncEnd    ( 1430 ),
        .V_ActiveSize ( 720  ),
        .V_FrameSize  ( 750  ),
        .V_SyncStart  ( 725  ),
        .V_SyncEnd    ( 730  )
    )u_hdmi_vtc(
        .I_vtc_rstn    ( S_hdmi_rst_n    ),
        .I_vtc_clk     ( S_hdmi_pixel_clk ),
        .O_vtc_vs      ( S_hdmi_vsync     ),
        .O_vtc_hs      ( S_hdmi_hsync     ),
        .O_vtc_de_valid( S_hdmi_de        ),
        .O_vtc_user    ( S_hdmi_user      ),
        .O_vtc_last    ( S_hdmi_last      )
    );

    hdmi_mixer #(
        .H_OFFSET   ( 0    ),
        .V_OFFSET   ( 0    ),
        .IMG_WIDTH  ( 1280 ),
        .IMG_HEIGHT ( 720  ),
        .DEBUG_MODE ( 0    ),
        .ENABLE_DEMO_TEXT ( 0 )
    )u_hdmi_mixer(
        .I_clk           ( S_hdmi_pixel_clk   ),
        .I_rst_n         ( S_hdmi_rst_n       ),
        .I_video_vsync   ( S_hdmi_vsync       ),
        .I_video_hsync   ( S_hdmi_hsync       ),
        .I_video_de      ( S_hdmi_de          ),
        .I_video_user    ( S_hdmi_user        ),
        .I_video_last    ( S_hdmi_last        ),
        .I_debug_status  ( S_hdmi_debug_status),
        .O_video_rd_en   ( S_hdmi_window_rd_en),
        .I_video_rd_data ( S_video_rd_data    ),
        .O_hdmi_vsync    ( S_hdmi_out_vsync   ),
        .O_hdmi_hsync    ( S_hdmi_out_hsync   ),
        .O_hdmi_de       ( S_hdmi_out_de      ),
        .O_hdmi_data     ( S_hdmi_out_data    )
    );

    wire [23:0] S_ui_rgb;wire S_ui_vs,S_ui_de;
    wire [6:0] S_ui_display_style;
    wire [251:0] S_ui_meter_payload;wire [71:0] S_ui_meter_debug;wire [3:0] S_ui_meter_flags;
    wire [1:0] S_ui_ref_mode;
    wire [15:0] S_ui_ref_psi;
    wire S_ui_ref_valid;
    wire S_ui_meter_estimated,S_ui_psi_valid,S_ui_hard_fault;
    wire [31:0] S_ui_age_loc,S_ui_age_geo,S_ui_age_read,S_ui_psi_source;
    wire [15:0] S_ui_psi;
    wire [23:0] S_hdmi_diagnostic_data;
    // Production slim: omit the eight-cell diagnostic overlay; no pixel delay.
    // The independent clean candidate retains the complete debug view.
    assign S_hdmi_diagnostic_data=S_hdmi_out_data;

    // Mirror the existing mixer's data1d/data2d/output three registered edges.
    // Original mixer and all video-control signals remain byte-for-byte intact.
    always @(posedge S_hdmi_pixel_clk or negedge S_hdmi_rst_n) begin
      if(!S_hdmi_rst_n)begin S_lf_good_pipe<=0;S_lf_bad_pipe<=7'b1111111;end
      else begin S_lf_good_pipe<={S_lf_good_pipe[5:0],S_lf_read_good};
                 S_lf_bad_pipe<={S_lf_bad_pipe[5:0],S_lf_read_bad};end
    end
    t06_latency_frame_core u_latency_frame(
      .time_clk(S_100m_clk),.time_rst_n(S_lp_rst_n),
      .csi_clk(S_csi_rx_clk),.csi_rst_n(S_t06_rst_n),
      .raw_frame_start(S_raw_tuser),.raw_valid(S_raw_tvalid),
      .isp_frame_start(S_ISP_O_tuser),.isp_valid(S_ISP_O_tvalid),.isp_sof_aligned(S_t06_sof_aligned),
      .ddr_clk(S_ddr_clk),.ddr_rst_n(S_ddr_run_rst_n),
      .frame_boundary(S_fb_boundary),.frame_good(S_fb_good),
      .write_bank(S_fb_write_bank),.latest_bank(S_video_out_rp),
      .latest_valid(S_fb_latest_valid),.frame_acquire(S_fb_acquire),
      .hdmi_clk(S_hdmi_pixel_clk),.hdmi_rst_n(S_hdmi_rst_n),
      .display_frame_start(~S_ui_vs),.final_de(S_ui_de),
      .final_source_valid(S_lf_good_pipe[6]),.final_frame_bad(S_lf_bad_pipe[6]),
      .camera_display_style(S_t06_display_style),.display_style(S_ui_display_style),
      .measure_pulse(S_lf_measure),.status(S_lf_status),.source_frame_id(S_lf_id),
      .capture_us(S_lf_capture_us),.display_us(S_lf_display_us),.latency_us(S_lf_latency_us),
      .new_frames(S_lf_new),.repeat_frames(S_lf_repeat),.skipped_source_frames(S_lf_skip),
      .invalid_displays(S_lf_invalid),.stale_displays(S_lf_stale),.partial_displays(S_lf_partial),
      .captured_frames(S_lf_captured),.committed_frames(S_lf_committed),
      .dropped_frames(S_lf_dropped),.bad_metadata_frames(S_lf_metadata_bad),
      .current_frame_bad(S_lf_current_bad),.source_metadata_fault(S_lf_source_fault),
      .display_metadata_fault(S_lf_display_fault),
      .csi_source_id(S_motion_source_id),.csi_source_valid(S_motion_source_valid)
    );
    assign S_lf_rgb=S_hdmi_diagnostic_data;

    // MOT15 is a read-only side branch. Common session reset prevents ID reuse.
    t06_motion_link #(.ENABLE_SHARED_ANALYSIS(1)) u_motion(
      .csi_clk(S_csi_rx_clk),.hdmi_clk(S_hdmi_pixel_clk),
      .arst_n(S_t06_rst_n&S_ddr_run_rst_n&S_hdmi_rst_n&S_lp_rst_n),
      .rgb4(S_analysis_rgb4),.gray4(S_motion_gray4),.gray_valid(S_motion_gray_valid),
      .gray_sof(S_motion_gray_sof),.gray_eol(S_motion_gray_eol),
      .frame_error(S_rx_frame_error|S_motion_abort),
      .source_id(S_motion_source_id),.source_id_valid(S_motion_source_valid),
      .vs(S_hdmi_out_vsync),.measure_pulse(S_lf_measure),.display_id(S_lf_id),
      .display_good((S_lf_status==1||S_lf_status==2)&&!S_lf_current_bad&&
                    !S_lf_source_fault&&!S_lf_display_fault),
      .state(S_motion_state),.stable(S_motion_stable),.changed(S_motion_changed),
      .events(S_motion_events),.xmin(S_motion_xmin),.xmax(S_motion_xmax),
      .ymin(S_motion_ymin),.ymax(S_motion_ymax),.result_valid(S_motion_valid),
       .analysis_valid(S_analysis_valid),.analysis_rgb_sig(S_analysis_rgb_sig),.analysis_gray_sig(S_analysis_gray_sig));
    // Existing transport raster places source pixel0 at final x2; preserve the
    // video phase and compensate only this passive rectangle, clipped to raster.
    t06_motion_osd #(.SOURCE_X_OFFSET(2),.ENABLE_ANALYSIS_PANEL(1),.SHOW_TEXT(0)) u_motion_osd(
      .clk(S_hdmi_pixel_clk),.rst_n(S_hdmi_rst_n),.vs(S_hdmi_out_vsync),
      .de(S_hdmi_out_de),.rgb(S_lf_rgb),.state(S_motion_state),
      .stable(S_motion_stable),.result_valid(S_motion_valid),.changed(S_motion_changed),
      .events(S_motion_events),.xmin(S_motion_xmin),.xmax(S_motion_xmax),
      .ymin(S_motion_ymin),.ymax(S_motion_ymax),
       .analysis_valid(S_analysis_valid),.analysis_rgb_sig(S_analysis_rgb_sig),.analysis_gray_sig(S_analysis_gray_sig),.out_rgb(S_motion_rgb));

    assign S_quality_rgb=S_motion_rgb;
    // Isolated static/frontal bench test only. Original video path is parallel.
    wire [23:0] S_pair_rgb;wire S_pair_vs,S_pair_de;
    // Independent hard-MCU platform. Video recovery revokes ROI access;
    // it never resets the CPU/slot ownership behind a running AHB master.
    wire S_mcu_core50,S_mcu_timer25,S_mcu_pll_lock,S_mcu_ahb_clk;
    wire S_mcu_arst_n=I_rst_n&S_pll_lock&S_mcu_pll_lock;
    (* ASYNC_REG="TRUE" *) reg [7:0] S_mcu_release;
    always @(posedge S_mcu_core50 or negedge S_mcu_arst_n)
      if(!S_mcu_arst_n)S_mcu_release<=0;else S_mcu_release<={S_mcu_release[6:0],1'b1};
    wire [30:0] S_mcu_haddr;wire [1:0] S_mcu_htrans,S_mcu_hresp;
    wire S_mcu_hwrite,S_mcu_hready;wire [2:0] S_mcu_hsize;
    wire [31:0] S_mcu_hwdata,S_mcu_hrdata;
    mroi_pll u_mcu_clocks(.refclk(I_sys_clk),.clk0_out(S_mcu_core50),.clk1_out(S_mcu_timer25),
      .lock(S_mcu_pll_lock),.reset(!I_rst_n));
    // Independent immutable bootROM. This slave runs before video/ROI ARM.
    wire [31:0] S_roi_hrdata;wire [1:0] S_roi_hresp,S_roi_htrans;wire S_roi_hready;
    meter_mcu_bootrom_ahb #(.BASE(31'h20000000),.ROM_FILE("C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_coldboot_20261101/project/user_source/hdl_source/boot_rom/bootrom.mem")) u_mcu_bootrom(
      .clk(S_mcu_ahb_clk),.arst_n(S_mcu_release[1]),.haddr(S_mcu_haddr),.htrans(S_mcu_htrans),
      .hwrite(S_mcu_hwrite),.hsize(S_mcu_hsize),.mmio_hrdata(S_roi_hrdata),.mmio_hresp(S_roi_hresp),
      .mmio_hready(S_roi_hready),.mmio_htrans(S_roi_htrans),.hrdata(S_mcu_hrdata),
      .hresp(S_mcu_hresp),.hready(S_mcu_hready));
    mcu_roi50 u_mcu_processor(.core_sysrst(),.ahb_clk(S_mcu_ahb_clk),.htrans(S_mcu_htrans),
      .hwrite(S_mcu_hwrite),.haddr(S_mcu_haddr),.hsize(S_mcu_hsize),.hburst(),.hprot(),.hmastlock(),
      .hwdata(S_mcu_hwdata),.hrdata(S_mcu_hrdata),.hresp(S_mcu_hresp),.hready(S_mcu_hready),
      .core_clk(S_mcu_core50),.timer_clk(S_mcu_timer25),.core_reset(!S_mcu_release[7]),
      .por_reset(!S_mcu_release[7]),.nmi(1'b0),.clic_irq(23'd0));
    t06_meter_pair_link #(
      .PAIR_FILE("C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native/project/user_source/hdl_source/meter_pair/pair_base_rom.mem"),
      .TRIG_FILE("C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native/project/user_source/hdl_source/meter_pair/needle_trig128.hex"),
      .STATIC_FRONTAL_BENCH(1),.ENABLE_REFERENCE(1),.REFERENCE_DEBOUNCE_CYCLES(1500000)) u_meter_pair(
       .preset_sw(I_preset_sw),
      .mcu_clk(S_mcu_ahb_clk),.mcu_arst_n(S_mcu_arst_n),
      .mcu_haddr(S_mcu_haddr),.mcu_htrans(S_roi_htrans),.mcu_hwrite(S_mcu_hwrite),
      .mcu_hsize(S_mcu_hsize),.mcu_hwdata(S_mcu_hwdata),.mcu_hrdata(S_roi_hrdata),
      .mcu_hresp(S_roi_hresp),.mcu_hready(S_roi_hready),
      .csi_clk(S_csi_rx_clk),.hdmi_clk(S_hdmi_pixel_clk),
      .arst_n(S_t06_rst_n&S_ddr_run_rst_n&S_hdmi_rst_n&S_lp_rst_n),
      .gray4(S_motion_gray4),.gray_valid(S_motion_gray_valid),.gray_sof(S_motion_gray_sof),.gray_eol(S_motion_gray_eol),
      .frame_error(S_rx_frame_error|S_motion_abort),.source_id(S_motion_source_id),.source_valid(S_motion_source_valid),
      .vs(S_hdmi_out_vsync),.de(S_hdmi_out_de),.rgb(S_quality_rgb),
      .display_id_valid(S_lf_measure),.display_source_id(S_lf_id),
      .display_good((S_lf_status==1||S_lf_status==2)&&!S_lf_current_bad&&!S_lf_source_fault&&!S_lf_display_fault),
      .display_fault(S_lf_current_bad|S_lf_source_fault|S_lf_display_fault),
      .analysis_fault(S_lf_source_fault),
      .out_rgb(S_pair_rgb),.out_vs(S_pair_vs),.out_de(S_pair_de),
      .segment_n(O_meter_segment_n),.digit_select_n(O_meter_digit_n),
       .ui_payload(S_ui_meter_payload),.ui_debug(S_ui_meter_debug),.ui_flags(S_ui_meter_flags),.ui_estimated(S_ui_meter_estimated),
       .ui_age_loc(S_ui_age_loc),.ui_age_geo(S_ui_age_geo),.ui_age_read(S_ui_age_read),
       .ui_psi(S_ui_psi),.ui_psi_valid(S_ui_psi_valid),.ui_psi_source(S_ui_psi_source),.ui_hard_fault(S_ui_hard_fault),
        .ui_ref_mode(S_ui_ref_mode),.ui_ref_valid(S_ui_ref_valid),.ui_ref_psi(S_ui_ref_psi));
    t06_hdmi_dashboard #(.TEXT_FILE("C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_landmark_s3_20261103/project/user_source/hdl_source/ui/ui_text.mem"),.FONT_FILE("C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_landmark_s3_20261103/project/user_source/hdl_source/ui/ui_font.mem")) u_dashboard(
       .clk(S_hdmi_pixel_clk),.rst_n(S_hdmi_rst_n),.vs(S_pair_vs),.de(S_pair_de),.rgb(S_pair_rgb),
       .mode(S_ui_display_style[4:0]),.sat(S_ui_display_style[6:5]),
       .meter_payload(S_ui_meter_payload),.meter_debug(S_ui_meter_debug),.meter_show(S_ui_meter_flags),.estimated(S_ui_meter_estimated),
        .ref_mode(S_ui_ref_mode),.ref_valid(S_ui_ref_valid),.ref_psi(S_ui_ref_psi),
       .age_loc(S_ui_age_loc),.age_geo(S_ui_age_geo),.age_read(S_ui_age_read),
       .psi_hundredths(S_ui_psi),.psi_display_valid(S_ui_psi_valid),.psi_source_id(S_ui_psi_source),.hard_fault(S_ui_hard_fault),
       .lf_status(S_lf_status),.lf_source(S_lf_id),.lf_latency(S_lf_latency_us),
       .lf_metadata_fault({S_lf_display_fault,S_lf_source_fault}),.lf_bad(S_lf_current_bad),
       .lf_valid((S_lf_status==1||S_lf_status==2)&&!S_lf_current_bad&&!S_lf_source_fault&&!S_lf_display_fault),
       .mot_state(S_motion_state),.mot_stable(S_motion_stable),.mot_valid(S_motion_valid),
       .mot_changed(S_motion_changed),.mot_events(S_motion_events),
       .a4_valid(S_analysis_valid),.a4_rgb(S_analysis_rgb_sig),.a4_gray(S_analysis_gray_sig),
       .aq_valid(S_aq_hdmi_valid),.aq_payload(S_aq_hdmi_payload),.out_vs(S_ui_vs),.out_de(S_ui_de),.out_rgb(S_ui_rgb));
    hdmi_tx u_hdmi_tx(
        .I_pixel_clk        ( S_hdmi_pixel_clk  ),
        .I_serial_clk       ( S_hdmi_serial_clk ),
        .I_rst              ( ~S_hdmi_rst_n     ),
        .I_key_in           ( 1'b0              ),
        .I_edid_read_trig   ( 1'b0              ),
        .O_edid_read_valid  (                   ),
        .O_edid_read_data   (                   ),
        .I_video_rgb_enable ( 1'b1              ),
        .I_video_in_vs      ( S_ui_vs  ),
        .I_video_in_de      ( S_ui_de  ),
        .I_video_in_user    ( 1'b0              ),
        .I_video_in_valid   ( 1'b0              ),
        .I_video_in_last    ( 1'b0              ),
        .O_video_in_ready   (                   ),
        .I_video_in_data    ( S_ui_rgb   ),
        .I_audio_valid      ( 1'b0              ),
        .I_audio_left_data  ( 24'd0             ),
        .I_audio_right_data ( 24'd0             ),
        .I_i2s_BCLK         ( 1'b0              ),
        .I_i2s_LRCK         ( 1'b0              ),
        .I_i2s_DOUT         ( 1'b0              ),
        .O_ddc_scl          (                   ),
        .O_hdmi_clk_p       (                   ),
        .O_hdmi_tx_p        (                   ),
        .O_tmds_ch0_p       ( O_tmds_ch0_p      ),
        .O_tmds_ch1_p       ( O_tmds_ch1_p      ),
        .O_tmds_ch2_p       ( O_tmds_ch2_p      ),
        .O_tmds_clk_p       ( O_tmds_clk_p      )
    );


    
endmodule
