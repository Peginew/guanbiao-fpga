// Uses a bounded pipelined metric; waits for cancel/fault drains before reuse.
// Wide128 hierarchical TRACK:289 full192 screen +2*(25centers*15poses).
// Dedicated SEARCH and same-target fresh-frame TRACK, one serial metric only.
// SEARCH:33poses*Top16 ->528pool ->two seeds ->30 fine maxima.
// TRACK:local original printed-pair evidence, fresh source and existing lock.
// A constructed square bbox NEVER asserts physical pose, focus, stop or READ.
module t06_pair_search #(
 parameter PAIR_FILE="C:/Users/Edward/Desktop/FPGA/Stable3s_Rover_Merged_20261104/fpga/project/user_source/hdl_source/meter_pair/pair_base_rom.mem",parameter MAX_RUN_CYCLES=1500000000,
 parameter MAX_LOCK_GAP_CYCLES=1500000000,parameter MAX_TRACK_USES=7
)(
 input wire clk,rst_n,cancel,
 input wire start,input wire track_mode,
 input wire owner_valid,input wire [31:0] owner_source,owner_epoch,owner_cfg,owner_lease,owner_age,
 output reg busy,output reg done,output reg fault,
 output reg candidate_valid,output reg partial,
 output reg [7:0] best_count,output reg signed [8:0] far_margin_count,
 output reg margin_valid,output reg fresh_track_confirm,
 output reg [10:0] box_x0,box_x1,center_x,
 output reg [9:0] box_y0,box_y1,center_y,diameter,
 output reg [8:0] low_center_x,output reg [7:0] low_center_y,output reg [2:0] roll_index,
 output reg [31:0] result_source,result_epoch,result_cfg,result_lease,result_age,actual_cycles,
 output reg [31:0] gray_reads,evaluated_positions,
 output reg [3:0] reason,output reg global_lock,output wire reacquire_due,
 output reg [31:0] target_id,
 output wire rd_req,output wire [15:0] rd_addr,output wire [31:0] rd_lease,
 input wire rd_valid,input wire [7:0] rd_data,input wire rd_fault
);
 localparam IDLE=0,CLEAR=1,CONFIG=2,CFGWAIT=3,SCORE=4,SWAIT=5,
            MIN_INIT=6,MIN_SCAN=7,MIN_STORE=8,NEXTXY=9,POOL_WRITE=10,
            PREQ=11,PUSE=12,POSE_END=13,FPOOL_WRITE=14,FPREQ=15,FPUSE=16,FINISH=17,MIN_REQ=18,MIN_USE=19;
 localparam COARSE=0,FINE=1,LOCAL=2,HCOARSE=3;
 reg [4:0] state;reg [1:0] phase;
 reg mode,planned_recheck;reg [31:0] held_source,held_epoch,held_cfg,held_lease;
 reg [31:0] lock_source,lock_epoch,lock_cfg,lock_age;reg [15:0] track_uses;
 reg [35:0] lock_desc,seed0,seed1,overall_best,far_best,pose_best;
 (* ram_style="bram" *)reg [35:0] pool[0:527];reg [35:0] pool_q;
 reg [5:0] coarse_config;reg [3:0] coarse_d;reg [1:0] coarse_r;
 reg [3:0] list_index,min_index;reg [35:0] min_word,pending_desc;
 reg [9:0] pool_index;reg scan_second,seed_select;
 reg [2:0] fine_d;reg [1:0] fine_r;reg [4:0] fine_pose;
 reg signed [10:0] px,py,xmin,xmax,ymin,ymax;
 reg [9:0] current_diameter;reg [2:0] current_roll;
 wire [35:0] active_seed=seed_select?seed1:seed0;
 wire [9:0] seed_diameter={active_seed[9:3],3'b000};
 wire [2:0] seed_roll=active_seed[2:0];
 wire signed [11:0] next_d=$signed({2'b00,seed_diameter})-12'sd16+$signed({6'd0,fine_d,3'b000});
 wire signed [4:0] next_r=$signed({2'b00,seed_roll})-5'sd1+$signed({3'd0,fine_r});
 reg cfg_start,score_start,metric_cancel;
 wire cfg_done,cfg_valid,score_done,metric_fault,metric_busy;wire signed [8:0] metric_count;
 wire [31:0] metric_elapsed,metric_reads;
 assign rd_lease=held_lease;
 assign reacquire_due=track_uses>=MAX_TRACK_USES;
 t06_pair_metric #(.PAIR_FILE(PAIR_FILE)) metric(
  .clk(clk),.rst_n(rst_n),.cancel(metric_cancel|cancel),.cfg_start(cfg_start),.cfg_diameter(current_diameter),.cfg_roll_index(current_roll),
  .cfg_done(cfg_done),.cfg_valid(cfg_valid),.score_start(score_start),.center_x(px[8:0]),.center_y(py[7:0]),.busy(metric_busy),
  .score_done(score_done),.score_count(metric_count),.fault(metric_fault),.rd_req(rd_req),.rd_addr(rd_addr),
  .rd_valid(rd_valid),.rd_data(rd_data),.rd_fault(rd_fault),.elapsed_cycles(metric_elapsed),.read_requests(metric_reads));
 wire [35:0] scored_desc={1'b1,metric_count[7:0],px[8:0],py[7:0],current_diameter[9:3],current_roll};
 wire [35:0] compare_word=pool_q;
 wire [35:0] compare_anchor=state==FPUSE?overall_best:seed0;
 wire signed [9:0] delta_x=$signed({1'b0,compare_word[26:18]})-$signed({1'b0,compare_anchor[26:18]});
 wire signed [9:0] delta_y=$signed({2'b00,compare_word[17:10]})-$signed({2'b00,compare_anchor[17:10]});
 wire [19:0] delta_x2=delta_x*delta_x,delta_y2=delta_y*delta_y;
 wire [20:0] distance2={1'b0,delta_x2}+{1'b0,delta_y2};
 wire [6:0] min_dcode=compare_word[9:3]<compare_anchor[9:3]?compare_word[9:3]:compare_anchor[9:3];
 wire [13:0] min_dcode2=min_dcode*min_dcode;
 wire spatially_far=distance2>={7'd0,min_dcode2};
 wire [31:0] fresh_delta=owner_source-lock_source;
 wire new_track_source=owner_epoch==lock_epoch&&owner_cfg==lock_cfg&&fresh_delta!=0&&!fresh_delta[31];
 wire [35:0] final_far=far_best[35]?far_best:seed1;
 wire signed [8:0] final_margin=$signed({1'b0,overall_best[34:27]})-$signed({1'b0,final_far[34:27]});
 wire final_accept=overall_best[35]&&overall_best[34:27]>=135&&(mode||final_margin>=8);
 // Identity continuity uses the EXISTING TRACK search envelope: the +/-32
 // low-pixel translation screen plus +/-2 local refinement, D +/-16 native,
 // and one roll-index step. This is not a new geometric display tolerance.
 wire signed [9:0] recheck_dx=$signed({1'b0,overall_best[26:18]})-$signed({1'b0,lock_desc[26:18]});
 wire signed [9:0] recheck_dy=$signed({2'b00,overall_best[17:10]})-$signed({2'b00,lock_desc[17:10]});
 wire signed [7:0] recheck_dd=$signed({1'b0,overall_best[9:3]})-$signed({1'b0,lock_desc[9:3]});
 wire signed [3:0] recheck_dr=$signed({1'b0,overall_best[2:0]})-$signed({1'b0,lock_desc[2:0]});
 wire same_recheck_target=planned_recheck&&lock_desc[35]&&new_track_source&&
  recheck_dx>=-10'sd34&&recheck_dx<=10'sd34&&recheck_dy>=-10'sd34&&recheck_dy<=10'sd34&&
  recheck_dd>=-8'sd2&&recheck_dd<=8'sd2&&recheck_dr>=-4'sd1&&recheck_dr<=4'sd1;
 wire signed [12:0] left=$signed({2'b00,overall_best[26:18],2'b00})+13'sd2-$signed({4'd0,overall_best[9:3],2'b00});
 wire signed [12:0] right=$signed({2'b00,overall_best[26:18],2'b00})+13'sd2+$signed({4'd0,overall_best[9:3],2'b00});
 wire signed [12:0] top=$signed({3'b000,overall_best[17:10],2'b00})+13'sd2-$signed({4'd0,overall_best[9:3],2'b00});
 wire signed [12:0] bottom=$signed({3'b000,overall_best[17:10],2'b00})+13'sd2+$signed({4'd0,overall_best[9:3],2'b00});
 wire pool_we=state==CLEAR||state==FPOOL_WRITE||(state==MIN_STORE&&pending_desc>min_word);
 wire [9:0] pool_waddr=state==FPOOL_WRITE?{5'd0,fine_pose}:({coarse_config,4'b0000}+{6'd0,(state==MIN_STORE?min_index:list_index)});
 wire [35:0] pool_wdata=state==CLEAR?36'd0:state==MIN_STORE?pending_desc:pose_best;
 wire [9:0] pool_raddr=state==MIN_REQ?({coarse_config,4'b0000}+{6'd0,list_index}):pool_index;
 always @(posedge clk)begin
  // Exactly ONE syntactic write port; two state-exclusive source statements
  // caused TD to implement all528x36 entries as FF in preserved cost/syn01.
  if(pool_we)pool[pool_waddr]<=pool_wdata;
  if(state==PREQ||state==FPREQ||state==MIN_REQ)pool_q<=pool[pool_raddr];
 end
 task begin_pose;
  begin
   pose_best<=0;
   if(phase==HCOARSE)begin
    // One exact192 translation screen around the last qualified descriptor.
    // Grid step4low means any distinct points are >=4low apart, so the two
    // greatest descriptors are exactly the frozen separated Top2 seeds.
    current_diameter<={lock_desc[9:3],3'b000};current_roll<=lock_desc[2:0];
    xmin<=$signed({2'b00,lock_desc[26:18]})-11'sd32;xmax<=$signed({2'b00,lock_desc[26:18]})+11'sd32;
    ymin<=$signed({3'b000,lock_desc[17:10]})-11'sd32;ymax<=$signed({3'b000,lock_desc[17:10]})+11'sd32;
    px<=$signed({2'b00,lock_desc[26:18]})-11'sd32;py<=$signed({3'b000,lock_desc[17:10]})-11'sd32;
    state<=CONFIG;
   end else if(phase==COARSE)begin
    current_diameter<=10'd192+{3'd0,coarse_d,5'b00000};current_roll<=3'd1+{coarse_r,1'b0};
    xmin<=4;xmax<=316;ymin<=4;ymax<=176;px<=4;py<=4;list_index<=0;state<=CLEAR;
   end else if(next_r<0||next_r>6||next_d<160||next_d>544)state<=FPOOL_WRITE;
   else begin
    current_diameter<=next_d[9:0];current_roll<=next_r[2:0];
    xmin<=$signed({2'b00,active_seed[26:18]})-(phase==LOCAL?11'sd2:11'sd4);xmax<=$signed({2'b00,active_seed[26:18]})+(phase==LOCAL?11'sd2:11'sd4);
    ymin<=$signed({3'b000,active_seed[17:10]})-(phase==LOCAL?11'sd2:11'sd4);ymax<=$signed({3'b000,active_seed[17:10]})+(phase==LOCAL?11'sd2:11'sd4);
    px<=$signed({2'b00,active_seed[26:18]})-(phase==LOCAL?11'sd2:11'sd4);py<=$signed({3'b000,active_seed[17:10]})-(phase==LOCAL?11'sd2:11'sd4);
    state<=CONFIG;
   end
  end
 endtask
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=IDLE;phase<=COARSE;mode<=0;planned_recheck<=0;busy<=0;done<=0;fault<=0;candidate_valid<=0;partial<=0;best_count<=0;far_margin_count<=0;margin_valid<=0;fresh_track_confirm<=0;
   held_source<=0;held_epoch<=0;held_cfg<=0;held_lease<=0;lock_source<=0;lock_epoch<=0;lock_cfg<=0;lock_age<=0;track_uses<=0;lock_desc<=0;
   seed0<=0;seed1<=0;overall_best<=0;far_best<=0;pose_best<=0;coarse_config<=0;coarse_d<=0;coarse_r<=0;
   list_index<=0;min_index<=0;min_word<=0;pending_desc<=0;pool_index<=0;scan_second<=0;seed_select<=0;fine_d<=0;fine_r<=0;fine_pose<=0;
   px<=0;py<=0;xmin<=0;xmax<=0;ymin<=0;ymax<=0;current_diameter<=0;current_roll<=0;cfg_start<=0;score_start<=0;metric_cancel<=0;
   box_x0<=0;box_x1<=0;box_y0<=0;box_y1<=0;center_x<=0;center_y<=0;diameter<=0;low_center_x<=0;low_center_y<=0;roll_index<=0;
   result_source<=0;result_epoch<=0;result_cfg<=0;result_lease<=0;result_age<=0;actual_cycles<=0;gray_reads<=0;evaluated_positions<=0;reason<=0;global_lock<=0;target_id<=0;
  end else begin
   done<=0;fault<=0;fresh_track_confirm<=0;cfg_start<=0;score_start<=0;metric_cancel<=0;
   if(global_lock&&lock_age<MAX_LOCK_GAP_CYCLES)lock_age<=lock_age+1'b1;
   if(global_lock&&lock_age>=MAX_LOCK_GAP_CYCLES-1)begin global_lock<=0;candidate_valid<=0;end
   if(!busy&&global_lock&&owner_valid&&(owner_epoch!=lock_epoch||owner_cfg!=lock_cfg))begin global_lock<=0;candidate_valid<=0;end
   if(!busy&&candidate_valid&&(!owner_valid||owner_lease!=result_lease||owner_source!=result_source||owner_epoch!=result_epoch||owner_cfg!=result_cfg))candidate_valid<=0;
   if(busy)actual_cycles<=actual_cycles+1'b1;
   if(rd_req)gray_reads<=gray_reads+1'b1;
   if(cancel||(busy&&(!owner_valid||owner_source!=held_source||owner_epoch!=held_epoch||owner_cfg!=held_cfg||owner_lease!=held_lease||actual_cycles>=MAX_RUN_CYCLES-1||metric_fault||(mode&&(!global_lock||lock_age>=MAX_LOCK_GAP_CYCLES-1||reacquire_due)))))begin
    state<=IDLE;busy<=0;planned_recheck<=0;done<=busy;fault<=busy;metric_cancel<=1;candidate_valid<=0;fresh_track_confirm<=0;global_lock<=0;
    reason<=cancel?4'd1:metric_fault?4'd2:actual_cycles>=MAX_RUN_CYCLES-1?4'd3:4'd4;
   end else case(state)
    IDLE:if(start)begin
     candidate_valid<=0;fresh_track_confirm<=0;actual_cycles<=0;gray_reads<=0;evaluated_positions<=0;reason<=0;
     if(!owner_valid||(track_mode&&(!global_lock||!new_track_source||reacquire_due)))begin
      done<=1;fault<=1;reason<=!owner_valid?5:6;if(track_mode)global_lock<=0;
     end else begin
      held_source<=owner_source;held_epoch<=owner_epoch;held_cfg<=owner_cfg;held_lease<=owner_lease;mode<=track_mode;
      planned_recheck<=!track_mode&&global_lock&&reacquire_due&&new_track_source;
      busy<=1;overall_best<=0;far_best<=0;seed1<=0;seed_select<=0;fine_d<=0;fine_r<=0;fine_pose<=0;
      if(track_mode)begin phase<=HCOARSE;seed0<=0;state<=POSE_END;end
      else begin global_lock<=0;phase<=COARSE;coarse_config<=0;coarse_d<=0;coarse_r<=0;state<=POSE_END;end
     end
    end
    CLEAR:begin if(list_index==15)state<=CONFIG;else list_index<=list_index+1'b1;end
    CONFIG:if(!metric_busy)begin cfg_start<=1;state<=CFGWAIT;end
    CFGWAIT:if(cfg_done)begin if(!cfg_valid)begin state<=IDLE;busy<=0;done<=1;fault<=1;global_lock<=0;reason<=2;end else state<=SCORE;end
    SCORE:if(!metric_busy)begin score_start<=1;state<=SWAIT;end
    SWAIT:if(score_done)begin
     evaluated_positions<=evaluated_positions+1'b1;
     if(metric_count<0)state<=NEXTXY;
     else if(phase==HCOARSE)begin
      if(scored_desc>seed0)begin seed0<=scored_desc;seed1<=seed0;end
      else if(scored_desc>seed1)seed1<=scored_desc;
      state<=NEXTXY;
     end
     else if(phase==COARSE)begin pending_desc<=scored_desc;state<=MIN_INIT;end
     else begin if(scored_desc>pose_best)pose_best<=scored_desc;if(scored_desc>overall_best)overall_best<=scored_desc;state<=NEXTXY;end
    end
    MIN_INIT:begin min_word<=36'hfffffffff;min_index<=0;list_index<=0;state<=MIN_REQ;end
    MIN_REQ:state<=MIN_USE;
    MIN_USE:begin if(pool_q<min_word)begin min_word<=pool_q;min_index<=list_index;end
     if(list_index==15)state<=MIN_STORE;else begin list_index<=list_index+1'b1;state<=MIN_REQ;end
    end
    MIN_STORE:state<=NEXTXY;
    NEXTXY:begin
     if(px+((phase==COARSE||phase==HCOARSE)?4:1)<=xmax)begin px<=px+((phase==COARSE||phase==HCOARSE)?4:1);state<=SCORE;end
     else if(py+((phase==COARSE||phase==HCOARSE)?4:1)<=ymax)begin px<=xmin;py<=py+((phase==COARSE||phase==HCOARSE)?4:1);state<=SCORE;end
     else if(phase==HCOARSE)begin
      phase<=LOCAL;seed_select<=0;fine_d<=0;fine_r<=0;fine_pose<=0;overall_best<=0;
      state<=seed0[35]?POSE_END:FINISH;
     end
     else if(phase==COARSE)begin list_index<=0;state<=POOL_WRITE;end
     else state<=FPOOL_WRITE;
    end
    POOL_WRITE:begin
     if(list_index!=15)list_index<=list_index+1'b1;
     else if(coarse_config==32)begin pool_index<=0;scan_second<=0;seed0<=0;seed1<=0;state<=PREQ;end
     else begin coarse_config<=coarse_config+1'b1;if(coarse_r==2)begin coarse_r<=0;coarse_d<=coarse_d+1'b1;end else coarse_r<=coarse_r+1'b1;state<=POSE_END;end
    end
    PREQ:state<=PUSE;
    PUSE:begin
     if(!scan_second)begin if(pool_q>seed0)seed0<=pool_q;end
     else if(pool_q[35]&&spatially_far&&pool_q>seed1)seed1<=pool_q;
     if(pool_index<527)begin pool_index<=pool_index+1'b1;state<=PREQ;end
     else if(!scan_second)begin scan_second<=1;pool_index<=0;state<=PREQ;end
     else begin phase<=FINE;seed_select<=0;fine_d<=0;fine_r<=0;fine_pose<=0;overall_best<=0;state<=POSE_END;end
    end
    POSE_END:begin_pose;
    FPOOL_WRITE:begin
     if(phase==LOCAL)begin
      if(fine_r<2)begin fine_r<=fine_r+1'b1;state<=POSE_END;end
      else if(fine_d<4)begin fine_r<=0;fine_d<=fine_d+1'b1;state<=POSE_END;end
      else if(!seed_select&&seed1[35])begin seed_select<=1;fine_d<=0;fine_r<=0;fine_pose<=0;state<=POSE_END;end
      else state<=FINISH;
     end else begin
      if(fine_r<2)begin fine_r<=fine_r+1'b1;fine_pose<=fine_pose+1'b1;state<=POSE_END;end
      else if(fine_d<4)begin fine_r<=0;fine_d<=fine_d+1'b1;fine_pose<=fine_pose+1'b1;state<=POSE_END;end
      else if(!seed_select)begin seed_select<=1;fine_d<=0;fine_r<=0;fine_pose<=fine_pose+1'b1;state<=POSE_END;end
      else begin pool_index<=0;far_best<=0;state<=FPREQ;end
     end
    end
    FPREQ:state<=FPUSE;
    FPUSE:begin
     if(pool_q[35]&&spatially_far&&pool_q>far_best)far_best<=pool_q;
     if(pool_index<29)begin pool_index<=pool_index+1'b1;state<=FPREQ;end else state<=FINISH;
    end
    FINISH:begin
     busy<=0;done<=1;state<=IDLE;candidate_valid<=final_accept;fresh_track_confirm<=mode&&final_accept;
     margin_valid<=!mode;far_margin_count<=mode?9'sd0:final_margin;best_count<=overall_best[34:27];
     low_center_x<=overall_best[26:18];low_center_y<=overall_best[17:10];roll_index<=overall_best[2:0];diameter<={overall_best[9:3],3'b000};
     center_x<={overall_best[26:18],2'b00}+11'd2;
     center_y<={overall_best[17:10],2'b00}+10'd2;
     box_x0<=left<0?0:left>1280?1280:left[10:0];box_x1<=right<0?0:right>1280?1280:right[10:0];
     box_y0<=top<0?0:top>720?720:top[9:0];box_y1<=bottom<0?0:bottom>720?720:bottom[9:0];
     partial<=left<0||top<0||right>1280||bottom>720;
     result_source<=held_source;result_epoch<=held_epoch;result_cfg<=held_cfg;result_lease<=held_lease;result_age<=owner_age;
     if(final_accept)begin
      global_lock<=1;lock_desc<=overall_best;lock_source<=held_source;lock_epoch<=held_epoch;lock_cfg<=held_cfg;lock_age<=0;
      if(mode)begin if(track_uses<MAX_TRACK_USES)track_uses<=track_uses+1'b1;end
       else begin if(!same_recheck_target)target_id<=target_id+1'b1;track_uses<=0;end
     end else begin global_lock<=0;reason<=7;end
    end
   endcase
  end
 end
endmodule
