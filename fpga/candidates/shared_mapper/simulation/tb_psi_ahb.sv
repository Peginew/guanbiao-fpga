`timescale 1ns/1ps
module tb_psi_ahb;
 reg clk=0;always #5 clk=~clk;
 reg rst_n=0;reg [30:0] addr=0;reg[1:0] trans=0;reg wr=0;reg[2:0]size=2;reg[31:0]data=0;
 wire[31:0]rdata;wire[1:0]resp;wire ready;
 reg offer=0;wire offer_ready;reg[95:0]token={32'd1,32'd42,32'd7};
 reg live=1,cancel=0,accept=0;wire rv;wire[95:0]rt;wire[15:0]rtarget;wire[31:0]rcfg,rcrc,rbytes,rcode;
 wire[15:0]rpsi;wire rpsiv,armed,own,claimed;wire[7:0]error;
 meter_mcu_roi_ahb_live dut(.clk(clk),.rst_n(rst_n),.haddr(addr),.htrans(trans),.hwrite(wr),.hsize(size),.hwdata(data),.hrdata(rdata),.hresp(resp),.hready(ready),
 .source_crc32(32'h12345678),.quality_flags(0),.quality_mean(0),.quality_gradient(0),.quality_counts(0),.observer_seq(0),.observer_hword(0),.observer_snapshot(96'd0),.observer_offer_accepted(),
 .offer_valid(offer),.offer_ready(offer_ready),.offer_token(token),.offer_target(16'd1),.offer_config(32'd1),.offer_x0(11'd0),.offer_y0(10'd0),.offer_stride(3'd2),.offer_radius(7'd60),
 .roi_live(live),.cancel(cancel),.cpu_reset_quiescent(1'b0),.session_busy(),.owner_visible(own),.cpu_claimed(claimed),.revoked(),.release_pulse(),.offer_rejected(),.last_error(error),
 .roi_rd_en(),.roi_rd_addr(),.roi_rd_data(8'd0),.checksum_result_valid(rv),.checksum_result_ready(accept),.checksum_result_token(rt),.checksum_result_target(rtarget),.checksum_result_config(rcfg),.checksum_crc32(rcrc),
 .platform_armed(armed),.checksum_bytes(rbytes),.checksum_code(rcode),.checksum_psi_q8(rpsi),.checksum_psi_valid(rpsiv),.progress_ready(1'b1));
 integer checks=0;reg[31:0]read_value;reg bus_error;
 task check;input condition;input[255:0]why;begin if(!condition)begin $display("FAIL PSI_AHB %s error=%0d",why,error);$fatal;end checks=checks+1;end endtask
 task access;input is_write;input[31:0]offset,value;integer n;begin
  @(negedge clk);addr=offset;trans=2;wr=is_write;data=value;bus_error=0;
  @(negedge clk);trans=0;n=0;
  while(!ready&&n<20)begin if(resp!=0)bus_error=1;@(negedge clk);n=n+1;end
  if(resp!=0)bus_error=1;read_value=rdata;check(n<20,"bus completes");
  @(negedge clk);
 end endtask
 task writeok;input[31:0]a,v;begin access(1,a,v);check(!bus_error,"legal write");end endtask
 task claim;begin
  @(negedge clk);offer=1;while(!offer_ready)@(negedge clk);@(negedge clk);offer=0;
  check(own,"owner");writeok('h80,token[95:64]);writeok('h84,token[63:32]);writeok('h88,token[31:0]);writeok('h8c,32'h434c4149);check(claimed,"claim");
 end endtask
 task body;begin
  writeok('h100,token[95:64]);writeok('h104,token[63:32]);writeok('h108,token[31:0]);writeok('h10c,1);writeok('h110,1);writeok('h114,32'h12345678);writeok('h118,16384);writeok('h11c,32'hbc080400);
 end endtask
 initial begin
  repeat(4)@(negedge clk);rst_n=1;
  access(0,'h60,0);check(read_value==0,"ARM remains original");access(0,'h64,0);check(read_value==3,"FEATURES PSI plus stage, ARM unchanged");
  writeok('h60,32'h41524d31);access(0,'h60,0);check(read_value==1&&armed,"ARM still works");
  claim;access(1,'h124,32'h80010300);check(bus_error&&error==10,"reject reserved bits");
  writeok('h124,32'h80000800);body;writeok('h120,32'h52455331);
  check(rv&&rpsiv&&rpsi==2048&&rt==token&&rbytes==16384,"samecommit scalar");
  repeat(4)begin @(negedge clk);check(rv&&rpsiv&&rpsi==2048,"bundled payload held");end
  accept=1;@(negedge clk);accept=0;token[31:0]=8;token[63:32]=43;
  claim;body;writeok('h120,32'h52455331);check(rv&&!rpsiv,"oldresult cannotreuse PSI");
  accept=1;@(negedge clk);accept=0;token[31:0]=9;token[63:32]=44;
  claim;writeok('h124,32'h80000c00);body;cancel=1;@(negedge clk);
  access(1,'h120,32'h52455331);check(bus_error&&!rv,"cancelled source cannot publish");
  $display("PASS PSI_AHB checks=%0d same_source_commit_ARM060_FEATURES064_RETURN124",checks);$finish;
 end
 initial begin #200000;$display("FAIL PSI_AHB timeout");$fatal;end
endmodule
