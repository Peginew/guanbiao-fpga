// Exact endpoint-preserving projection of the existing 160x160 logo.
// 92x92, original 25-bit alpha/RGB colors; 2394 row-envelope byte indexes.
// Two synchronous ROM stages: input coordinates at edge N -> output at N+1.
// Two 2048x8 index banks plus one 512x25 palette; no image/frame RAM.
module t06_ui_logo_rom #(
 parameter INDEX0_INIT_FILE="C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_landmark_s3_20261103/project/user_source/hdl_source/ui/ui_logo_index0.dath",
 parameter INDEX1_INIT_FILE="C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_landmark_s3_20261103/project/user_source/hdl_source/ui/ui_logo_index1.dath",
 parameter PALETTE_INIT_FILE="C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_landmark_s3_20261103/project/user_source/hdl_source/ui/ui_logo_palette.dath"
)(input wire I_clk,input wire [6:0] I_local_x,I_local_y,output wire [24:0] O_pixel);
 reg [26:0] descriptor;
 always @* begin
  case(I_local_y)
   7'd20:descriptor={1'b1,7'd31,7'd87,12'd0};
   7'd21:descriptor={1'b1,7'd31,7'd86,12'd57};
   7'd22:descriptor={1'b1,7'd30,7'd86,12'd113};
   7'd23:descriptor={1'b1,7'd30,7'd33,12'd170};
   7'd24:descriptor={1'b1,7'd29,7'd33,12'd174};
   7'd25:descriptor={1'b1,7'd29,7'd34,12'd179};
   7'd26:descriptor={1'b1,7'd28,7'd84,12'd185};
   7'd27:descriptor={1'b1,7'd27,7'd84,12'd242};
   7'd28:descriptor={1'b1,7'd27,7'd83,12'd300};
   7'd29:descriptor={1'b1,7'd27,7'd82,12'd357};
   7'd30:descriptor={1'b1,7'd26,7'd36,12'd413};
   7'd31:descriptor={1'b1,7'd26,7'd37,12'd424};
   7'd32:descriptor={1'b1,7'd25,7'd37,12'd436};
   7'd33:descriptor={1'b1,7'd25,7'd81,12'd449};
   7'd34:descriptor={1'b1,7'd24,7'd80,12'd506};
   7'd35:descriptor={1'b1,7'd23,7'd80,12'd563};
   7'd36:descriptor={1'b1,7'd23,7'd39,12'd621};
   7'd37:descriptor={1'b1,7'd23,7'd40,12'd638};
   7'd38:descriptor={1'b1,7'd22,7'd41,12'd656};
   7'd39:descriptor={1'b1,7'd22,7'd77,12'd676};
   7'd40:descriptor={1'b1,7'd21,7'd77,12'd732};
   7'd41:descriptor={1'b1,7'd21,7'd77,12'd789};
   7'd42:descriptor={1'b1,7'd20,7'd42,12'd846};
   7'd43:descriptor={1'b1,7'd19,7'd43,12'd869};
   7'd44:descriptor={1'b1,7'd19,7'd44,12'd894};
   7'd45:descriptor={1'b1,7'd19,7'd74,12'd920};
   7'd46:descriptor={1'b1,7'd18,7'd74,12'd976};
   7'd47:descriptor={1'b1,7'd18,7'd73,12'd1033};
   7'd48:descriptor={1'b1,7'd17,7'd73,12'd1089};
   7'd49:descriptor={1'b1,7'd17,7'd46,12'd1146};
   7'd50:descriptor={1'b1,7'd16,7'd46,12'd1176};
   7'd51:descriptor={1'b1,7'd15,7'd71,12'd1207};
   7'd52:descriptor={1'b1,7'd15,7'd71,12'd1264};
   7'd53:descriptor={1'b1,7'd15,7'd70,12'd1321};
   7'd54:descriptor={1'b1,7'd14,7'd70,12'd1377};
   7'd55:descriptor={1'b1,7'd14,7'd49,12'd1434};
   7'd56:descriptor={1'b1,7'd13,7'd49,12'd1470};
   7'd57:descriptor={1'b1,7'd13,7'd50,12'd1507};
   7'd58:descriptor={1'b1,7'd12,7'd68,12'd1545};
   7'd59:descriptor={1'b1,7'd11,7'd68,12'd1602};
   7'd60:descriptor={1'b1,7'd11,7'd67,12'd1660};
   7'd61:descriptor={1'b1,7'd11,7'd52,12'd1717};
   7'd62:descriptor={1'b1,7'd10,7'd53,12'd1759};
   7'd63:descriptor={1'b1,7'd10,7'd53,12'd1803};
   7'd64:descriptor={1'b1,7'd9,7'd65,12'd1847};
   7'd65:descriptor={1'b1,7'd9,7'd65,12'd1904};
   7'd66:descriptor={1'b1,7'd8,7'd64,12'd1961};
   7'd67:descriptor={1'b1,7'd7,7'd55,12'd2018};
   7'd68:descriptor={1'b1,7'd7,7'd56,12'd2067};
   7'd69:descriptor={1'b1,7'd7,7'd56,12'd2117};
   7'd70:descriptor={1'b1,7'd6,7'd62,12'd2167};
   7'd71:descriptor={1'b1,7'd6,7'd61,12'd2224};
   7'd72:descriptor={1'b1,7'd5,7'd61,12'd2280};
   7'd73:descriptor={1'b1,7'd5,7'd61,12'd2337};
   default:descriptor=27'd0;
  endcase
 end
 wire [6:0] xmin=descriptor[25:19],xmax=descriptor[18:12];
 wire [11:0] offset=descriptor[11:0];
 wire hit=descriptor[26] && I_local_x>=xmin && I_local_x<=xmax &&
   I_local_x<92 && I_local_y<92;
 wire [11:0] index_addr=hit ? offset+{5'd0,I_local_x}-{5'd0,xmin} : 12'd0;
 wire [7:0] index0,index1;
 reg bank_q,hit_q;
 always @(posedge I_clk)begin bank_q<=index_addr[11];hit_q<=hit;end
 wire [8:0] palette_addr={1'b0,hit_q?(bank_q?index1:index0):8'd0};
 PH1P_LOGIC_ERAM #(
  .DATA_WIDTH_A(8),.DATA_WIDTH_B(8),.ADDR_WIDTH_A(11),.ADDR_WIDTH_B(11),
  .DATA_DEPTH_A(2048),.DATA_DEPTH_B(2048),.BYTE_ENABLE(0),.BYTE_A(1),.BYTE_B(1),
  .MODE("SP"),.REGMODE_A("NOREG"),.REGMODE_B("NOREG"),
  .WRITEMODE_A("NORMAL"),.WRITEMODE_B("NORMAL"),
  .RESETMODE_A("ASYNC"),.RESETMODE_B("ASYNC"),
  .OREGSET_A("RESET"),.OREGSET_B("RESET"),.SSROVERCE("DISABLE"),
  .ECC_DECODE("DISABLE"),.ECC_ENCODE("DISABLE"),
  .ASYNC_RESET_RELEASE_A("ASYNC"),.ASYNC_RESET_RELEASE_B("ASYNC"),
  .CLKMODE("ASYNC"),.DEBUGGABLE("NO"),.PACKABLE("NO"),.FORCE_KEEP("ON"),
  .INIT_FILE(INDEX0_INIT_FILE),.FILL_ALL("NONE"),.IMPLEMENT("20K")
 ) u_index0 (
  .doa(index0),.dob(),.ecc_sbiterr(),.ecc_dbiterr(),
  .dia(8'd0),.dib(8'd0),.ecc_sbiterrinj(1'b0),.ecc_dbiterrinj(1'b0),
  .cea(1'b1),.ocea(1'b1),.clka(I_clk),.wea(1'b0),.rsta(1'b0),
  .ceb(1'b0),.oceb(1'b0),.clkb(I_clk),.web(1'b0),.rstb(1'b0),
  .bea(1'b0),.beb(1'b0),.addra(index_addr[10:0]),.addrb(11'd0)
 );
 PH1P_LOGIC_ERAM #(
  .DATA_WIDTH_A(8),.DATA_WIDTH_B(8),.ADDR_WIDTH_A(11),.ADDR_WIDTH_B(11),
  .DATA_DEPTH_A(2048),.DATA_DEPTH_B(2048),.BYTE_ENABLE(0),.BYTE_A(1),.BYTE_B(1),
  .MODE("SP"),.REGMODE_A("NOREG"),.REGMODE_B("NOREG"),
  .WRITEMODE_A("NORMAL"),.WRITEMODE_B("NORMAL"),
  .RESETMODE_A("ASYNC"),.RESETMODE_B("ASYNC"),
  .OREGSET_A("RESET"),.OREGSET_B("RESET"),.SSROVERCE("DISABLE"),
  .ECC_DECODE("DISABLE"),.ECC_ENCODE("DISABLE"),
  .ASYNC_RESET_RELEASE_A("ASYNC"),.ASYNC_RESET_RELEASE_B("ASYNC"),
  .CLKMODE("ASYNC"),.DEBUGGABLE("NO"),.PACKABLE("NO"),.FORCE_KEEP("ON"),
  .INIT_FILE(INDEX1_INIT_FILE),.FILL_ALL("NONE"),.IMPLEMENT("20K")
 ) u_index1 (
  .doa(index1),.dob(),.ecc_sbiterr(),.ecc_dbiterr(),
  .dia(8'd0),.dib(8'd0),.ecc_sbiterrinj(1'b0),.ecc_dbiterrinj(1'b0),
  .cea(1'b1),.ocea(1'b1),.clka(I_clk),.wea(1'b0),.rsta(1'b0),
  .ceb(1'b0),.oceb(1'b0),.clkb(I_clk),.web(1'b0),.rstb(1'b0),
  .bea(1'b0),.beb(1'b0),.addra(index_addr[10:0]),.addrb(11'd0)
 );
 PH1P_LOGIC_ERAM #(
  .DATA_WIDTH_A(25),.DATA_WIDTH_B(25),.ADDR_WIDTH_A(9),.ADDR_WIDTH_B(9),
  .DATA_DEPTH_A(512),.DATA_DEPTH_B(512),.BYTE_ENABLE(0),.BYTE_A(1),.BYTE_B(1),
  .MODE("SP"),.REGMODE_A("NOREG"),.REGMODE_B("NOREG"),
  .WRITEMODE_A("NORMAL"),.WRITEMODE_B("NORMAL"),
  .RESETMODE_A("ASYNC"),.RESETMODE_B("ASYNC"),
  .OREGSET_A("RESET"),.OREGSET_B("RESET"),.SSROVERCE("DISABLE"),
  .ECC_DECODE("DISABLE"),.ECC_ENCODE("DISABLE"),
  .ASYNC_RESET_RELEASE_A("ASYNC"),.ASYNC_RESET_RELEASE_B("ASYNC"),
  .CLKMODE("ASYNC"),.DEBUGGABLE("NO"),.PACKABLE("NO"),.FORCE_KEEP("ON"),
  .INIT_FILE(PALETTE_INIT_FILE),.FILL_ALL("NONE"),.IMPLEMENT("20K")
 ) u_palette (
  .doa(O_pixel),.dob(),.ecc_sbiterr(),.ecc_dbiterr(),
  .dia(25'd0),.dib(25'd0),.ecc_sbiterrinj(1'b0),.ecc_dbiterrinj(1'b0),
  .cea(1'b1),.ocea(1'b1),.clka(I_clk),.wea(1'b0),.rsta(1'b0),
  .ceb(1'b0),.oceb(1'b0),.clkb(I_clk),.web(1'b0),.rstb(1'b0),
  .bea(1'b0),.beb(1'b0),.addra(palette_addr),.addrb(9'd0)
 );
endmodule
