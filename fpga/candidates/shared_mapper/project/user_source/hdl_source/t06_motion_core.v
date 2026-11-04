// MOT15: passive four-lane grayscale analysis. No video ready/backpressure.
// One history image; a poisoned partial write invalidates the ENTIRE reference.
// Synchronous RAM arrays have no reset. Flags protect uninitialized contents.
module t06_motion_core #(
 parameter WIDTH=1280,HEIGHT=720,DIFF_TH=20,MIN_LOCAL=16,
 parameter GLOBAL_CELLS=(WIDTH/8)*(HEIGHT/8)/2,
 parameter GLOBAL_SUM=(WIDTH/8)*(HEIGHT/8)*12,
 parameter QUIET_FRAMES=3,LOCAL_FRAMES=2,USE_SHARED_COORDS=0
)(
 input clk,rst_n,input [31:0] gray4,input s_valid,s_sof,s_eol,frame_error,
 input [31:0] source_id,input source_id_valid,
 input [8:0] shared_group_x,input [9:0] shared_y,
 output reg result_pulse,output reg [2:0] result_state,
 output reg [31:0] result_id,output reg [13:0] changed,
 output reg [7:0] xmin,xmax,output reg [6:0] ymin,ymax,
 output reg result_stable,output reg [15:0] events
);
 localparam GROUPS=WIDTH/4,COLS=WIDTH/8,ROWS=HEIGHT/8,CELLS=COLS*ROWS;
 localparam XW=(GROUPS<=1)?1:$clog2(GROUPS),YW=(HEIGHT<=1)?1:$clog2(HEIGHT);
 localparam CW=(COLS<=1)?1:$clog2(COLS),CAW=(CELLS<=1)?1:$clog2(CELLS);
 localparam CD=1<<CW,HD=1<<CAW;
 localparam INVALID=0,WARMUP=1,QUIET=2,LOCAL=3,GLOBAL=4;
 reg active,bad,done,can_compare,ref_valid;
 reg [XW-1:0] gx;reg [YW-1:0] gy;
 reg [31:0] fid,ref_id;
 reg [17:0] groups_seen;
 reg [13:0] cells_seen,change_acc;
 reg [21:0] frame_sum,ref_sum;
 reg [7:0] minx,maxx;reg [6:0] miny,maxy;
 reg [7:0] quiet_run,local_run;reg event_lock;
 reg [9:0] first_half;
 wire [9:0] group_sum={2'd0,gray4[31:24]}+{2'd0,gray4[23:16]}+
                        {2'd0,gray4[15:8]}+{2'd0,gray4[7:0]};
 wire start=s_valid&&s_sof;
 wire take=s_valid&&(active||s_sof);
 wire [XW-1:0] input_x=s_sof?0:(USE_SHARED_COORDS?shared_group_x[XW-1:0]:gx);
 wire [YW-1:0] input_y=s_sof?0:(USE_SHARED_COORDS?shared_y[YW-1:0]:gy);
 // Pair accumulation and a one-read / one-write synchronous vertical RAM.
 reg pv,p1v;reg [10:0] ps,p1s;
 reg [CW-1:0] pc,p1c;reg [2:0] pr,p1r;reg [6:0] py,p1y;
 reg [13:0] vertical[0:CD-1]; // synthesis ram_style=bram
 reg [13:0] vertical_q;
 wire [13:0] vertical_total=p1r==0?{3'd0,p1s}:vertical_q+{3'd0,p1s};
 reg cell_v;reg [7:0] cell_value;reg [CAW-1:0] cell_addr,next_addr;
 reg [7:0] cell_x;reg [6:0] cell_y;
 reg [7:0] history[0:HD-1]; // synthesis ram_style=bram
 reg [7:0] history_q,compare_value,compare_x;reg [6:0] compare_y;
 reg compare_v;
 wire [7:0] difference=compare_value>=history_q?compare_value-history_q:history_q-compare_value;
 wire [21:0] sum_difference=frame_sum>=ref_sum?frame_sum-ref_sum:ref_sum-frame_sum;
 wire pipelines_busy=pv||p1v||cell_v||compare_v;
 wire close_good=active&&!bad&&!frame_error&&done&&groups_seen==GROUPS*HEIGHT&&
                 cells_seen==CELLS&&!pipelines_busy;
 wire is_global=change_acc>=GLOBAL_CELLS||sum_difference>=GLOBAL_SUM;
 wire is_local=change_acc>=MIN_LOCAL;
 // RAM processes are intentionally reset-free; write enables are reset-gated.
 always @(posedge clk)begin
  if(pv)vertical_q<=vertical[pc];
  if(rst_n&&p1v)vertical[p1c]<=vertical_total;
  if(cell_v)history_q<=history[cell_addr];
  if(rst_n&&cell_v)history[cell_addr]<=cell_value;
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   active<=0;bad<=0;done<=0;can_compare<=0;ref_valid<=0;gx<=0;gy<=0;fid<=0;ref_id<=0;
   groups_seen<=0;cells_seen<=0;change_acc<=0;frame_sum<=0;ref_sum<=0;
   minx<=0;maxx<=0;miny<=0;maxy<=0;quiet_run<=0;local_run<=0;event_lock<=0;
   first_half<=0;pv<=0;p1v<=0;ps<=0;p1s<=0;pc<=0;p1c<=0;pr<=0;p1r<=0;py<=0;p1y<=0;
   cell_v<=0;cell_value<=0;cell_addr<=0;next_addr<=0;cell_x<=0;cell_y<=0;
   compare_v<=0;compare_value<=0;compare_x<=0;compare_y<=0;
   result_pulse<=0;result_state<=INVALID;result_id<=0;changed<=0;
   xmin<=0;xmax<=0;ymin<=0;ymax<=0;result_stable<=0;events<=0;
  end else begin
   result_pulse<=0;pv<=0;p1v<=pv;cell_v<=0;compare_v<=cell_v;
   if(pv)begin p1s<=ps;p1c<=pc;p1r<=pr;p1y<=py;end
   if(p1v&&p1r==7)begin
    cell_v<=1;cell_value<=(vertical_total+14'd32)>>6;
    cell_addr<=next_addr;next_addr<=next_addr+1'b1;cell_x<=p1c;cell_y<=p1y;
   end
   if(cell_v)begin compare_value<=cell_value;compare_x<=cell_x;compare_y<=cell_y;end
   if(compare_v)begin
    cells_seen<=cells_seen+1'b1;frame_sum<=frame_sum+compare_value;
    if(can_compare&&difference>=DIFF_TH)begin
     change_acc<=change_acc+1'b1;
     if(change_acc==0)begin minx<=compare_x;maxx<=compare_x;miny<=compare_y;maxy<=compare_y;end
     else begin
      if(compare_x<minx)minx<=compare_x;if(compare_x>maxx)maxx<=compare_x;
      if(compare_y<miny)miny<=compare_y;if(compare_y>maxy)maxy<=compare_y;
     end
    end
   end
   if(active&&frame_error)bad<=1;
   if(take)begin
    if(start)begin
     if(active)begin
      result_pulse<=1;result_id<=fid;result_stable<=0;
      if(!close_good)begin
       result_state<=INVALID;changed<=0;xmin<=0;xmax<=0;ymin<=0;ymax<=0;
       quiet_run<=0;local_run<=0;
      end else if(!can_compare)begin
       result_state<=WARMUP;changed<=0;xmin<=0;xmax<=0;ymin<=0;ymax<=0;
       quiet_run<=0;local_run<=0;
      end else begin
       changed<=change_acc;xmin<=minx;xmax<=maxx;ymin<=miny;ymax<=maxy;
       if(is_global)begin result_state<=GLOBAL;quiet_run<=0;local_run<=0;end
       else if(is_local)begin
        result_state<=LOCAL;quiet_run<=0;
        if(local_run<LOCAL_FRAMES)local_run<=local_run+1'b1;
        if(!event_lock&&local_run>=LOCAL_FRAMES-1)begin
         if(!(&events))events<=events+1'b1;event_lock<=1;
        end
       end else begin
        result_state<=QUIET;local_run<=0;
        if(quiet_run<QUIET_FRAMES)quiet_run<=quiet_run+1'b1;
        if(quiet_run>=QUIET_FRAMES-1)begin result_stable<=1;event_lock<=0;end
       end
      end
      ref_valid<=close_good;ref_sum<=frame_sum;ref_id<=fid;
     end
     active<=1;fid<=source_id;done<=0;
     // Pending stages belong to an interrupted old frame; poison the new one.
     bad<=frame_error||!source_id_valid||pipelines_busy;
     can_compare<=active?close_good&&source_id_valid&&source_id==fid+1'b1:
                          ref_valid&&source_id_valid&&source_id==ref_id+1'b1;
     groups_seen<=1;cells_seen<=0;change_acc<=0;frame_sum<=0;next_addr<=0;
     minx<=0;maxx<=0;miny<=0;maxy<=0;
     // Suppress residual old-frame writes rather than let them enter next frame.
     pv<=0;p1v<=0;cell_v<=0;compare_v<=0;
    end else begin
     if(done)bad<=1;
     if(groups_seen<GROUPS*HEIGHT+1)groups_seen<=groups_seen+1'b1;
    end
    if(s_eol!=(input_x==GROUPS-1))bad<=1;
    if(!input_x[0])first_half<=group_sum;
    else if(!done||start)begin
     pv<=1;ps<={1'b0,first_half}+{1'b0,group_sum};
     pc<=input_x>>1;pr<=input_y[2:0];py<=input_y>>3;
    end
    if(input_x==GROUPS-1)begin
     gx<=0;
     if(input_y==HEIGHT-1)begin gy<=0;done<=1;end else gy<=input_y+1'b1;
    end else begin gx<=input_x+1'b1;gy<=input_y;end
   end
  end
 end
endmodule
