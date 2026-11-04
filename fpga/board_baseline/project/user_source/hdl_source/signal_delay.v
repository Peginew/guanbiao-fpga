// Fixed clock delay for the native four-pixel RGB stream.
// Uses the existing generated 96-bit DP RAM (NOREG, synchronous read).
// Valid bubbles and back-to-back rows are preserved instead of rebuilding
// a 320-clock read window from an input pixel counter.
module signal_delay #(
    parameter IMG_HEIGHT = 1080,
    parameter IMG_WIDTH = 1920,
    parameter DATA_WIDTH = 96,
    parameter DELAY_CYCLE = 50
)(
    input wire I_clk, I_rst_n, I_tuser, I_valid,
    input wire [DATA_WIDTH-1:0] I_data,
    output wire O_valid,
    output wire [DATA_WIDTH-1:0] O_data,
    output wire O_tuser
);
    // Limited to the supplied native 96-bit RAM and 2..64 clocks.
    // Current AWB instantiates 96/50. 64 slots use low6 of the11-bit port.
    localparam [5:0] READ_OFFSET = DELAY_CYCLE-1;
    reg [5:0] write_slot;
    reg [DELAY_CYCLE-1:0] valid_pipe, sof_pipe;
    wire [5:0] active_write_slot = I_tuser ? 6'd0 : write_slot;
    wire [5:0] read_slot = active_write_slot - READ_OFFSET;
    wire [95:0] ram_rgb;
    (* keep = "true" *) reg sof_discarded_pending;
    always @(posedge I_clk or negedge I_rst_n) begin
        if(!I_rst_n) begin
            write_slot <= 0; valid_pipe <= 0; sof_pipe <= 0;
            sof_discarded_pending <= 0;
        end else if(I_tuser) begin
            // A legal new early SOF follows drainage of the prior frame tail.
            // Early overlap discards pending samples; frame-count/protocol
            // checks must reject the old incomplete frame, never publish it.
            if(|valid_pipe) sof_discarded_pending <= 1'b1;
            write_slot <= 6'd1;
            valid_pipe <= {{(DELAY_CYCLE-1){1'b0}},I_valid};
            sof_pipe <= {{(DELAY_CYCLE-1){1'b0}},1'b1};
        end else begin
            write_slot <= write_slot + 1'b1;
            valid_pipe <= {valid_pipe[DELAY_CYCLE-2:0],I_valid};
            sof_pipe <= {sof_pipe[DELAY_CYCLE-2:0],1'b0};
        end
    end
    assign O_valid = valid_pipe[DELAY_CYCLE-1];
    assign O_data = O_valid ? ram_rgb : {DATA_WIDTH{1'b0}};
    // Auxiliary delayed pulse. Current AWB retains external O_tuser=I_tuser;
    // it does not output this delayed pulse.
    assign O_tuser = sof_pipe[DELAY_CYCLE-1];
    blk_mem_gen_awb_delay_signal u_rgb_delay_ram (
        .clka(I_clk), .wea(I_rst_n && I_valid),
        .addra({5'd0,active_write_slot}), .dia(I_data), .doa(),
        .clkb(I_clk), .addrb({5'd0,read_slot}),
        .web(1'b0), .dib(96'd0), .dob(ram_rgb)
    );
endmodule
