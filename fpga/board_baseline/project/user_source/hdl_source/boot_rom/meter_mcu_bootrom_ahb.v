// Single-master native AHB ROM interposer. Existing ROI bridge remains intact.
// HADDR[31] is not exposed by PH1P hardMCU: A0000000 -> low31 20000000.
// Responses select the accepted data phase, never the current address phase.
module meter_mcu_bootrom_ahb #(
 parameter [30:0] BASE=31'h20000000,
 parameter ROM_FILE="bootrom.mem"
)(
 input wire clk,arst_n,
 input wire [30:0] haddr,input wire [1:0] htrans,
 input wire hwrite,input wire [2:0] hsize,
 input wire [31:0] mmio_hrdata,input wire [1:0] mmio_hresp,input wire mmio_hready,
 output wire [1:0] mmio_htrans,
 output reg [31:0] hrdata,output reg [1:0] hresp,output reg hready
);
 // Integration supplies existingS_mcu_release[1]: asynchronousassertion,
 // synchronousHCLKdeassertion, alreadyreadybeforeCPUrelease[7]. No duplicate
 // externalreset synchronizer or newuntimedreset-entry frontier is added.
 wire rst_n=arst_n;
 localparam SEL_NONE=2'd0,SEL_MMIO=2'd1,SEL_ROM=2'd2;
 localparam ROM_WAIT=2'd0,ROM_RESP=2'd1,ROM_ERR1=2'd2,ROM_ERR2=2'd3;
 reg [1:0] data_select,rom_phase;
 (* rom_style="bram" *) reg [31:0] rom[0:511];
 reg [31:0] rom_q;
 initial $readmemh(ROM_FILE,rom);
 wire rom_hit=haddr[30:11]==BASE[30:11];
 wire bad_access=hwrite||hsize>3'd2||
  (hsize==3'd1&&haddr[0])||(hsize==3'd2&&(|haddr[1:0]));
 wire rom_accept=rst_n&&hready&&htrans[1]&&rom_hit;
 // No runtime array reset/write. One synchronous read on the accepted A edge;
 // one conservative AHB wait then returns the complete aligned word/lanes.
 always @(posedge clk)
  if(rom_accept&&!bad_access)rom_q<=rom[haddr[10:2]];
 assign mmio_htrans=(rst_n&&hready&&!rom_hit)?htrans:2'b00;
 always @* begin
  hrdata=0;hresp=0;hready=1;
  case(data_select)
   SEL_MMIO:begin hrdata=mmio_hrdata;hresp=mmio_hresp;hready=mmio_hready;end
   SEL_ROM:case(rom_phase)
    ROM_WAIT:begin hready=0;end
    ROM_RESP:begin hrdata=rom_q;end
    ROM_ERR1:begin hresp=2'b01;hready=0;end
    ROM_ERR2:begin hresp=2'b01;end
    default:begin hresp=2'b01;hready=0;end
   endcase
   default:begin end
  endcase
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin data_select<=SEL_NONE;rom_phase<=ROM_WAIT;end
  else begin
   if(hready)begin
    if(htrans[1])begin
     data_select<=rom_hit?SEL_ROM:SEL_MMIO;
     if(rom_hit)rom_phase<=bad_access?ROM_ERR1:ROM_WAIT;
    end else data_select<=SEL_NONE;
   end
   if(data_select==SEL_ROM&&!hready)begin
    if(rom_phase==ROM_WAIT)rom_phase<=ROM_RESP;
    else if(rom_phase==ROM_ERR1)rom_phase<=ROM_ERR2;
   end
  end
 end
endmodule
