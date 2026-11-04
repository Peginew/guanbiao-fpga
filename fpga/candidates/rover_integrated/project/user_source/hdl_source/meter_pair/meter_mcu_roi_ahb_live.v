// Single-master AHB subset, 32-bit aligned word accesses, 00 OKAY/01 ERROR.
// Component contract: HCLK and the owned canonical ROI port MUST be the same
// clock with a fixed synchronous one-cycle byte return. No CDC is implemented.
module meter_mcu_roi_ahb_live #(parameter [30:0] BASE=31'd0)(
 input wire clk,rst_n,
 input wire [30:0] haddr,input wire [1:0] htrans,input wire hwrite,
 input wire [2:0] hsize,input wire [31:0] hwdata,
 output reg [31:0] hrdata,output reg [1:0] hresp,output reg hready,
 input wire [31:0] source_crc32,quality_flags,quality_mean,quality_gradient,quality_counts,
 input wire [31:0] observer_seq,observer_hword,input wire [95:0] observer_snapshot,
 output wire observer_offer_accepted,
 input wire offer_valid,output wire offer_ready,input wire [95:0] offer_token,
 input wire [15:0] offer_target,input wire [31:0] offer_config,
 input wire [10:0] offer_x0,input wire [9:0] offer_y0,
 input wire [2:0] offer_stride,input wire [6:0] offer_radius,
 input wire roi_live,cancel,cpu_reset_quiescent,
 output wire session_busy,owner_visible,cpu_claimed,revoked,
 output reg release_pulse,offer_rejected,output reg [7:0] last_error,
 output wire roi_rd_en,output wire [13:0] roi_rd_addr,input wire [7:0] roi_rd_data,
 output wire checksum_result_valid,input wire checksum_result_ready,
 output wire [95:0] checksum_result_token,output wire [15:0] checksum_result_target,
 output wire [31:0] checksum_result_config,output reg [31:0] checksum_crc32,
 output reg platform_armed,
 output reg [31:0] checksum_bytes,checksum_code,
 output reg [15:0] checksum_psi_q8,output reg checksum_psi_valid
);
 localparam IDLE=0,DECODE=1,RESP=2,RREQ=3,RWAIT=4,ERR1=5,ERR2=6;
 localparam E_ALIGN=1,E_SIZE=2,E_ADDRESS=3,E_READONLY=4,E_OWNER=5,
  E_CLAIM=6,E_TOKEN=7,E_BODY=8,E_REVOKED=9,E_FORMAT=10,E_MAGIC=11,E_REPLAY=12;
 reg [2:0] bus_state;reg [31:0] bus_offset,write_data,read_data;
 reg bus_write,bus_roi;reg [2:0] bus_size;reg [1:0] bus_align;
 reg present,active,claimed,result_pending,ram_pending,roi_word_active;
 reg [95:0] token;reg [15:0] target;reg [31:0] config_id,descriptor_seq;
 reg [10:0] x0;reg [9:0] y0;reg [2:0] stride;reg [6:0] radius;
 reg seen;reg [31:0] seen_epoch,seen_job;
 wire [31:0] epoch_delta=offer_token[95:64]-seen_epoch,job_delta=offer_token[31:0]-seen_job;
 wire fresh=!seen||(offer_token[95:64]==seen_epoch?(job_delta!=0&&!job_delta[31]):(epoch_delta!=0&&!epoch_delta[31]));
 wire [11:0] offered_xend={1'b0,offer_x0}+{2'b0,offer_stride,7'd0};
 wire [10:0] offered_yend={1'b0,offer_y0}+{1'b0,offer_stride,7'd0};
 wire offer_format=offer_stride>=1&&offer_stride<=4&&offer_radius>=40&&offer_radius<=62&&
  offer_x0[1:0]==0&&offered_xend<=1280&&offered_yend<=720;
 wire kill=cancel||!roi_live||cpu_reset_quiescent;
 assign offer_ready=rst_n&&platform_armed&&!kill&&!present&&!ram_pending&&!roi_word_active;
 assign observer_offer_accepted=offer_valid&&offer_ready&&fresh&&offer_format; // exact existing legal accept, no feedback
 assign owner_visible=rst_n&&present&&active&&!kill;
 assign cpu_claimed=present&&claimed;
 assign revoked=present&&!active&&!result_pending;
 assign session_busy=present||ram_pending||roi_word_active;
 assign checksum_result_valid=rst_n&&present&&result_pending&&!kill;
 assign checksum_result_token=token;assign checksum_result_target=target;
 assign checksum_result_config=config_id;
 wire read_allowed=owner_visible&&claimed;
 reg [1:0] byte_index;reg [31:0] word_acc;
 assign roi_rd_en=rst_n&&bus_state==RREQ&&read_allowed;
 assign roi_rd_addr=bus_offset[13:0]-14'h1000+{12'd0,byte_index};
 reg [31:0] claim_epoch,claim_source,claim_job;reg [2:0] claim_mask;
 reg [31:0] quiet_epoch,quiet_source,quiet_job;reg [2:0] quiet_mask;
 reg [31:0] ret_epoch,ret_source,ret_job,ret_target,ret_config,ret_crc,ret_bytes,ret_code;
 reg [7:0] ret_mask;reg [15:0] ret_psi_q8;reg ret_psi_valid;
 wire claim_token_ok={claim_epoch,claim_source,claim_job}==token;
 wire quiet_token_ok={quiet_epoch,quiet_source,quiet_job}==token;
 wire return_token_ok={ret_epoch,ret_source,ret_job}==token&&ret_target=={16'd0,target}&&ret_config==config_id;
 wire [31:0] address_delta={1'b0,haddr}-{1'b0,BASE};
 wire address_in_window={1'b0,haddr}>={1'b0,BASE}&&address_delta<32'h5000;
 wire [31:0] incoming_offset=address_in_window?address_delta:32'hffffffff;
 wire [7:0] result_response_error=bus_roi&&!read_allowed?E_REVOKED:8'd0;
 function register_readable;input [31:0] a;
  begin register_readable=(a<=32'h64&&a[1:0]==0)||(a>=32'h200&&a<=32'h210&&a[1:0]==0);end
 endfunction
 function [31:0] read_register;input [31:0] a;
  begin case(a)
   'h00:read_register=32'h524f4931;'h04:read_register=32'h00010000;
   'h08:read_register={25'd0,ram_pending,result_pending,claimed,revoked,present,owner_visible,1'b0};
   'h0c:read_register={24'd0,last_error};'h10:read_register=descriptor_seq;
   'h14:read_register=token[95:64];'h18:read_register=token[63:32];'h1c:read_register=token[31:0];
   'h20:read_register={16'd0,target};'h24:read_register=config_id;
   'h28:read_register={21'd0,x0};'h2c:read_register={22'd0,y0};
   'h30:read_register={16'd128,16'd128};'h34:read_register={29'd0,stride};
   'h38:read_register={25'd0,radius};'h3c:read_register=32'd1; // native U8 blockmean
   'h40:read_register=32'd16384;'h44:read_register=32'd0;
   'h48:read_register=source_crc32;'h4c:read_register=quality_flags;
   'h50:read_register=quality_mean;'h54:read_register=quality_gradient;
   'h58:read_register=quality_counts;'h5c:read_register=32'h4c565231;
   'h60:read_register={31'd0,platform_armed};
   'h64:read_register=32'h00000001; // FEATURES bit0: PSI_Q8_RETURN_V1
   'h200:read_register=observer_seq;
   'h204:read_register=observer_snapshot[31:0];
   'h208:read_register=32'd0;
   'h20c:read_register=32'd0;
   'h210:read_register=observer_hword;
   default:read_register=0;
  endcase end
 endfunction
 reg [7:0] write_error;
 always @* begin
  write_error=0;
  case(bus_offset)
   'h60:if(write_data!=32'h41524d31)write_error=E_MAGIC;
   'h80,'h84,'h88:if(!owner_visible)write_error=E_OWNER;else if(claimed)write_error=E_CLAIM;
   'h8c:if(!owner_visible)write_error=E_OWNER;else if(claimed)write_error=E_CLAIM;
    else if(write_data!=32'h434c4149)write_error=E_MAGIC;
    else if(claim_mask!=3'b111)write_error=E_BODY;else if(!claim_token_ok)write_error=E_TOKEN;
   'h100,'h104,'h108,'h10c,'h110,'h114,'h118,'h11c:
    if(!owner_visible)write_error=E_OWNER;else if(!claimed)write_error=E_CLAIM;
   'h124:if(!owner_visible)write_error=E_OWNER;else if(!claimed)write_error=E_CLAIM;
    else if(write_data[30:16]!=0||(write_data[31]&&(write_data[15:0]<640||write_data[15:0]>3072)))write_error=E_FORMAT;
   'h120:if(!owner_visible)write_error=E_OWNER;else if(!claimed)write_error=E_CLAIM;
    else if(write_data!=32'h52455331)write_error=E_MAGIC;else if(ret_mask!=8'hff)write_error=E_BODY;
    else if(!return_token_ok)write_error=E_TOKEN;
    else if(ret_bytes!=16384)write_error=E_FORMAT;
   'h180,'h184,'h188:if(!present||!claimed||cpu_reset_quiescent)write_error=E_OWNER;
   'h18c:if(!present||!claimed||cpu_reset_quiescent)write_error=E_OWNER;
    else if(write_data!=32'h51554945)write_error=E_MAGIC;
    else if(quiet_mask!=3'b111)write_error=E_BODY;else if(!quiet_token_ok)write_error=E_TOKEN;
   default:write_error=E_READONLY;
  endcase
 end
 always @* begin
  hrdata=read_data;hresp=0;hready=0;
  case(bus_state)
   IDLE:begin hready=1;hrdata=0;end
   RESP:if(bus_write&&write_error!=0||!bus_write&&result_response_error!=0)begin hresp=1;hready=0;hrdata=0;end
        else begin hready=1;if(bus_write)hrdata=0;end
   ERR1:begin hresp=1;hready=0;hrdata=0;end
   ERR2:begin hresp=1;hready=1;hrdata=0;end
   default:begin end
  endcase
 end
 task accept_address;
  begin
   if(htrans[1]&&!cpu_reset_quiescent)begin
    bus_offset<=incoming_offset;bus_write<=hwrite;bus_size<=hsize;bus_align<=haddr[1:0];
    bus_roi<=address_in_window&&incoming_offset>=32'h1000;
    roi_word_active<=address_in_window&&incoming_offset>=32'h1000&&!hwrite;
    bus_state<=DECODE;
   end else begin bus_state<=IDLE;bus_roi<=0;roi_word_active<=0;end
  end
 endtask
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   bus_state<=IDLE;bus_offset<=0;bus_write<=0;bus_roi<=0;bus_size<=0;bus_align<=0;
   write_data<=0;read_data<=0;present<=0;active<=0;claimed<=0;result_pending<=0;
   ram_pending<=0;roi_word_active<=0;token<=0;target<=0;config_id<=0;descriptor_seq<=0;
   x0<=0;y0<=0;stride<=0;radius<=0;seen<=0;seen_epoch<=0;seen_job<=0;
   byte_index<=0;word_acc<=0;claim_epoch<=0;claim_source<=0;claim_job<=0;claim_mask<=0;
   quiet_epoch<=0;quiet_source<=0;quiet_job<=0;quiet_mask<=0;
   ret_epoch<=0;ret_source<=0;ret_job<=0;ret_target<=0;ret_config<=0;ret_crc<=0;ret_bytes<=0;ret_code<=0;ret_mask<=0;ret_psi_q8<=0;ret_psi_valid<=0;
   platform_armed<=0;release_pulse<=0;offer_rejected<=0;last_error<=0;checksum_crc32<=0;checksum_bytes<=0;checksum_code<=0;checksum_psi_q8<=0;checksum_psi_valid<=0;
  end else begin
   release_pulse<=0;offer_rejected<=0;
   if(offer_valid&&offer_ready)begin
    if(!fresh||!offer_format)begin offer_rejected<=1;last_error<=fresh?E_FORMAT:E_REPLAY;end
    else begin
     present<=1;active<=1;claimed<=0;result_pending<=0;token<=offer_token;target<=offer_target;config_id<=offer_config;
     x0<=offer_x0;y0<=offer_y0;stride<=offer_stride;radius<=offer_radius;descriptor_seq<=descriptor_seq+1'b1;
     seen<=1;seen_epoch<=offer_token[95:64];seen_job<=offer_token[31:0];claim_mask<=0;ret_mask<=0;quiet_mask<=0;ret_psi_q8<=0;ret_psi_valid<=0;
    end
   end
   if(present&&kill)begin active<=0;result_pending<=0;claim_mask<=0;ret_mask<=0;end
   if(cpu_reset_quiescent)begin
    active<=0;claimed<=0;result_pending<=0;claim_mask<=0;ret_mask<=0;quiet_mask<=0;
   end
   if(present&&!active&&!claimed&&!result_pending&&!ram_pending&&!roi_word_active)begin present<=0;release_pulse<=1;end
   if(checksum_result_valid&&checksum_result_ready)begin result_pending<=0;present<=0;release_pulse<=1;end
   if(cpu_reset_quiescent)begin
    // The sole outstanding native read has fixed one-cycle return. At this
    // edge it is drained/discarded; never clear a variable-latency transaction.
    ram_pending<=0;roi_word_active<=0;bus_state<=IDLE;read_data<=0;
   end else case(bus_state)
    IDLE:accept_address;
    DECODE:begin
     write_data<=hwdata;
     if(bus_align!=0)begin last_error<=E_ALIGN;bus_state<=ERR1;end
     else if(bus_size!=3'd2)begin last_error<=E_SIZE;bus_state<=ERR1;end
     else if(bus_offset>=32'h5000)begin last_error<=E_ADDRESS;bus_state<=ERR1;end
     else if(bus_write)bus_state<=RESP;
     else if(bus_roi)begin
      if(!read_allowed)begin last_error<=owner_visible?E_CLAIM:E_OWNER;bus_state<=ERR1;end
      else begin byte_index<=0;word_acc<=0;bus_state<=RREQ;end
     end else if(!register_readable(bus_offset))begin last_error<=E_ADDRESS;bus_state<=ERR1;end
     else begin read_data<=read_register(bus_offset);bus_state<=RESP;end
    end
    RREQ:if(read_allowed)begin ram_pending<=1;bus_state<=RWAIT;end
          else begin last_error<=E_REVOKED;bus_state<=ERR1;end
    RWAIT:begin
     ram_pending<=0;
     if(!read_allowed)begin last_error<=E_REVOKED;bus_state<=ERR1;end
     else begin
      case(byte_index)0:word_acc[7:0]<=roi_rd_data;1:word_acc[15:8]<=roi_rd_data;2:word_acc[23:16]<=roi_rd_data;3:word_acc[31:24]<=roi_rd_data;endcase
      if(byte_index==3)begin read_data<={roi_rd_data,word_acc[23:0]};bus_state<=RESP;end
      else begin byte_index<=byte_index+1'b1;bus_state<=RREQ;end
     end
    end
    RESP:begin
     if(bus_write)begin
      // Every final-commit attempt consumes its staged-body completeness bits.
      if(bus_offset=='h8c)claim_mask<=0;
      if(bus_offset=='h120)begin ret_mask<=0;ret_psi_valid<=0;end
      if(bus_offset=='h18c)quiet_mask<=0;
     end
     if(!hready)begin last_error<=bus_write?write_error:result_response_error;bus_state<=ERR2;end
     else begin
      if(bus_write)case(bus_offset)
       'h60:platform_armed<=1;
       'h80:begin claim_epoch<=write_data;claim_mask[0]<=1;end
       'h84:begin claim_source<=write_data;claim_mask[1]<=1;end
       'h88:begin claim_job<=write_data;claim_mask[2]<=1;end
       'h8c:begin claimed<=1;ret_psi_q8<=0;ret_psi_valid<=0;end
       'h100:begin ret_epoch<=write_data;ret_mask[0]<=1;end
       'h104:begin ret_source<=write_data;ret_mask[1]<=1;end
       'h108:begin ret_job<=write_data;ret_mask[2]<=1;end
       'h10c:begin ret_target<=write_data;ret_mask[3]<=1;end
       'h110:begin ret_config<=write_data;ret_mask[4]<=1;end
       'h114:begin ret_crc<=write_data;ret_mask[5]<=1;end
       'h118:begin ret_bytes<=write_data;ret_mask[6]<=1;end
       'h11c:begin ret_code<=write_data;ret_mask[7]<=1;end
       'h124:begin ret_psi_q8<=write_data[15:0];ret_psi_valid<=write_data[31];end
       'h120:begin
        checksum_psi_q8<=ret_psi_q8;checksum_psi_valid<=ret_psi_valid;
        checksum_crc32<=ret_crc;checksum_bytes<=ret_bytes;checksum_code<=ret_code;
        result_pending<=1;active<=0;claimed<=0;
       end
       'h180:begin quiet_epoch<=write_data;quiet_mask[0]<=1;end
       'h184:begin quiet_source<=write_data;quiet_mask[1]<=1;end
       'h188:begin quiet_job<=write_data;quiet_mask[2]<=1;end
       'h18c:begin active<=0;claimed<=0;result_pending<=0;end
       default:begin end
      endcase
      accept_address;
     end
    end
    ERR1:bus_state<=ERR2;
    ERR2:accept_address;
    default:bus_state<=IDLE;
   endcase
  end
 end
endmodule
