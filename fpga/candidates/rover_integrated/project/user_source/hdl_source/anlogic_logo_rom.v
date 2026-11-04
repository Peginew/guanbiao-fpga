// Exact original 32768x25-bit address semantics. No pixel/alpha changes.
// Stage1: eight 2048x10 PH1P ERAM synchronous reads + the same-edge bank select.
// Stage2: unchanged synchronous palette lookup. Existing mixer stays byte-identical.
// PH1P_LOGIC_ERAM parameters/ports follow the installed PH1P device template.
// All unused inputs are tied; no reset, CE, clock, pin or constraint is introduced.
module anlogic_logo_rom #(
 parameter INDEX0_INIT_FILE = "C:/Users/Edward/Desktop/FPGA/Stable3s_Rover_Merged_20261104/fpga/external/489db80c7623_anlogic_logo_index0.dath",
 parameter INDEX1_INIT_FILE = "C:/Users/Edward/Desktop/FPGA/Stable3s_Rover_Merged_20261104/fpga/external/972cd6c86c57_anlogic_logo_index1.dath",
 parameter INDEX2_INIT_FILE = "C:/Users/Edward/Desktop/FPGA/Stable3s_Rover_Merged_20261104/fpga/external/e2df7be93fc5_anlogic_logo_index2.dath",
 parameter INDEX3_INIT_FILE = "C:/Users/Edward/Desktop/FPGA/Stable3s_Rover_Merged_20261104/fpga/external/473907034859_anlogic_logo_index3.dath",
 parameter INDEX4_INIT_FILE = "C:/Users/Edward/Desktop/FPGA/Stable3s_Rover_Merged_20261104/fpga/external/9d75a2550b8e_anlogic_logo_index4.dath",
 parameter INDEX5_INIT_FILE = "C:/Users/Edward/Desktop/FPGA/Stable3s_Rover_Merged_20261104/fpga/external/668748d315ff_anlogic_logo_index5.dath",
 parameter INDEX6_INIT_FILE = "C:/Users/Edward/Desktop/FPGA/Stable3s_Rover_Merged_20261104/fpga/external/402fcb865820_anlogic_logo_index6.dath",
 parameter INDEX7_INIT_FILE = "C:/Users/Edward/Desktop/FPGA/Stable3s_Rover_Merged_20261104/fpga/external/286bbe41de71_anlogic_logo_index7.dath",
 parameter PALETTE_INIT_FILE = "C:/Users/Edward/Desktop/FPGA/Stable3s_Rover_Merged_20261104/fpga/external/05c2f63c5ef1_anlogic_logo_palette.mem"
)(input wire I_clk, input wire [14:0] I_addr, output reg [24:0] O_pixel);
 wire [13:0] index_addr = (I_addr >= 15'd5440 && I_addr < 15'd20480)
                          ? I_addr - 15'd5440 : 14'd16383;
 wire [9:0] bank_data [0:7];
 reg [2:0] bank_q;
 wire [9:0] palette_index = bank_data[bank_q];
 (* ram_style = "bram" *) reg [24:0] palette_rom [0:1023]; // synthesis ram_style=bram
 initial $readmemh(PALETTE_INIT_FILE, palette_rom);
 always @(posedge I_clk) begin
  bank_q <= index_addr[13:11];
  O_pixel <= palette_rom[palette_index];
 end
 PH1P_LOGIC_ERAM #(
  .DATA_WIDTH_A(10), .DATA_WIDTH_B(10), .ADDR_WIDTH_A(11), .ADDR_WIDTH_B(11),
  .DATA_DEPTH_A(2048), .DATA_DEPTH_B(2048), .BYTE_ENABLE(0), .BYTE_A(1), .BYTE_B(1),
  .MODE("SP"), .REGMODE_A("NOREG"), .REGMODE_B("NOREG"),
  .WRITEMODE_A("NORMAL"), .WRITEMODE_B("NORMAL"),
  .RESETMODE_A("ASYNC"), .RESETMODE_B("ASYNC"),
  .OREGSET_A("RESET"), .OREGSET_B("RESET"), .SSROVERCE("DISABLE"),
  .ECC_DECODE("DISABLE"), .ECC_ENCODE("DISABLE"),
  .ASYNC_RESET_RELEASE_A("ASYNC"), .ASYNC_RESET_RELEASE_B("ASYNC"),
  .CLKMODE("ASYNC"), .DEBUGGABLE("NO"), .PACKABLE("NO"), .FORCE_KEEP("ON"),
  .INIT_FILE(INDEX0_INIT_FILE), .FILL_ALL("NONE"), .IMPLEMENT("20K")
 ) u_index_bank0 (
  .doa(bank_data[0]), .dob(), .ecc_sbiterr(), .ecc_dbiterr(),
  .dia(10'd0), .dib(10'd0), .ecc_sbiterrinj(1'b0), .ecc_dbiterrinj(1'b0),
  .cea(1'b1), .ocea(1'b1), .clka(I_clk), .wea(1'b0), .rsta(1'b0),
  .ceb(1'b0), .oceb(1'b0), .clkb(I_clk), .web(1'b0), .rstb(1'b0),
  .bea(1'b0), .beb(1'b0), .addra(index_addr[10:0]), .addrb(11'd0)
 );
 PH1P_LOGIC_ERAM #(
  .DATA_WIDTH_A(10), .DATA_WIDTH_B(10), .ADDR_WIDTH_A(11), .ADDR_WIDTH_B(11),
  .DATA_DEPTH_A(2048), .DATA_DEPTH_B(2048), .BYTE_ENABLE(0), .BYTE_A(1), .BYTE_B(1),
  .MODE("SP"), .REGMODE_A("NOREG"), .REGMODE_B("NOREG"),
  .WRITEMODE_A("NORMAL"), .WRITEMODE_B("NORMAL"),
  .RESETMODE_A("ASYNC"), .RESETMODE_B("ASYNC"),
  .OREGSET_A("RESET"), .OREGSET_B("RESET"), .SSROVERCE("DISABLE"),
  .ECC_DECODE("DISABLE"), .ECC_ENCODE("DISABLE"),
  .ASYNC_RESET_RELEASE_A("ASYNC"), .ASYNC_RESET_RELEASE_B("ASYNC"),
  .CLKMODE("ASYNC"), .DEBUGGABLE("NO"), .PACKABLE("NO"), .FORCE_KEEP("ON"),
  .INIT_FILE(INDEX1_INIT_FILE), .FILL_ALL("NONE"), .IMPLEMENT("20K")
 ) u_index_bank1 (
  .doa(bank_data[1]), .dob(), .ecc_sbiterr(), .ecc_dbiterr(),
  .dia(10'd0), .dib(10'd0), .ecc_sbiterrinj(1'b0), .ecc_dbiterrinj(1'b0),
  .cea(1'b1), .ocea(1'b1), .clka(I_clk), .wea(1'b0), .rsta(1'b0),
  .ceb(1'b0), .oceb(1'b0), .clkb(I_clk), .web(1'b0), .rstb(1'b0),
  .bea(1'b0), .beb(1'b0), .addra(index_addr[10:0]), .addrb(11'd0)
 );
 PH1P_LOGIC_ERAM #(
  .DATA_WIDTH_A(10), .DATA_WIDTH_B(10), .ADDR_WIDTH_A(11), .ADDR_WIDTH_B(11),
  .DATA_DEPTH_A(2048), .DATA_DEPTH_B(2048), .BYTE_ENABLE(0), .BYTE_A(1), .BYTE_B(1),
  .MODE("SP"), .REGMODE_A("NOREG"), .REGMODE_B("NOREG"),
  .WRITEMODE_A("NORMAL"), .WRITEMODE_B("NORMAL"),
  .RESETMODE_A("ASYNC"), .RESETMODE_B("ASYNC"),
  .OREGSET_A("RESET"), .OREGSET_B("RESET"), .SSROVERCE("DISABLE"),
  .ECC_DECODE("DISABLE"), .ECC_ENCODE("DISABLE"),
  .ASYNC_RESET_RELEASE_A("ASYNC"), .ASYNC_RESET_RELEASE_B("ASYNC"),
  .CLKMODE("ASYNC"), .DEBUGGABLE("NO"), .PACKABLE("NO"), .FORCE_KEEP("ON"),
  .INIT_FILE(INDEX2_INIT_FILE), .FILL_ALL("NONE"), .IMPLEMENT("20K")
 ) u_index_bank2 (
  .doa(bank_data[2]), .dob(), .ecc_sbiterr(), .ecc_dbiterr(),
  .dia(10'd0), .dib(10'd0), .ecc_sbiterrinj(1'b0), .ecc_dbiterrinj(1'b0),
  .cea(1'b1), .ocea(1'b1), .clka(I_clk), .wea(1'b0), .rsta(1'b0),
  .ceb(1'b0), .oceb(1'b0), .clkb(I_clk), .web(1'b0), .rstb(1'b0),
  .bea(1'b0), .beb(1'b0), .addra(index_addr[10:0]), .addrb(11'd0)
 );
 PH1P_LOGIC_ERAM #(
  .DATA_WIDTH_A(10), .DATA_WIDTH_B(10), .ADDR_WIDTH_A(11), .ADDR_WIDTH_B(11),
  .DATA_DEPTH_A(2048), .DATA_DEPTH_B(2048), .BYTE_ENABLE(0), .BYTE_A(1), .BYTE_B(1),
  .MODE("SP"), .REGMODE_A("NOREG"), .REGMODE_B("NOREG"),
  .WRITEMODE_A("NORMAL"), .WRITEMODE_B("NORMAL"),
  .RESETMODE_A("ASYNC"), .RESETMODE_B("ASYNC"),
  .OREGSET_A("RESET"), .OREGSET_B("RESET"), .SSROVERCE("DISABLE"),
  .ECC_DECODE("DISABLE"), .ECC_ENCODE("DISABLE"),
  .ASYNC_RESET_RELEASE_A("ASYNC"), .ASYNC_RESET_RELEASE_B("ASYNC"),
  .CLKMODE("ASYNC"), .DEBUGGABLE("NO"), .PACKABLE("NO"), .FORCE_KEEP("ON"),
  .INIT_FILE(INDEX3_INIT_FILE), .FILL_ALL("NONE"), .IMPLEMENT("20K")
 ) u_index_bank3 (
  .doa(bank_data[3]), .dob(), .ecc_sbiterr(), .ecc_dbiterr(),
  .dia(10'd0), .dib(10'd0), .ecc_sbiterrinj(1'b0), .ecc_dbiterrinj(1'b0),
  .cea(1'b1), .ocea(1'b1), .clka(I_clk), .wea(1'b0), .rsta(1'b0),
  .ceb(1'b0), .oceb(1'b0), .clkb(I_clk), .web(1'b0), .rstb(1'b0),
  .bea(1'b0), .beb(1'b0), .addra(index_addr[10:0]), .addrb(11'd0)
 );
 PH1P_LOGIC_ERAM #(
  .DATA_WIDTH_A(10), .DATA_WIDTH_B(10), .ADDR_WIDTH_A(11), .ADDR_WIDTH_B(11),
  .DATA_DEPTH_A(2048), .DATA_DEPTH_B(2048), .BYTE_ENABLE(0), .BYTE_A(1), .BYTE_B(1),
  .MODE("SP"), .REGMODE_A("NOREG"), .REGMODE_B("NOREG"),
  .WRITEMODE_A("NORMAL"), .WRITEMODE_B("NORMAL"),
  .RESETMODE_A("ASYNC"), .RESETMODE_B("ASYNC"),
  .OREGSET_A("RESET"), .OREGSET_B("RESET"), .SSROVERCE("DISABLE"),
  .ECC_DECODE("DISABLE"), .ECC_ENCODE("DISABLE"),
  .ASYNC_RESET_RELEASE_A("ASYNC"), .ASYNC_RESET_RELEASE_B("ASYNC"),
  .CLKMODE("ASYNC"), .DEBUGGABLE("NO"), .PACKABLE("NO"), .FORCE_KEEP("ON"),
  .INIT_FILE(INDEX4_INIT_FILE), .FILL_ALL("NONE"), .IMPLEMENT("20K")
 ) u_index_bank4 (
  .doa(bank_data[4]), .dob(), .ecc_sbiterr(), .ecc_dbiterr(),
  .dia(10'd0), .dib(10'd0), .ecc_sbiterrinj(1'b0), .ecc_dbiterrinj(1'b0),
  .cea(1'b1), .ocea(1'b1), .clka(I_clk), .wea(1'b0), .rsta(1'b0),
  .ceb(1'b0), .oceb(1'b0), .clkb(I_clk), .web(1'b0), .rstb(1'b0),
  .bea(1'b0), .beb(1'b0), .addra(index_addr[10:0]), .addrb(11'd0)
 );
 PH1P_LOGIC_ERAM #(
  .DATA_WIDTH_A(10), .DATA_WIDTH_B(10), .ADDR_WIDTH_A(11), .ADDR_WIDTH_B(11),
  .DATA_DEPTH_A(2048), .DATA_DEPTH_B(2048), .BYTE_ENABLE(0), .BYTE_A(1), .BYTE_B(1),
  .MODE("SP"), .REGMODE_A("NOREG"), .REGMODE_B("NOREG"),
  .WRITEMODE_A("NORMAL"), .WRITEMODE_B("NORMAL"),
  .RESETMODE_A("ASYNC"), .RESETMODE_B("ASYNC"),
  .OREGSET_A("RESET"), .OREGSET_B("RESET"), .SSROVERCE("DISABLE"),
  .ECC_DECODE("DISABLE"), .ECC_ENCODE("DISABLE"),
  .ASYNC_RESET_RELEASE_A("ASYNC"), .ASYNC_RESET_RELEASE_B("ASYNC"),
  .CLKMODE("ASYNC"), .DEBUGGABLE("NO"), .PACKABLE("NO"), .FORCE_KEEP("ON"),
  .INIT_FILE(INDEX5_INIT_FILE), .FILL_ALL("NONE"), .IMPLEMENT("20K")
 ) u_index_bank5 (
  .doa(bank_data[5]), .dob(), .ecc_sbiterr(), .ecc_dbiterr(),
  .dia(10'd0), .dib(10'd0), .ecc_sbiterrinj(1'b0), .ecc_dbiterrinj(1'b0),
  .cea(1'b1), .ocea(1'b1), .clka(I_clk), .wea(1'b0), .rsta(1'b0),
  .ceb(1'b0), .oceb(1'b0), .clkb(I_clk), .web(1'b0), .rstb(1'b0),
  .bea(1'b0), .beb(1'b0), .addra(index_addr[10:0]), .addrb(11'd0)
 );
 PH1P_LOGIC_ERAM #(
  .DATA_WIDTH_A(10), .DATA_WIDTH_B(10), .ADDR_WIDTH_A(11), .ADDR_WIDTH_B(11),
  .DATA_DEPTH_A(2048), .DATA_DEPTH_B(2048), .BYTE_ENABLE(0), .BYTE_A(1), .BYTE_B(1),
  .MODE("SP"), .REGMODE_A("NOREG"), .REGMODE_B("NOREG"),
  .WRITEMODE_A("NORMAL"), .WRITEMODE_B("NORMAL"),
  .RESETMODE_A("ASYNC"), .RESETMODE_B("ASYNC"),
  .OREGSET_A("RESET"), .OREGSET_B("RESET"), .SSROVERCE("DISABLE"),
  .ECC_DECODE("DISABLE"), .ECC_ENCODE("DISABLE"),
  .ASYNC_RESET_RELEASE_A("ASYNC"), .ASYNC_RESET_RELEASE_B("ASYNC"),
  .CLKMODE("ASYNC"), .DEBUGGABLE("NO"), .PACKABLE("NO"), .FORCE_KEEP("ON"),
  .INIT_FILE(INDEX6_INIT_FILE), .FILL_ALL("NONE"), .IMPLEMENT("20K")
 ) u_index_bank6 (
  .doa(bank_data[6]), .dob(), .ecc_sbiterr(), .ecc_dbiterr(),
  .dia(10'd0), .dib(10'd0), .ecc_sbiterrinj(1'b0), .ecc_dbiterrinj(1'b0),
  .cea(1'b1), .ocea(1'b1), .clka(I_clk), .wea(1'b0), .rsta(1'b0),
  .ceb(1'b0), .oceb(1'b0), .clkb(I_clk), .web(1'b0), .rstb(1'b0),
  .bea(1'b0), .beb(1'b0), .addra(index_addr[10:0]), .addrb(11'd0)
 );
 PH1P_LOGIC_ERAM #(
  .DATA_WIDTH_A(10), .DATA_WIDTH_B(10), .ADDR_WIDTH_A(11), .ADDR_WIDTH_B(11),
  .DATA_DEPTH_A(2048), .DATA_DEPTH_B(2048), .BYTE_ENABLE(0), .BYTE_A(1), .BYTE_B(1),
  .MODE("SP"), .REGMODE_A("NOREG"), .REGMODE_B("NOREG"),
  .WRITEMODE_A("NORMAL"), .WRITEMODE_B("NORMAL"),
  .RESETMODE_A("ASYNC"), .RESETMODE_B("ASYNC"),
  .OREGSET_A("RESET"), .OREGSET_B("RESET"), .SSROVERCE("DISABLE"),
  .ECC_DECODE("DISABLE"), .ECC_ENCODE("DISABLE"),
  .ASYNC_RESET_RELEASE_A("ASYNC"), .ASYNC_RESET_RELEASE_B("ASYNC"),
  .CLKMODE("ASYNC"), .DEBUGGABLE("NO"), .PACKABLE("NO"), .FORCE_KEEP("ON"),
  .INIT_FILE(INDEX7_INIT_FILE), .FILL_ALL("NONE"), .IMPLEMENT("20K")
 ) u_index_bank7 (
  .doa(bank_data[7]), .dob(), .ecc_sbiterr(), .ecc_dbiterr(),
  .dia(10'd0), .dib(10'd0), .ecc_sbiterrinj(1'b0), .ecc_dbiterrinj(1'b0),
  .cea(1'b1), .ocea(1'b1), .clka(I_clk), .wea(1'b0), .rsta(1'b0),
  .ceb(1'b0), .oceb(1'b0), .clkb(I_clk), .web(1'b0), .rstb(1'b0),
  .bea(1'b0), .beb(1'b0), .addra(index_addr[10:0]), .addrb(11'd0)
 );
endmodule
