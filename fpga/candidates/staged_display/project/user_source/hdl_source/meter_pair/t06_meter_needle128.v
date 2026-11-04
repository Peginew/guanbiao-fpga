// Budget128rawROI thin-ray candidate,360angles/32radii/5 nearest samples.
// This differs from old192canonical720bilinear kernel and has NO READ output.
// Source identity,quality,pose,calibration and history are external gates.
module t06_meter_needle128 #(
 parameter TRIG_FILE="needle_trig128.hex"
)(
 input wire clk,rst_n,start,cancel,
 input wire [6:0] hub_x,hub_y,radius,input wire [4:0] hub_radius,
 output wire rd_en,output wire [13:0] rd_addr,input wire [7:0] rd_data,
 output reg busy,done,candidate,output reg [8:0] angle,
 output reg [6:0] length,output reg [5:0] count,
 output reg [4:0] reason,output reg [31:0] cycles,
 output reg row_valid,output reg [8:0] row_angle,
 output reg [15:0] row_score,output reg [6:0] row_length,output reg [5:0] row_count,row_last,
 output reg row_qualified,
 // Private second phase reuses the exact ray address arithmetic and ROM.
 // CHW forward288 then reverse288 S8 bytes; no new frame or ROI ownership.
 input wire sample_start,input wire sample_ready,
 output reg sample_valid,output reg [7:0] sample_data,output reg sample_last,
 output reg sample_done,sample_error
);
 localparam IDLE=0,ANGLE_REQ=1,ANGLE_INIT=2,RAD_MUL=3,COORD=4,ISSUE=5,WAIT_RD=6,GET=7,
  STRIPE=8,STORE=9,NEXT_ANGLE=10,REVERSE_REQ=11,REVERSE_USE=12,COMPARE_REQ=13,COMPARE_USE=14,FINISH=15,SAMPLE_SEND=16;
 reg [4:0] state;reg sampling_mode,sample_reverse;
 reg [23:0] trig[0:511]; // synthesis ram_style=bram
 reg [35:0] rows[0:511]; // score16,length7,count6,last6,qualified1
 reg [23:0] tq;reg [35:0] rq;
 initial $readmemh(TRIG_FILE,trig,0,359);
 reg signed [11:0] cs,sn;
 reg signed [28:0] xp,yp;
 reg signed [29:0] xq,yq;
 reg [6:0] hx,hy,rmax,rfull;
 reg [7:0] rstart_latched;
 reg [14:0] radial_q8,step_q8;
 reg [4:0] step_rem,radial_rem;
 reg [5:0] radial_index,last_index,hits;
 reg have_hit,qualified_any;
 reg [3:0] stripe_index;
 reg [7:0] stripe[0:4];
 reg [8:0] ai,compare_index;
 reg [15:0] total,best,best_any;
 reg [8:0] any_angle;
 reg [6:0] ending,reverse_length;
 reg competition,reverse_ok;
 wire [7:0] mid_min=(stripe[1]<stripe[2]?(stripe[1]<stripe[3]?stripe[1]:stripe[3]):(stripe[2]<stripe[3]?stripe[2]:stripe[3]));
 wire [7:0] mid_max=(stripe[1]>stripe[2]?(stripe[1]>stripe[3]?stripe[1]:stripe[3]):(stripe[2]>stripe[3]?stripe[2]:stripe[3]));
 wire [7:0] side_min=stripe[0]<stripe[4]?stripe[0]:stripe[4];
 wire signed [10:0] contrast=$signed({3'b0,side_min})-$signed({3'b0,mid_min});
 // Both far flanks must be brighter than the thin center: a one-sided
 // edge of the thick reverse counterweight cannot meet this condition.
 wire hit=contrast>8;
 reg [6:0] misses;
 wire [6:0] next_misses={misses[5:0],!hit};
 wire [3:0] miss_count={3'b0,next_misses[0]}+{3'b0,next_misses[1]}+{3'b0,next_misses[2]}+{3'b0,next_misses[3]}+{3'b0,next_misses[4]}+{3'b0,next_misses[5]}+{3'b0,next_misses[6]};
 wire stop_ray=radial_index>=6&&miss_count>=5;
 wire [15:0] positive=contrast>0?{5'd0,contrast}:16'd0;
 wire [8:0] score_angle=state==REVERSE_REQ?(angle>=180?angle-180:angle+180):compare_index;
 wire [8:0] sep0=compare_index>=angle?compare_index-angle:angle-compare_index;
 wire [8:0] sep=sep0>180?360-sep0:sep0;
 wire [8:0] revsep=sep>=180?sep-180:180-sep;
 wire [15:0] qscore=rq[35:20];wire [6:0] qlength=rq[19:13];wire qqualified=rq[0];
 function [22:0] times100;input [15:0] x;begin times100=({7'd0,x}<<6)+({7'd0,x}<<5)+({7'd0,x}<<2);end endfunction
 function [22:0] times52;input [15:0] x;begin times52=({7'd0,x}<<5)+({7'd0,x}<<4)+({7'd0,x}<<2);end endfunction
 function [22:0] times56;input [15:0] x;begin times56=({7'd0,x}<<5)+({7'd0,x}<<4)+({7'd0,x}<<3);end endfunction
 function [22:0] times118;input [15:0] x;begin times118=({7'd0,x}<<6)+({7'd0,x}<<5)+({7'd0,x}<<4)+({7'd0,x}<<2)+({7'd0,x}<<1);end endfunction
 function [22:0] times82;input [15:0] x;begin times82=({7'd0,x}<<6)+({7'd0,x}<<4)+({7'd0,x}<<1);end endfunction
 wire ray_qualified=have_hit&&times100({9'd0,ending})>=times52({9'd0,rfull})&&times100({10'd0,hits})>=times56({10'd0,last_index}+1'b1)&&hits>=12;
 reg signed [3:0] cross_offset;
 always @*begin
  if(sampling_mode)cross_offset=$signed(stripe_index)-4'sd4;
  else case(stripe_index)0:cross_offset=-2;1:cross_offset=-1;2:cross_offset=0;3:cross_offset=1;default:cross_offset=2;endcase
 end
 wire signed [15:0] cross_x=sn*cross_offset;
 wire signed [15:0] cross_y=cs*cross_offset;
 wire signed [29:0] coord_x=$signed({1'b0,hx,18'b0})+$signed(xp)-($signed({{14{cross_x[15]}},cross_x})<<<8)+30'sd131072;
 wire signed [29:0] coord_y=$signed({1'b0,hy,18'b0})+$signed(yp)+($signed({{14{cross_y[15]}},cross_y})<<<8)+30'sd131072;
 assign rd_addr={yq[24:18],xq[24:18]};
 assign rd_en=rst_n&&busy&&state==ISSUE;
 wire [7:0] start_r=hub_radius+3>8?hub_radius+3:8;
 wire [7:0] end_r=(radius*7)>>3;
 wire [14:0] distance_q8=(end_r-start_r)<<8;
 always @(posedge clk)begin
  if(rst_n&&state==ANGLE_REQ)tq<=trig[ai];
  if(rst_n&&state==STORE)rows[ai]<={total,ending,hits,last_index,ray_qualified};
  if(rst_n&&(state==REVERSE_REQ||state==COMPARE_REQ))rq<=rows[score_angle];
 end
 integer k;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=IDLE;sampling_mode<=0;sample_reverse<=0;sample_valid<=0;sample_data<=0;sample_last<=0;sample_done<=0;sample_error<=0;busy<=0;done<=0;candidate<=0;angle<=0;length<=0;count<=0;reason<=0;cycles<=0;
   cs<=0;sn<=0;xp<=0;yp<=0;xq<=0;yq<=0;hx<=0;hy<=0;rmax<=0;rfull<=0;rstart_latched<=0;radial_q8<=0;step_q8<=0;step_rem<=0;radial_rem<=0;
   radial_index<=0;last_index<=0;hits<=0;have_hit<=0;qualified_any<=0;stripe_index<=0;ai<=0;compare_index<=0;
   total<=0;best<=0;best_any<=0;any_angle<=0;ending<=0;reverse_length<=0;competition<=0;reverse_ok<=0;misses<=0;
   row_valid<=0;row_angle<=0;row_score<=0;row_length<=0;row_count<=0;row_last<=0;row_qualified<=0;
   for(k=0;k<5;k=k+1)stripe[k]<=0;
  end else begin
   done<=0;row_valid<=0;sample_done<=0;if(busy)cycles<=cycles+1'b1;
   if(cancel)begin state<=IDLE;sampling_mode<=0;sample_valid<=0;sample_last<=0;busy<=0;candidate<=0;reason<=3;end
   else case(state)
    IDLE:if(sample_start)begin
     sample_valid<=0;sample_last<=0;sample_error<=0;sample_reverse<=0;
     if(!candidate)begin sample_done<=1;sample_error<=1;end
     else begin sampling_mode<=1;ai<=angle;busy<=1;state<=ANGLE_REQ;end
    end else if(start)begin
     sampling_mode<=0;sample_valid<=0;sample_error<=0;
     candidate<=0;best<=0;best_any<=0;qualified_any<=0;any_angle<=0;angle<=0;length<=0;count<=0;cycles<=0;
     if(radius<40||radius>62||hub_x<48||hub_x>79||hub_y<48||hub_y>79||end_r<=start_r)begin done<=1;reason<=1;end
     else begin hx<=hub_x;hy<=hub_y;rmax<=end_r;rfull<=radius;rstart_latched<=start_r;ai<=0;state<=ANGLE_REQ;busy<=1;reason<=0;
      step_q8<=distance_q8/31;step_rem<=distance_q8%31;end
    end
    ANGLE_REQ:state<=ANGLE_INIT;
    ANGLE_INIT:begin
     cs<=tq[23:12];sn<=tq[11:0];radial_q8<=rstart_latched<<8;radial_rem<=15;radial_index<=0;
     stripe_index<=0;last_index<=0;hits<=0;have_hit<=0;total<=0;ending<=0;misses<=0;state<=RAD_MUL;
    end
    RAD_MUL:begin xp<=cs*$signed({1'b0,radial_q8});yp<=sn*$signed({1'b0,radial_q8});state<=COORD;end
    COORD:begin xq<=coord_x;yq<=coord_y;state<=ISSUE;end
    ISSUE:begin
     if(xq<0||yq<0||xq>=30'sd33554432||yq>=30'sd33554432)begin busy<=0;state<=IDLE;
      if(sampling_mode)begin sample_valid<=0;sample_done<=1;sample_error<=1;sampling_mode<=0;end
      else begin done<=1;candidate<=0;reason<=2;end
     end
     else state<=WAIT_RD;
    end
    WAIT_RD:state<=GET;
    GET:if(sampling_mode)begin
     sample_data<=rd_data^8'h80;sample_valid<=1;
     sample_last<=sample_reverse&&radial_index==31&&stripe_index==8;state<=SAMPLE_SEND;
    end else begin
     stripe[stripe_index]<=rd_data;
     if(stripe_index==4)state<=STRIPE;
     else begin stripe_index<=stripe_index+1'b1;state<=COORD;end
    end
    STRIPE:begin
     if(stop_ray)state<=STORE;
     else begin
      misses<=next_misses;
      if(hit)begin have_hit<=1;last_index<=radial_index;ending<=radial_q8>>8;hits<=hits+1'b1;end
      if(radial_index>=3)total<=total+positive;
      if(radial_index==31)state<=STORE;
      else begin
       radial_index<=radial_index+1'b1;stripe_index<=0;
       if({1'b0,radial_rem}+{1'b0,step_rem}>=31)begin radial_q8<=radial_q8+step_q8+1'b1;radial_rem<=radial_rem+step_rem-31;end
       else begin radial_q8<=radial_q8+step_q8;radial_rem<=radial_rem+step_rem;end
       state<=RAD_MUL;
      end
     end
    end
    SAMPLE_SEND:if(sample_valid&&sample_ready)begin
     sample_valid<=0;sample_last<=0;
     if(stripe_index!=8)begin stripe_index<=stripe_index+1'b1;state<=COORD;end
     else if(radial_index!=31)begin
      radial_index<=radial_index+1'b1;stripe_index<=0;
      if({1'b0,radial_rem}+{1'b0,step_rem}>=31)begin radial_q8<=radial_q8+step_q8+1'b1;radial_rem<=radial_rem+step_rem-31;end
      else begin radial_q8<=radial_q8+step_q8;radial_rem<=radial_rem+step_rem;end
      state<=RAD_MUL;
     end else if(!sample_reverse)begin
      sample_reverse<=1;ai<=angle>=180?angle-180:angle+180;state<=ANGLE_REQ;
     end else begin sampling_mode<=0;busy<=0;sample_done<=1;state<=IDLE;end
    end
    STORE:begin
     row_valid<=1;row_angle<=ai;row_score<=total;row_length<=ending;row_count<=hits;row_last<=last_index;row_qualified<=ray_qualified;
     if(total>best_any)begin best_any<=total;any_angle<=ai;end
     if(ray_qualified&&(!qualified_any||total>best))begin qualified_any<=1;best<=total;angle<=ai;length<=ending;count<=hits;end
     state<=NEXT_ANGLE;
    end
    NEXT_ANGLE:if(ai==359)begin
     if(!qualified_any)begin angle<=any_angle;candidate<=0;reason<=4;busy<=0;done<=1;state<=IDLE;end
     else state<=REVERSE_REQ;
    end else begin ai<=ai+1'b1;state<=ANGLE_REQ;end
    REVERSE_REQ:state<=REVERSE_USE;
    REVERSE_USE:begin reverse_length<=qlength;reverse_ok<=times100({9'd0,length})>=times118({9'd0,qlength});compare_index<=0;competition<=0;state<=COMPARE_REQ;end
    COMPARE_REQ:state<=COMPARE_USE;
    COMPARE_USE:begin
     if(qqualified&&sep>12&&revsep>18&&times100(qscore)>=times82(best))competition<=1;
     if(compare_index==359)state<=FINISH;else begin compare_index<=compare_index+1'b1;state<=COMPARE_REQ;end
    end
    FINISH:begin busy<=0;done<=1;candidate<=reverse_ok&&!competition;reason<=!reverse_ok?5:competition?6:0;state<=IDLE;end
    default:begin state<=IDLE;busy<=0;candidate<=0;reason<=7;end
   endcase
  end
 end
endmodule
