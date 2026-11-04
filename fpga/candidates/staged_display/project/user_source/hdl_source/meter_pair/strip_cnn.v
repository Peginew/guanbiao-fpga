// Complete fixed strip CNN:2x32x9 ->Conv4x16x9 ->Conv4x8x9 ->sum9 S16
// ->FC32x8 ReLU ->FC8x2 S16. ALL four trained layers execute.
// No camera/DDR/video access. Source-bound576byte input is owned by one token.
module strip_cnn #(
 parameter MODEL_FILE="strip_model.hex",parameter MAX_JOB_CYCLES=200000
)(input wire clk,rst_n,cancel,
 input wire cmd_valid,output wire cmd_ready,input wire[95:0]cmd_token,
 input wire s_valid,output wire s_ready,input wire[95:0]s_token,input wire[7:0]s_data,input wire s_last,
 output reg m_valid,input wire m_ready,output reg[95:0]m_token,
 output reg signed[15:0]m_logit0,m_logit1,output reg[3:0]m_error,output wire m_q_valid,
 output reg busy,cancelled,output reg[31:0]cycles,
 output reg trace_valid,output reg[2:0]trace_kind,output reg[9:0]trace_index,output reg signed[15:0]trace_value);
 localparam IDLE=0,LOAD=1,PARAM_REQ=2,PARAM_WAIT=3,PARAM_USE=4,OUT_INIT=5,
  MAC_REQ=6,MAC_WAIT=7,MAC_X=8,MAC_HI_WAIT=9,MAC_HI_USE=10,MAC_MUL=11,MAC_ADD=12,
  RQ_SEND=13,RQ_WAIT=14,ADVANCE=15,POOL_REQ=16,POOL_WAIT=17,POOL_USE=18,POOL_WRITE_LO=19,POOL_WRITE_HI=20,RESULT=21;
 reg[4:0]state;reg[1:0]layer;reg[3:0]oc,oy,ox;reg[5:0]term_index;
 reg[1:0]ic,ky,kx;reg[3:0]parameter_index;reg[9:0]loaded;
 reg seen;reg[31:0]seen_epoch,seen_job;
 wire[31:0]epoch_delta=cmd_token[95:64]-seen_epoch,job_delta=cmd_token[31:0]-seen_job;
 wire cmd_fresh=!seen||(cmd_token[95:64]==seen_epoch?(job_delta!=0&&!job_delta[31]):(epoch_delta!=0&&!epoch_delta[31]));
 assign cmd_ready=rst_n&&!cancel&&state==IDLE;assign s_ready=rst_n&&!cancel&&state==LOAD;
 assign m_q_valid=rst_n&&!cancel&&m_valid&&m_error==0;
 reg[7:0]coefficients[0:1023]; // synthesis ram_style=bram
 reg[7:0]activation[0:2047]; // synthesis ram_style=bram
 initial $readmemh(MODEL_FILE,coefficients);
 reg[9:0]coefficient_address;reg[7:0]coefficient_q,activation_q;
 reg[10:0]activation_address;reg zero_sample;reg[7:0]activation_low;
 reg signed[15:0]x_operand;reg signed[23:0]product_q;
 reg signed[31:0]bias,acc;reg[31:0]multiplier;reg[5:0]shift;
 wire[4:0]global_neuron=layer==0?{1'b0,oc}:layer==1?5'd4+oc:layer==2?5'd8+oc:5'd16+oc;
 wire[5:0]terms=layer==0?18:layer==1?36:layer==2?32:8;
 wire signed[6:0]sample_y=($signed({2'b0,oy})<<<1)+$signed({5'b0,ky})-7'sd1;
 wire signed[5:0]sample_x=$signed({2'b0,ox})+$signed({4'b0,kx})-6'sd1;
 wire sample_inside=sample_x>=0&&sample_x<9&&sample_y>=0&&sample_y<(layer==0?32:16);
 wire[10:0]sample_y9=({4'b0,sample_y[6:0]}<<3)+{4'b0,sample_y[6:0]};
 wire[10:0]sample_address=layer==0?(({9'b0,ic}<<8)+({9'b0,ic}<<5)+sample_y9+sample_x):
                                 (11'd576+({9'b0,ic}<<7)+({9'b0,ic}<<4)+sample_y9+sample_x);
 wire[9:0]weight_base=layer==0?({6'd0,oc}<<4)+({6'd0,oc}<<1):
                          layer==1?10'd72+({6'd0,oc}<<5)+({6'd0,oc}<<2):
                          layer==2?10'd216+({6'd0,oc}<<5):10'd472+({6'd0,oc}<<3);
 wire[10:0]output_address=layer==0?11'd576+({7'd0,oc}<<7)+({7'd0,oc}<<4)+({7'd0,oy}<<3)+oy+ox:
                         layer==1?({7'd0,oc}<<6)+({7'd0,oc}<<3)+({7'd0,oy}<<3)+oy+ox:{7'd0,oc};
 wire[9:0]output_index=layer==0?(({6'd0,oc}<<7)+({6'd0,oc}<<4)+({6'd0,oy}<<3)+oy+ox):
                        layer==1?(({6'd0,oc}<<6)+({6'd0,oc}<<3)+({6'd0,oy}<<3)+oy+ox):{6'd0,oc};
 (* dsp_style="yes" *)wire signed[23:0]product=x_operand*$signed(coefficient_q);
 wire signed[32:0]sum=$signed({acc[31],acc})+$signed({{9{product_q[23]}},product_q});
 wire rq_ready,rq_valid;wire signed[15:0]rq_q;wire[3:0]rq_error;
 wire rq_abort=cancel||(state==RESULT&&m_error!=0);
 strip_requant rq(.clk(clk),.rst_n(rst_n),.cancel(rq_abort),.in_valid(state==RQ_SEND),.in_ready(rq_ready),
  .in_acc(acc),.in_multiplier(multiplier),.in_shift(shift),.in_wide(layer==3),.out_valid(rq_valid),.out_ready(state==RQ_WAIT),.out_q(rq_q),.out_error(rq_error));
 wire signed[15:0]activated=layer==3?rq_q:rq_q[15]?16'sd0:rq_q;
 reg[5:0]pool_index;reg[3:0]pool_column;reg[15:0]pool_sum;
 wire[10:0]pool_read_address=({5'd0,pool_index}<<3)+pool_index+pool_column;
 wire[10:0]pool_write_address=11'd576+{4'd0,pool_index,1'b0};
 wire activation_ren=(state==MAC_WAIT&&!zero_sample)||state==MAC_HI_WAIT||state==POOL_WAIT;
 wire[10:0]activation_raddr=state==POOL_WAIT?pool_read_address:state==MAC_HI_WAIT?activation_address+1'b1:activation_address;
 reg activation_wen;reg[10:0]activation_waddr;reg[7:0]activation_wdata;
 always@*begin
  activation_wen=0;activation_waddr=0;activation_wdata=0;
  if(rst_n&&!cancel)case(state)
   LOAD:if(s_valid&&s_ready&&s_token==m_token&&s_last==(loaded==575))begin activation_wen=1;activation_waddr={1'b0,loaded};activation_wdata=s_data;end
   RQ_WAIT:if(rq_valid&&rq_error==0&&layer!=3)begin activation_wen=1;activation_waddr=output_address;activation_wdata=activated[7:0];end
   POOL_WRITE_LO:begin activation_wen=1;activation_waddr=pool_write_address;activation_wdata=pool_sum[7:0];end
   POOL_WRITE_HI:begin activation_wen=1;activation_waddr=pool_write_address+1'b1;activation_wdata=pool_sum[15:8];end
   default:begin end
  endcase
 end
 always@(posedge clk)begin
  if(state==PARAM_WAIT||state==MAC_WAIT)coefficient_q<=coefficients[coefficient_address];
  if(activation_ren)activation_q<=activation[activation_raddr];
  if(activation_wen)activation[activation_waddr]<=activation_wdata;
 end
 task fail;input[3:0]code;begin state<=RESULT;busy<=0;m_valid<=1;m_error<=code;m_logit0<=0;m_logit1<=0;end endtask
 always@(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=IDLE;layer<=0;oc<=0;oy<=0;ox<=0;term_index<=0;ic<=0;ky<=0;kx<=0;parameter_index<=0;loaded<=0;
   seen<=0;seen_epoch<=0;seen_job<=0;coefficient_address<=0;activation_address<=0;zero_sample<=0;activation_low<=0;x_operand<=0;product_q<=0;
   bias<=0;acc<=0;multiplier<=0;shift<=0;pool_index<=0;pool_column<=0;pool_sum<=0;
   m_valid<=0;m_token<=0;m_logit0<=0;m_logit1<=0;m_error<=0;busy<=0;cancelled<=0;cycles<=0;
   trace_valid<=0;trace_kind<=0;trace_index<=0;trace_value<=0;
  end else begin
   trace_valid<=0;cancelled<=0;if(busy)cycles<=cycles+1'b1;
   if(cancel)begin state<=IDLE;busy<=0;m_valid<=0;m_logit0<=0;m_logit1<=0;m_error<=5;cancelled<=1;end
   else if(busy&&cycles>=MAX_JOB_CYCLES)fail(3);
   else case(state)
    IDLE:if(cmd_valid&&cmd_ready)begin
     m_token<=cmd_token;m_valid<=0;m_logit0<=0;m_logit1<=0;m_error<=0;cycles<=0;
     if(!cmd_fresh)fail(1);
     else begin seen<=1;seen_epoch<=cmd_token[95:64];seen_job<=cmd_token[31:0];loaded<=0;busy<=1;state<=LOAD;end
    end
    LOAD:if(s_valid&&s_ready)begin
     if(s_token!=m_token||s_last!=(loaded==575))fail(4);
     else if(loaded==575)begin layer<=0;oc<=0;oy<=0;ox<=0;parameter_index<=0;state<=PARAM_REQ;end
     else loaded<=loaded+1'b1;
    end
    PARAM_REQ:begin
     if(parameter_index<4)coefficient_address<=10'd488+{global_neuron,2'b0}+parameter_index;
     else if(parameter_index<8)coefficient_address<=10'd560+{global_neuron,2'b0}+parameter_index-4;
     else coefficient_address<=10'd632+global_neuron;
     state<=PARAM_WAIT;
    end
    PARAM_WAIT:state<=PARAM_USE;
    PARAM_USE:begin
     case(parameter_index)
      0:bias[7:0]<=coefficient_q;1:bias[15:8]<=coefficient_q;2:bias[23:16]<=coefficient_q;3:bias[31:24]<=coefficient_q;
      4:multiplier[7:0]<=coefficient_q;5:multiplier[15:8]<=coefficient_q;6:multiplier[23:16]<=coefficient_q;7:multiplier[31:24]<=coefficient_q;
      8:shift<=coefficient_q[5:0];
     endcase
     if(parameter_index==8)begin if(coefficient_q[7:6]!=0||multiplier[31])fail(1);else state<=OUT_INIT;end
     else begin parameter_index<=parameter_index+1'b1;state<=PARAM_REQ;end
    end
    OUT_INIT:begin acc<=bias;term_index<=0;ic<=0;ky<=0;kx<=0;state<=MAC_REQ;end
    MAC_REQ:begin
     coefficient_address<=weight_base+term_index;
     zero_sample<=layer<2&&!sample_inside;
     activation_address<=layer<2?sample_address:layer==2?11'd576+{4'b0,term_index,1'b0}:{5'd0,term_index};
     state<=MAC_WAIT;
    end
    MAC_WAIT:state<=MAC_X;
    MAC_X:begin
     if(layer==2)begin activation_low<=activation_q;state<=MAC_HI_WAIT;end
     else begin x_operand<=zero_sample?0:$signed(activation_q);state<=MAC_MUL;end
    end
    MAC_HI_WAIT:state<=MAC_HI_USE;
    MAC_HI_USE:begin x_operand<=$signed({activation_q,activation_low});state<=MAC_MUL;end
    MAC_MUL:begin product_q<=product;state<=MAC_ADD;end
    MAC_ADD:begin
     if(sum[32]!=sum[31])fail(2);
     else begin
      acc<=sum[31:0];
      if(term_index+1==terms)state<=RQ_SEND;
      else begin
       term_index<=term_index+1'b1;
       if(layer<2)begin if(kx==2)begin kx<=0;if(ky==2)begin ky<=0;ic<=ic+1'b1;end else ky<=ky+1'b1;end else kx<=kx+1'b1;end
       state<=MAC_REQ;
      end
     end
    end
    RQ_SEND:if(rq_ready)state<=RQ_WAIT;
    RQ_WAIT:if(rq_valid)begin
     if(rq_error!=0)fail(1);
     else begin
      trace_valid<=1;trace_kind<=layer<2?{1'b0,layer}:layer==2?3'd3:3'd4;trace_index<=output_index;trace_value<=activated;
      if(layer==3)begin
       if(oc==0)m_logit0<=activated;else m_logit1<=activated;
       if(oc==1)begin m_valid<=1;busy<=0;state<=RESULT;end else begin oc<=1;parameter_index<=0;state<=PARAM_REQ;end
      end else state<=ADVANCE;
     end
    end
    ADVANCE:begin
     if(layer<2)begin
      if(ox<8)begin ox<=ox+1'b1;state<=OUT_INIT;end
      else if(oy<(layer==0?15:7))begin ox<=0;oy<=oy+1'b1;state<=OUT_INIT;end
      else if(oc<3)begin ox<=0;oy<=0;oc<=oc+1'b1;parameter_index<=0;state<=PARAM_REQ;end
      else if(layer==0)begin layer<=1;oc<=0;oy<=0;ox<=0;parameter_index<=0;state<=PARAM_REQ;end
      else begin pool_index<=0;pool_column<=0;pool_sum<=0;state<=POOL_REQ;end
     end else if(oc<7)begin oc<=oc+1'b1;parameter_index<=0;state<=PARAM_REQ;end
     else begin layer<=3;oc<=0;parameter_index<=0;state<=PARAM_REQ;end
    end
    POOL_REQ:state<=POOL_WAIT;
    POOL_WAIT:state<=POOL_USE;
    POOL_USE:begin pool_sum<=pool_sum+{8'd0,activation_q};if(pool_column==8)state<=POOL_WRITE_LO;else begin pool_column<=pool_column+1'b1;state<=POOL_REQ;end end
    POOL_WRITE_LO:state<=POOL_WRITE_HI;
    POOL_WRITE_HI:begin
     trace_valid<=1;trace_kind<=2;trace_index<={4'd0,pool_index};trace_value<=pool_sum;
     if(pool_index==31)begin layer<=2;oc<=0;parameter_index<=0;state<=PARAM_REQ;end
     else begin pool_index<=pool_index+1'b1;pool_column<=0;pool_sum<=0;state<=POOL_REQ;end
    end
    RESULT:if(m_ready)begin m_valid<=0;state<=IDLE;end
    default:fail(6);
   endcase
  end
 end
endmodule
