`timescale 1ns/1ps
// Bounded software candidate. Thresholds are development defaults, not sensor calibration.
// Statistics are measured before AWB/OSD. Never gates or resets the video path.
module t06_auto_exposure #(
    parameter integer ENABLE_AUTO = 1,
    parameter integer I2C_TIMEOUT_CYCLES = 12000000,
    parameter integer STALE_CYCLES = 24000000,
    parameter integer SETTLE_FRAMES = 3
) (
    input wire I_src_clk, input wire I_dst_clk, input wire I_arst_n,
    input wire I_stats_valid, input wire I_stats_good,
    input wire [31:0] I_frame_id,
    input wire [23:0] I_y_sum,
    input wire [15:0] I_sample_count, I_dark_count, I_bright_count,
    input wire [15:0] I_global_count, I_global_bright,
    input wire I_awb_stable, I_awb_confident,
    input wire [11:0] I_awb_r_gain, I_awb_b_gain,
    input wire I_cam_cfg_done, I_ae_cfg_done, I_iic_error,
    output reg O_ae_req,
    output reg [15:0] O_ae, O_ag,
    output reg [3:0] O_state,
    output reg O_stable, O_fault,
    output wire O_stats_busy,
    output wire [31:0] O_stats_dropped,
    output reg [31:0] O_last_frame_id,
    output reg [23:0] O_last_y_sum,
    output reg [15:0] O_last_sample_count, O_last_dark_count, O_last_bright_count,
    output reg O_last_awb_stable, O_last_awb_confident,
    output reg [11:0] O_last_awb_r_gain, O_last_awb_b_gain
);
    function integer bits_for;
        input integer n; integer v;
        begin v=n-1; bits_for=1; while(v>1) begin v=v>>1; bits_for=bits_for+1; end end
    endfunction
    localparam integer TW=bits_for(I2C_TIMEOUT_CYCLES);
    localparam integer SW=bits_for(STALE_CYCLES);
    localparam [3:0] ST_INIT=0, ST_WAIT_BUSY=1, ST_WAIT_DONE=2,
                     ST_SETTLE=3, ST_AUTO=4, ST_FAULT=15;
    (* ASYNC_REG="TRUE" *) reg [1:0] rst_dst_ff;
    always @(posedge I_dst_clk or negedge I_arst_n)
        if(!I_arst_n) rst_dst_ff<=0; else rst_dst_ff<={rst_dst_ff[0],1'b1};
    wire dst_rst_n=rst_dst_ff[1];
    wire [162:0] stats_payload;
    wire stats_valid;
    t06_quality_mailbox #(.WIDTH(163)) u_stats_mailbox (
        .I_arst_n(I_arst_n), .I_src_clk(I_src_clk), .I_src_valid(I_stats_valid),
        .I_src_payload({I_frame_id,I_y_sum,I_sample_count,I_dark_count,I_bright_count,
                        I_global_count,I_global_bright,I_stats_good,I_awb_stable,
                        I_awb_confident,I_awb_r_gain,I_awb_b_gain}),
        .O_src_busy(O_stats_busy), .O_src_dropped(O_stats_dropped),
        .I_dst_clk(I_dst_clk), .O_dst_valid(stats_valid), .O_dst_payload(stats_payload)
    );
    wire [31:0] frame_id;
    wire [23:0] ysum;
    wire [15:0] ns,nd,nb,ng,ngb;
    wire good,awb_stable,awb_confident;
    wire [11:0] awb_r,awb_b;
    assign {frame_id,ysum,ns,nd,nb,ng,ngb,good,awb_stable,awb_confident,awb_r,awb_b}=stats_payload;
    reg have_frame;
    reg [TW-1:0] wait_count;
    reg [SW-1:0] stale_count;
    reg [7:0] settle_left;
    reg [1:0] stable_frames;
    wire [31:0] frame_delta=frame_id-O_last_frame_id;
    wire newer_frame=!have_frame || ((frame_delta!=0) && !frame_delta[31]);
    wire [23:0] max_sum=({8'd0,ns}<<8)-{8'd0,ns};
    wire [16:0] classified={1'b0,nd}+{1'b0,nb};
    wire measurement_ok=good && (ns!=0) && (ng!=0) && (nd<=ns) && (nb<=ns)
                          && (classified<={1'b0,ns}) && (ngb<=ng) && (ysum<=max_sum);
    wire [23:0] lower_sum=({8'd0,ns}<<6)+({8'd0,ns}<<5); // 96*N
    wire [23:0] upper_sum=({8'd0,ns}<<7)+({8'd0,ns}<<4); // 144*N
    wire global_over=({4'd0,ngb}<<4)>{4'd0,ng}; // strictly more than 1/16
    wire too_dark=ysum<lower_sum;
    wire too_bright=(ysum>upper_sum)||global_over;
    wire [15:0] exp_step=(O_ae[15:3]<16)?16:(O_ae>>3);
    wire [16:0] exp_up={1'b0,O_ae}+{1'b0,exp_step};
    wire [15:0] next_ae_up=(exp_up>1991)?16'd1991:exp_up[15:0];
    wire [15:0] next_ae_down=(O_ae>(32+exp_step))?(O_ae-exp_step):16'd32;
    wire [15:0] next_ag_up=(O_ag>=172)?16'd176:O_ag+16'd4;
    wire [15:0] next_ag_down=(O_ag<=20)?16'd16:O_ag-16'd4;

    always @(posedge I_dst_clk or negedge dst_rst_n) begin
        if(!dst_rst_n) begin
            O_ae_req<=0; O_ae<=1991; O_ag<=144; O_state<=ST_INIT;
            O_stable<=0; O_fault<=0; wait_count<=0; stale_count<=0;
            settle_left<=0; stable_frames<=0; have_frame<=0;
            O_last_frame_id<=0; O_last_y_sum<=0; O_last_sample_count<=0;
            O_last_dark_count<=0; O_last_bright_count<=0;
            O_last_awb_stable<=0; O_last_awb_confident<=0;
            O_last_awb_r_gain<=256; O_last_awb_b_gain<=256;
        end else begin
            O_ae_req<=0;
            if(stale_count<STALE_CYCLES-1) stale_count<=stale_count+1'b1;
            else begin O_stable<=0; stable_frames<=0; end

            // A duplicate cannot renew freshness, accumulate convergence or issue a write.
            if(stats_valid && newer_frame) begin
                have_frame<=1; O_last_frame_id<=frame_id;
                O_last_y_sum<=ysum; O_last_sample_count<=ns;
                O_last_dark_count<=nd; O_last_bright_count<=nb;
                O_last_awb_stable<=awb_stable; O_last_awb_confident<=awb_confident;
                O_last_awb_r_gain<=awb_r; O_last_awb_b_gain<=awb_b;
                if(measurement_ok) stale_count<=0;
                else begin O_stable<=0; stable_frames<=0; end
            end

            case(O_state)
                ST_INIT: begin
                    O_stable<=0;
                    if(I_cam_cfg_done && I_ae_cfg_done) begin
                        // Reproduce the previous known-good initial target exactly once.
                        O_ae_req<=1; wait_count<=0; O_state<=ST_WAIT_BUSY;
                    end
                end
                ST_WAIT_BUSY: begin
                    // A high done level is not an acknowledgement of this new request.
                    if(!I_ae_cfg_done) begin wait_count<=0; O_state<=ST_WAIT_DONE; end
                    else if(wait_count==I2C_TIMEOUT_CYCLES-1) begin
                        O_fault<=1; O_stable<=0; O_state<=ST_FAULT;
                    end else wait_count<=wait_count+1'b1;
                end
                ST_WAIT_DONE: begin
                    if(I_ae_cfg_done) begin
                        settle_left<=SETTLE_FRAMES; stable_frames<=0;
                        O_state<=ST_SETTLE; wait_count<=0;
                    end else if(wait_count==I2C_TIMEOUT_CYCLES-1) begin
                        O_fault<=1; O_stable<=0; O_state<=ST_FAULT;
                    end else wait_count<=wait_count+1'b1;
                end
                ST_SETTLE: begin
                    O_stable<=0;
                    if(stats_valid && newer_frame && measurement_ok) begin
                        if(settle_left<=1) begin settle_left<=0; O_state<=ST_AUTO; end
                        else settle_left<=settle_left-1'b1;
                    end
                end
                ST_AUTO: if(stats_valid && newer_frame) begin
                    if(!measurement_ok) begin O_stable<=0; stable_frames<=0; end
                    else if(global_over && too_dark) begin
                        // Conflicting metering goals cannot be solved by exposure:
                        // hold rather than hunting between bright and dark commands.
                        O_stable<=0; stable_frames<=0;
                    end
                    else if(too_bright || too_dark) begin
                        O_stable<=0; stable_frames<=0;
                        // Bright/highlight protection takes priority even if ROI is dark.
                        // Reverse the increase order: gain down before exposure down.
                        if(ENABLE_AUTO && I_cam_cfg_done && I_ae_cfg_done) begin
                            if(too_bright && (O_ag>16 || O_ae>32)) begin
                                if(O_ag>16) O_ag<=next_ag_down; else O_ae<=next_ae_down;
                                O_ae_req<=1; wait_count<=0; O_state<=ST_WAIT_BUSY;
                            end else if(!too_bright && too_dark && (O_ae<1991 || O_ag<176)) begin
                                if(O_ae<1991) O_ae<=next_ae_up; else O_ag<=next_ag_up;
                                O_ae_req<=1; wait_count<=0; O_state<=ST_WAIT_BUSY;
                            end
                        end
                    end else if(awb_stable && awb_confident) begin
                        if(stable_frames<3) stable_frames<=stable_frames+1'b1;
                        if(stable_frames>=2) O_stable<=1;
                    end else begin O_stable<=0; stable_frames<=0; end
                end
                ST_FAULT: begin O_ae_req<=0; O_stable<=0; O_fault<=1; end
                default: begin O_ae_req<=0; O_stable<=0; O_fault<=1; O_state<=ST_FAULT; end
            endcase
            if(I_iic_error) begin
                O_ae_req<=0; O_stable<=0; O_fault<=1; O_state<=ST_FAULT;
            end
        end
    end
endmodule

// One outstanding message, no binary bus synchronizers. Drop new messages while
// busy; held data is immutable until the returned ACK traverses two source flops.
// Both domains MUST share the same asynchronously asserted global reset. The
// independent two-flop release chains avoid relying on clock startup order.
module t06_quality_mailbox #(parameter integer WIDTH=32) (
    input wire I_arst_n, input wire I_src_clk, input wire I_src_valid,
    input wire [WIDTH-1:0] I_src_payload,
    output wire O_src_busy, output reg [31:0] O_src_dropped,
    input wire I_dst_clk, output reg O_dst_valid,
    output wire [WIDTH-1:0] O_dst_payload
);
    (* ASYNC_REG="TRUE" *) reg [1:0] rst_s_ff,rst_d_ff;
    always @(posedge I_src_clk or negedge I_arst_n)
        if(!I_arst_n) rst_s_ff<=0; else rst_s_ff<={rst_s_ff[0],1'b1};
    always @(posedge I_dst_clk or negedge I_arst_n)
        if(!I_arst_n) rst_d_ff<=0; else rst_d_ff<={rst_d_ff[0],1'b1};
    wire src_rst_n=rst_s_ff[1], dst_rst_n=rst_d_ff[1];
    reg [WIDTH-1:0] s_payload_hold;
    reg s_req_toggle,d_ack_toggle;
    (* ASYNC_REG="TRUE" *) reg s_ack_sync1,s_ack_sync2,d_req_sync1,d_req_sync2;
    reg d_settle;
    reg [WIDTH-1:0] d_payload_capture;
    assign O_src_busy=s_req_toggle!=s_ack_sync2;
    assign O_dst_payload=d_payload_capture;
    always @(posedge I_src_clk or negedge src_rst_n) begin
        if(!src_rst_n) begin
            s_payload_hold<=0; s_req_toggle<=0; s_ack_sync1<=0; s_ack_sync2<=0;
            O_src_dropped<=0;
        end else begin
            s_ack_sync1<=d_ack_toggle; s_ack_sync2<=s_ack_sync1;
            if(I_src_valid) begin
                if(!O_src_busy) begin s_payload_hold<=I_src_payload; s_req_toggle<=~s_req_toggle; end
                else if(O_src_dropped!=32'hffffffff) O_src_dropped<=O_src_dropped+1'b1;
            end
        end
    end
    always @(posedge I_dst_clk or negedge dst_rst_n) begin
        if(!dst_rst_n) begin
            d_req_sync1<=0; d_req_sync2<=0; d_ack_toggle<=0; d_settle<=0;
            d_payload_capture<=0; O_dst_valid<=0;
        end else begin
            d_req_sync1<=s_req_toggle; d_req_sync2<=d_req_sync1;
            O_dst_valid<=0;
            if(d_req_sync2!=d_ack_toggle) begin
                if(!d_settle) d_settle<=1;
                else begin
                    d_payload_capture<=s_payload_hold; O_dst_valid<=1;
                    d_ack_toggle<=d_req_sync2; d_settle<=0;
                end
            end else d_settle<=0;
        end
    end
endmodule
