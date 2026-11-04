// Exact 192-pair metric; eight bounded ordered reads, no video interface.
// Each rd_req must produce exactly one ordered rd_valid OR rd_fault response.
// Cancel/fault drains outstanding responses before accepting another run.
// Missing responses fail closed in DRAIN; timeout never clears the ledger.
// Configuration builds 384 signed coordinate offsets with one shared 6x17 DSP
// and serial diameter shift/add. Count ties/thresholds are controller decisions.
module t06_pair_metric #(
 parameter PAIR_FILE="pair_base_rom.mem", parameter MAX_READ_WAIT=1024
)(
 input wire clk,rst_n,cancel,
 input wire cfg_start,input wire [9:0] cfg_diameter,input wire [2:0] cfg_roll_index,
 output reg cfg_done,output reg cfg_valid,
 input wire score_start,input wire [8:0] center_x,input wire [7:0] center_y,
 output wire busy,output reg score_done,output reg signed [8:0] score_count,
 output reg fault,
 output reg rd_req,output reg [15:0] rd_addr,
 input wire rd_valid,input wire [7:0] rd_data,input wire rd_fault,
 output reg [31:0] elapsed_cycles,output reg [31:0] read_requests
);
 localparam IDLE=0,CREQ=1,CLATCH=2,M0=3,M1=4,M2=5,M3=6,
            SCALE0=7,SCALE=8,CSTORE=9,OREQ=10,OUSE=11,RWAIT=12,DRAIN=13,HALT=14;
 reg [3:0] state;
 (* rom_style="dram" *)reg [24:0] pair_rom[0:191];
 (* ram_style="bram" *)reg [16:0] offset_ram[0:383];
 reg [24:0] pair_q;reg [16:0] offset_q;
 reg [8:0] index;
 reg signed [5:0] ux,uy;
 reg direction_positive;
 reg signed [16:0] cos_q,sin_q;
 reg signed [22:0] xc,ys,xs;
 reg signed [23:0] rot_x,rot_y;
 reg signed [34:0] sum_x,sum_y,shift_x,shift_y;
 reg [9:0] diameter,diameter_bits;reg [3:0] bit_index;
 reg [8:0] cx;reg [7:0] cy,pixel_a;reg [7:0] count;
 reg [15:0] read_wait;
 reg [9:0] fetch_index;
 reg [8:0] return_index,offset_index;
 reg prefetch_valid;
 reg [1:0] response_tags[0:7];
 reg [2:0] push_ptr,pop_ptr;
 reg [3:0] pending_count;
 wire response_event=rd_valid||rd_fault;
 wire retire=response_event&&pending_count!=0;
 wire signed [10:0] sample_x,sample_y;
 wire outside=sample_x<0||sample_x>=320||sample_y<0||sample_y>=180;
 wire response_error=rd_fault||(response_event&&pending_count==0);
 wire timed_out=pending_count!=0&&read_wait>=MAX_READ_WAIT-1;
 wire issue_fire=state==RWAIT&&prefetch_valid&&pending_count<8&&!outside&&!cancel&&!response_error&&!timed_out;
 wire prefetch_read=state==RWAIT&&(!prefetch_valid||issue_fire)&&fetch_index<384&&!cancel&&!response_error&&!timed_out;
 wire [3:0] after_retire=pending_count-(retire?4'd1:4'd0);
 wire response_b=response_tags[pop_ptr][1];
 wire response_positive=response_tags[pop_ptr][0];
 reg signed [5:0] mul_coord;reg signed [16:0] mul_trig;
 wire signed [22:0] mul_value=mul_coord*mul_trig;
 assign sample_x=$signed({2'b00,cx})+$signed({{3{offset_q[15]}},offset_q[15:8]});
 assign sample_y=$signed({3'b000,cy})+$signed({{3{offset_q[7]}},offset_q[7:0]});
 wire signed [8:0] difference=$signed({1'b0,pixel_a})-$signed({1'b0,rd_data});
 wire pair_match=response_positive?(difference>=9'sd6):(difference<= -9'sd6);
 assign busy=state!=IDLE;
 initial $readmemh(PAIR_FILE,pair_rom);
 function [33:0] trig;
  input [2:0] r;
  reg signed [16:0] c,s;
  begin
   case(r)
    0:begin c=17'sd32365;s=-17'sd5126;end
    1:begin c=17'sd32588;s=-17'sd3425;end
    2:begin c=17'sd32723;s=-17'sd1715;end
    3:begin c=17'sd32768;s=17'sd0;end
    4:begin c=17'sd32723;s=17'sd1715;end
    5:begin c=17'sd32588;s=17'sd3425;end
    default:begin c=17'sd32365;s=17'sd5126;end
   endcase
   trig={c,s};
  end
 endfunction
 wire [33:0] selected_trig=trig(cfg_roll_index);
 function signed [7:0] rne23;
  input signed [34:0] value;
  reg signed [34:0] floor_value,remainder;
  begin
   floor_value=value>>>23;remainder=value-(floor_value<<<23);
   if(remainder>35'sd4194304||(remainder==35'sd4194304&&floor_value[0]))floor_value=floor_value+1'b1;
   rne23=floor_value[7:0];
  end
 endfunction
 always @* begin
  mul_coord=ux;mul_trig=cos_q;
  case(state)
   M1:begin mul_coord=uy;mul_trig=sin_q;end
   M2:begin mul_coord=ux;mul_trig=sin_q;end
   M3:begin mul_coord=uy;mul_trig=cos_q;end
  endcase
 end
 always @(posedge clk) begin
  if(state==CREQ)pair_q<=pair_rom[index[8:1]];
  if(prefetch_read)offset_q<=offset_ram[fetch_index[8:0]];
  if(state==CSTORE)offset_ram[index]<={direction_positive,rne23(sum_x),rne23(sum_y)};
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=IDLE;cfg_done<=0;cfg_valid<=0;score_done<=0;score_count<=-1;fault<=0;
   rd_req<=0;rd_addr<=0;elapsed_cycles<=0;read_requests<=0;index<=0;
   ux<=0;uy<=0;direction_positive<=0;cos_q<=0;sin_q<=0;xc<=0;ys<=0;xs<=0;
   rot_x<=0;rot_y<=0;sum_x<=0;sum_y<=0;shift_x<=0;shift_y<=0;
   diameter<=0;diameter_bits<=0;bit_index<=0;cx<=0;cy<=0;pixel_a<=0;count<=0;read_wait<=0;
   fetch_index<=0;return_index<=0;offset_index<=0;prefetch_valid<=0;push_ptr<=0;pop_ptr<=0;pending_count<=0;
  end else begin
   cfg_done<=0;score_done<=0;fault<=0;rd_req<=0;
   if(state!=IDLE)elapsed_cycles<=elapsed_cycles+1'b1;
   // Preserve the outstanding ledger on cancellation. A new owner/run is
   // accepted only after every previously issued request is retired.
   if(retire)begin pop_ptr<=pop_ptr+1'b1;pending_count<=after_retire;end
   if(pending_count!=0)begin
    if(retire)read_wait<=0;else if(read_wait!=16'hffff)read_wait<=read_wait+1'b1;
   end else read_wait<=0;
   if(state==HALT)begin cfg_valid<=0;prefetch_valid<=0;end
   else if(cancel)begin
    state<=after_retire!=0?DRAIN:IDLE;cfg_valid<=0;score_count<=-1;rd_req<=0;prefetch_valid<=0;
   end else if(response_event&&pending_count==0)begin
    // The untagged external contract has been violated; do not relabel an
    // unsolicited late response as a new run. Only common reset recovers HALT.
    state<=HALT;cfg_valid<=0;prefetch_valid<=0;fault<=1;
   end
   else case(state)
    IDLE:begin
     if(cfg_start)begin
      cfg_valid<=0;elapsed_cycles<=0;index<=0;read_requests<=0;
      if(cfg_diameter<160||cfg_diameter>544||cfg_diameter[2:0]!=0||cfg_roll_index>6)begin cfg_done<=1;fault<=1;end
      else begin diameter<=cfg_diameter;cos_q<=selected_trig[33:17];sin_q<=selected_trig[16:0];state<=CREQ;end
     end else if(score_start)begin
      elapsed_cycles<=0;read_requests<=0;count<=0;index<=0;cx<=center_x;cy<=center_y;score_count<=-1;
      fetch_index<=0;return_index<=0;offset_index<=0;prefetch_valid<=0;push_ptr<=0;pop_ptr<=0;pending_count<=0;
      if(!cfg_valid)begin score_done<=1;fault<=1;end
      else if(center_x>=320||center_y>=180)score_done<=1;
      else state<=RWAIT;
     end
    end
    CREQ:state<=CLATCH;
    CLATCH:begin
     ux<=index[0]?$signed(pair_q[12:7]):$signed(pair_q[24:19]);
     uy<=index[0]?$signed(pair_q[6:1]):$signed(pair_q[18:13]);
     direction_positive<=pair_q[0];state<=M0;
    end
    M0:begin xc<=mul_value;state<=M1;end
    M1:begin ys<=mul_value;state<=M2;end
    M2:begin xs<=mul_value;state<=M3;end
    M3:begin rot_x<=$signed({xc[22],xc})-$signed({ys[22],ys});rot_y<=$signed({xs[22],xs})+$signed({mul_value[22],mul_value});state<=SCALE0;end
    SCALE0:begin
     sum_x<=0;sum_y<=0;shift_x<={{11{rot_x[23]}},rot_x};shift_y<={{11{rot_y[23]}},rot_y};
     diameter_bits<=diameter;bit_index<=0;state<=SCALE;
    end
    SCALE:begin
     if(diameter_bits[0])begin sum_x<=sum_x+shift_x;sum_y<=sum_y+shift_y;end
     shift_x<=shift_x<<<1;shift_y<=shift_y<<<1;diameter_bits<=diameter_bits>>1;
     if(bit_index==9)state<=CSTORE;else bit_index<=bit_index+1'b1;
    end
    CSTORE:begin
     if(index==383)begin cfg_valid<=1;cfg_done<=1;state<=IDLE;end
     else begin index<=index+1'b1;state<=CREQ;end
    end
    RWAIT:begin
     if(response_error||timed_out)begin
      score_count<=-1;score_done<=1;fault<=1;cfg_valid<=0;prefetch_valid<=0;
      state<=after_retire!=0?DRAIN:IDLE;
     end else if(prefetch_valid&&outside)begin
      score_count<=-1;score_done<=1;prefetch_valid<=0;
      state<=after_retire!=0?DRAIN:IDLE;
     end else begin
      if(issue_fire)begin
       rd_addr<={sample_y[7:0],8'b0}+{2'b0,sample_y[7:0],6'b0}+{7'd0,sample_x[8:0]};
       rd_req<=1;read_requests<=read_requests+1'b1;
       response_tags[push_ptr]<={offset_index[0],offset_q[16]};push_ptr<=push_ptr+1'b1;
       pending_count<=after_retire+1'b1;prefetch_valid<=0;
      end
      if(prefetch_read)begin
       offset_index<=fetch_index[8:0];fetch_index<=fetch_index+1'b1;prefetch_valid<=1;
      end
      if(retire&&rd_valid)begin
       if(!response_b)pixel_a<=rd_data;
       else if(pair_match)count<=count+1'b1;
       if(return_index==383)begin
        score_count<=$signed({1'b0,count})+(pair_match?9'sd1:9'sd0);score_done<=1;
        state<=IDLE;prefetch_valid<=0;
       end else return_index<=return_index+1'b1;
      end
     end
    end
    DRAIN:begin
     // read_wait may saturate; no watchdog is allowed to erase pending_count.
     prefetch_valid<=0;
     if(after_retire==0)state<=IDLE;
    end
    HALT:begin cfg_valid<=0;prefetch_valid<=0;end
    default:begin state<=IDLE;cfg_valid<=0;fault<=1;end
   endcase
  end
 end
endmodule
