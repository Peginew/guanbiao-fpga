// LF14: passive final-HDMI overlay. All telemetry inputs already belong to clk.
// No RGB/control register, divider, multiplier, RAM, external pin or new domain.
// VS is positive; metadata is sampled on its positive edge and held for one raster.
module t06_latency_frame_osd #(
    parameter ENABLE = 1,
    parameter SHOW_DETAIL_LINES = 1
)(
    input wire clk,
    input wire rst_n,
    input wire vs,
    input wire de,
    input wire [23:0] rgb,
    input wire [1:0] status,
    input wire [31:0] source_frame_id,
    input wire [31:0] latency_us,
    input wire [31:0] captured_frames,
    input wire [31:0] new_frames,
    input wire [31:0] repeat_frames,
    input wire [31:0] skipped_source_frames,
    input wire [31:0] invalid_displays,
    input wire [31:0] stale_displays,
    input wire [31:0] committed_frames,
    input wire [31:0] dropped_frames,
    input wire [31:0] bad_metadata_frames,
    input wire [31:0] partial_displays,
    input wire source_metadata_fault,
    input wire display_metadata_fault,
    input wire current_frame_bad,
    output wire [23:0] out_rgb
);
    reg de_prev, vs_prev;
    reg [10:0] raster_x, raster_y;
    reg [31:0] frame_number;
    reg [1:0] snap_status;
    reg [31:0] snap_source, snap_latency, snap_captured;
    reg [31:0] snap_new, snap_repeat, snap_skip;
    reg [31:0] snap_invalid, snap_stale, snap_commit, snap_drop;
    reg [31:0] snap_metadata, snap_partial;
    reg snap_source_fault, snap_display_fault, snap_bad;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            de_prev <= 0; vs_prev <= 0; raster_x <= 0; raster_y <= 0;
            frame_number <= 0; snap_status <= 0;
            snap_source <= 0; snap_latency <= 0; snap_captured <= 0;
            snap_new <= 0; snap_repeat <= 0; snap_skip <= 0;
            snap_invalid <= 0; snap_stale <= 0; snap_commit <= 0; snap_drop <= 0;
            snap_metadata <= 0; snap_partial <= 0;
            snap_source_fault <= 0; snap_display_fault <= 0; snap_bad <= 0;
        end else begin
            de_prev <= de; vs_prev <= vs;
            if (vs && !vs_prev) begin
                raster_x <= 0; raster_y <= 0;
                frame_number <= frame_number + 1'b1;
                snap_status <= status;
                snap_source <= source_frame_id; snap_latency <= latency_us;
                snap_captured <= captured_frames;
                snap_new <= new_frames; snap_repeat <= repeat_frames;
                snap_skip <= skipped_source_frames; snap_invalid <= invalid_displays;
                snap_stale <= stale_displays; snap_commit <= committed_frames;
                snap_drop <= dropped_frames; snap_metadata <= bad_metadata_frames;
                snap_partial <= partial_displays;
                snap_source_fault <= source_metadata_fault;
                snap_display_fault <= display_metadata_fault;
                snap_bad <= current_frame_bad;
            end else begin
                // Counter consumes the previous registered final-HDMI clock slot.
                // The current combinational RGB slot therefore retains pixel 0 at x=0.
                if (!de) raster_x <= 0;
                else if (raster_x != 11'h7ff) raster_x <= raster_x + 1'b1;
                if (de_prev && !de && raster_y != 11'h7ff)
                    raster_y <= raster_y + 1'b1;
            end
        end
    end

    // A glyph is 5x7, placed at x=1..5 in an 8x16 cell, with 2 vertical pixels per row.
    // Codes 0..15 are hexadecimal; the other codes are constant labels only.
    localparam G_SPACE=6'd16, G_L=6'd17, G_S=6'd18, G_N=6'd19,
               G_R=6'd20, G_K=6'd21, G_X=6'd22, G_I=6'd23,
               G_T=6'd24, G_P=6'd25, G_M=6'd26, G_V=6'd27,
               G_W=6'd28, G_EQ=6'd29, G_H=6'd30, G_U=6'd31;
    function [34:0] glyph;
        input [5:0] ch;
        begin
            case (ch)
                0:glyph={5'b01110,5'b10001,5'b10011,5'b10101,5'b11001,5'b10001,5'b01110};
                1:glyph={5'b00100,5'b01100,5'b00100,5'b00100,5'b00100,5'b00100,5'b01110};
                2:glyph={5'b01110,5'b10001,5'b00001,5'b00010,5'b00100,5'b01000,5'b11111};
                3:glyph={5'b11110,5'b00001,5'b00001,5'b01110,5'b00001,5'b00001,5'b11110};
                4:glyph={5'b00010,5'b00110,5'b01010,5'b10010,5'b11111,5'b00010,5'b00010};
                5:glyph={5'b11111,5'b10000,5'b10000,5'b11110,5'b00001,5'b00001,5'b11110};
                6:glyph={5'b01110,5'b10000,5'b10000,5'b11110,5'b10001,5'b10001,5'b01110};
                7:glyph={5'b11111,5'b00001,5'b00010,5'b00100,5'b01000,5'b01000,5'b01000};
                8:glyph={5'b01110,5'b10001,5'b10001,5'b01110,5'b10001,5'b10001,5'b01110};
                9:glyph={5'b01110,5'b10001,5'b10001,5'b01111,5'b00001,5'b00001,5'b01110};
                10:glyph={5'b01110,5'b10001,5'b10001,5'b11111,5'b10001,5'b10001,5'b10001};
                11:glyph={5'b11110,5'b10001,5'b10001,5'b11110,5'b10001,5'b10001,5'b11110};
                12:glyph={5'b01111,5'b10000,5'b10000,5'b10000,5'b10000,5'b10000,5'b01111};
                13:glyph={5'b11110,5'b10001,5'b10001,5'b10001,5'b10001,5'b10001,5'b11110};
                14:glyph={5'b11111,5'b10000,5'b10000,5'b11110,5'b10000,5'b10000,5'b11111};
                15:glyph={5'b11111,5'b10000,5'b10000,5'b11110,5'b10000,5'b10000,5'b10000};
                G_L:glyph={5'b10000,5'b10000,5'b10000,5'b10000,5'b10000,5'b10000,5'b11111};
                G_S:glyph={5'b01111,5'b10000,5'b10000,5'b01110,5'b00001,5'b00001,5'b11110};
                G_N:glyph={5'b10001,5'b11001,5'b10101,5'b10011,5'b10001,5'b10001,5'b10001};
                G_R:glyph={5'b11110,5'b10001,5'b10001,5'b11110,5'b10100,5'b10010,5'b10001};
                G_K:glyph={5'b10001,5'b10010,5'b10100,5'b11000,5'b10100,5'b10010,5'b10001};
                G_X:glyph={5'b10001,5'b10001,5'b01010,5'b00100,5'b01010,5'b10001,5'b10001};
                G_I:glyph={5'b01110,5'b00100,5'b00100,5'b00100,5'b00100,5'b00100,5'b01110};
                G_T:glyph={5'b11111,5'b00100,5'b00100,5'b00100,5'b00100,5'b00100,5'b00100};
                G_P:glyph={5'b11110,5'b10001,5'b10001,5'b11110,5'b10000,5'b10000,5'b10000};
                G_M:glyph={5'b10001,5'b11011,5'b10101,5'b10101,5'b10001,5'b10001,5'b10001};
                G_V:glyph={5'b10001,5'b10001,5'b10001,5'b10001,5'b10001,5'b01010,5'b00100};
                G_W:glyph={5'b10001,5'b10001,5'b10001,5'b10101,5'b10101,5'b11011,5'b10001};
                G_EQ:glyph={5'b00000,5'b00000,5'b11111,5'b00000,5'b11111,5'b00000,5'b00000};
                G_H:glyph={5'b10001,5'b10001,5'b10001,5'b11111,5'b10001,5'b10001,5'b10001};
                G_U:glyph={5'b10001,5'b10001,5'b10001,5'b10001,5'b10001,5'b10001,5'b01110};
                default:glyph=35'd0;
            endcase
        end
    endfunction

    wire in_panel = de && raster_x>=11'd704 && raster_x<11'd1216 &&
                    raster_y>=11'd48 && raster_y<(SHOW_DETAIL_LINES ? 11'd96 : 11'd64);
    wire [8:0] panel_x = raster_x - 11'd704;
    wire [5:0] panel_y = raster_y - 11'd48;
    wire [5:0] column = panel_x[8:3];
    wire [1:0] text_row = panel_y[5:4];
    wire [2:0] font_row = panel_y[3:1];
    wire [2:0] font_col = panel_x[2:0];
    reg [5:0] character;
    reg [31:0] field;
    reg [2:0] digit;
    reg is_digit;
    reg [4:0] row_bits;
    wire [34:0] pixels = glyph(character);
    wire live_snapshot = (snap_status==1 || snap_status==2) &&
                         !snap_source_fault && !snap_display_fault && !snap_bad;

    always @* begin
        character=G_SPACE; field=0; digit=0; is_digit=0;
        if (text_row==0) begin
            case (column)
                0:character=G_L; 1:character=15; 2:character=1; 3:character=4;
                5:character=G_H; 7:character=G_U; 8:character=G_S;
                10:character=G_L; 11:character=G_EQ;
                21:character=G_S; 22:character=G_EQ;
                32:character=15; 33:character=G_EQ;
                51:character=14; 52:character=G_EQ;
                53:character={4'd0,snap_display_fault,snap_source_fault};
                55:character=11; 56:character=G_EQ; 57:character={5'd0,snap_bad};
                59:character=G_V; 60:character=G_EQ; 61:character={5'd0,live_snapshot};
                default:begin end
            endcase
            if (column>=12 && column<=19) begin field=snap_latency; digit=column-12; is_digit=1; end
            if (column>=23 && column<=30) begin field=snap_source; digit=column-23; is_digit=1; end
            if (column>=34 && column<=41) begin field=frame_number; digit=column-34; is_digit=1; end
            if (column>=43 && column<=49) begin
                case (snap_status)
                    0:case(column)
                        43:character=G_I;44:character=G_N;45:character=G_V;46:character=10;
                        47:character=G_L;48:character=G_I;49:character=13;
                        default:character=G_SPACE;
                      endcase
                    1:case(column)
                        43:character=G_N;44:character=14;45:character=G_W;
                        default:character=G_SPACE;
                      endcase
                    2:case(column)
                        43:character=G_R;44:character=14;45:character=G_P;46:character=14;
                        47:character=10;48:character=G_T;
                        default:character=G_SPACE;
                      endcase
                    3:case(column)
                        43:character=G_S;44:character=G_T;45:character=10;46:character=G_L;47:character=14;
                        default:character=G_SPACE;
                      endcase
                endcase
            end
        end else if (SHOW_DETAIL_LINES) begin
            // Five fields per line, each 10 characters plus one separator.
            if (column<=9) begin
                if(column==0)character=(text_row==1)?G_N:G_I;
                else if(column==1)character=G_EQ;
                else begin field=(text_row==1)?snap_new:snap_invalid;digit=column-2;is_digit=1;end
            end else if(column>=11 && column<=20)begin
                if(column==11)character=(text_row==1)?G_R:G_T;
                else if(column==12)character=G_EQ;
                else begin field=(text_row==1)?snap_repeat:snap_stale;digit=column-13;is_digit=1;end
            end else if(column>=22 && column<=31)begin
                if(column==22)character=(text_row==1)?G_K:G_P;
                else if(column==23)character=G_EQ;
                else begin field=(text_row==1)?snap_skip:snap_partial;digit=column-24;is_digit=1;end
            end else if(column>=33 && column<=42)begin
                if(column==33)character=(text_row==1)?6'd12:G_M;
                else if(column==34)character=G_EQ;
                else begin field=(text_row==1)?snap_commit:snap_metadata;digit=column-35;is_digit=1;end
            end else if(column>=44 && column<=53)begin
                if(column==44)character=(text_row==1)?G_X:6'd10;
                else if(column==45)character=G_EQ;
                else begin field=(text_row==1)?snap_drop:snap_captured;digit=column-46;is_digit=1;end
            end
        end
        if(is_digit)begin
            // Constant-width nibble mux: no decimal conversion or non-power-of-two division.
            case(digit)
                0:character={2'd0,field[31:28]};1:character={2'd0,field[27:24]};
                2:character={2'd0,field[23:20]};3:character={2'd0,field[19:16]};
                4:character={2'd0,field[15:12]};5:character={2'd0,field[11:8]};
                6:character={2'd0,field[7:4]};7:character={2'd0,field[3:0]};
            endcase
        end
        case(font_row)
            0:row_bits=pixels[34:30];1:row_bits=pixels[29:25];2:row_bits=pixels[24:20];
            3:row_bits=pixels[19:15];4:row_bits=pixels[14:10];5:row_bits=pixels[9:5];
            6:row_bits=pixels[4:0];default:row_bits=0;
        endcase
    end

    wire ink = (font_col>=1 && font_col<=5) && row_bits[5-font_col];
    wire [23:0] state_color = (snap_source_fault || snap_display_fault || snap_bad) ? 24'hff6060 :
                             (snap_status==1) ? 24'h60ff80 :
                             (snap_status==2) ? 24'hffe060 :
                             (snap_status==3) ? 24'hffb060 : 24'hb0b0b0;
    wire state_cell = text_row==0 && column>=43 && column<=61;
    wire [23:0] ink_color = state_cell ? state_color : 24'he0f0ff;
    assign out_rgb = (ENABLE && in_panel) ? (ink ? ink_color : 24'h081018) : rgb;
endmodule
