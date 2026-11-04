// New128x128 owned native-gray ROI capture. No video ready and no DDR client.
// Exact stride1..4 square-block mean;four source pixels/CSI clock are reduced
// into four independently banked output columns. A request is only a future
// frame hint;captured sourceID is locked from the actual next CSI SOF.
module t06_meter_roi_capture_mcu #(
 parameter WIDTH=1280,HEIGHT=720,MAX_CAPTURE_WAIT=20000000
)(
 input wire csi_clk,clk,arst_n,
 input wire rd_clk,rd_rst_n,rd_authority,
 input wire [31:0] gray4,input wire gray_valid,gray_sof,gray_eol,frame_error,
 input wire [31:0] source_id,input wire source_id_valid,
 input wire capture_frame_allowed, // CSI SOF admission only; never gates activeT closure
 input wire req_valid,output wire req_ready,
 input wire [10:0] req_x0,input wire [9:0] req_y0,input wire [2:0] req_stride,
 input wire [6:0] req_radius,input wire [31:0] req_hint_source,
 input wire [15:0] req_target,input wire [31:0] req_config,
 input wire cancel,lease_release,
 output wire busy,output wire capture_armed,output reg commit_pulse,lease_valid,capture_good,
 output reg [4:0] capture_reason,
 output reg [10:0] captured_x0,output reg [9:0] captured_y0,
 output reg [2:0] captured_stride,output reg [6:0] captured_radius,
 output reg [31:0] captured_source,captured_hint_source,captured_config,
 output reg [15:0] captured_target,
 input wire rd_en,input wire [13:0] rd_addr,output wire [7:0] rd_data,
 // Qualified by existing commit_pulse/lease_valid and captured_* context.
 // {first_fault_cycle_causes12,bad,full,groups18,canonical15,close_flags6}.
 output reg [52:0] captured_diagnostics
);
 localparam GROUPS=WIDTH/4,IDLE=0,SETTLE=1,WAIT_SOF=2,CAPTURE=3,LEASED=4,CLOSE=5,CHECKCFG=6;
 (* ASYNC_REG="TRUE" *) reg [1:0] cr,pr;
 always @(posedge csi_clk or negedge arst_n)if(!arst_n)cr<=0;else cr<={cr[0],1'b1};
 always @(posedge clk or negedge arst_n)if(!arst_n)pr<=0;else pr<={pr[0],1'b1};
 wire creset=cr[1],preset=pr[1];
 reg request_toggle,release_toggle,request_ack,commit_toggle;
 reg [126:0] request_payload; // x11+y10+stride3+radius7+hint32+target16+config32+reserved16
 (* ASYNC_REG="TRUE" *) reg [1:0] request_sync,release_sync,ack_sync,commit_sync;
 reg [2:0] owner;reg release_seen;
 reg [10:0] x0;reg [9:0] y0;reg [2:0] stride;reg [6:0] radius;
 reg [31:0] hint,config_id,id;reg [15:0] target;
 reg [8:0] gx;reg [9:0] gy;
 reg [17:0] groups_seen;reg full_seen,bad;
 // Numeric count of admitted four-pixel source groups in this ROI row.
 // Arithmetic consumers need the actual integer value, never an FSM encoding.
 // This register increments arithmetically; it is not a finite-state code.
 reg [7:0] roi_groups;
 reg [6:0] roi_row;reg [2:0] vertical_phase;
 wire [7:0] roi_groups_div3=roi_groups/8'd3;
 wire [7:0] roi_col=stride==1?{roi_groups[5:0],2'b00}:
  stride==2?{roi_groups[6:0],1'b0}:stride==3?roi_groups+roi_groups_div3:roi_groups;
 wire [2:0] horizontal_phase=stride==3?(roi_groups-3*roi_groups_div3):3'd0;
 reg [9:0] horizontal_sum;
 reg [14:0] canonical_count;
 reg [4:0] metadata_reason;reg metadata_good;reg config_checked_good;
 reg [31:0] published_id;
 reg armed_csi;
 always @(posedge csi_clk or negedge creset)if(!creset)armed_csi<=0;else armed_csi<=owner==WAIT_SOF&&config_checked_good;
 (* ASYNC_REG="TRUE" *) reg [1:0] armed_sync;
 always @(posedge clk or negedge preset)if(!preset)armed_sync<=0;else armed_sync<={armed_sync[0],armed_csi};
 assign capture_armed=armed_sync[1]&&!cancel;
 // No RAM reset. Ownership/exact samplecount gates every processing read.
 reg [7:0] bank0[0:4095],bank1[0:4095],bank2[0:4095],bank3[0:4095]; // synthesis ram_style=bram
 reg [11:0] accum0[0:31],accum1[0:31],accum2[0:31],accum3[0:31]; // synthesis ram_style=bram
 reg [11:0] vq0,vq1,vq2,vq3;
 reg [7:0] rq0,rq1,rq2,rq3;reg [1:0] read_lane;
 assign rd_data=read_lane==0?rq0:read_lane==1?rq1:read_lane==2?rq2:rq3;
 wire sof=gray_valid&&gray_sof;
 wire start_capture=owner==WAIT_SOF&&config_checked_good&&sof&&capture_frame_allowed;
 wire take=gray_valid&&(owner==CAPTURE&&!full_seen&&!gray_sof||start_capture);
 wire [8:0] ix=gray_sof?0:gx;wire [9:0] iy=gray_sof?0:gy;
 wire [10:0] px={ix,2'b00};
 wire [10:0] span={1'b0,stride,7'b0};
 wire selected_row=iy>=y0&&{1'b0,iy}<{1'b0,y0}+span;
 wire config_ok=stride>=1&&stride<=4&&x0[1:0]==0&&{1'b0,x0}+span<=WIDTH&&{2'b0,y0}+span<=HEIGHT&&radius>=40&&radius<=62;
 wire write_allowed=creset&&release_sync[1]==release_seen&&(owner==CAPTURE||start_capture)&&!bad&&!frame_error;
 // CAPTURE validates T, including its closing SOF. Once in CLOSE, metadata_good
 // freezes those checks for T. Live frame_error/source-valid now describe the
 // following source and must neither poison T nor suppress its pending writes.
 // The same permission counts precisely the writes which actually reach RAM.
 wire drain_write_allowed=creset&&release_sync[1]==release_seen&&
  ((owner==CAPTURE&&!bad&&!frame_error)||(owner==CLOSE&&metadata_good));
 reg [3:0] complete_en;
 reg [9:0] sum0,sum1,sum2,sum3;
 reg [4:0] col0,col1,col2,col3;
 reg [2:0] next_hphase;
 reg [9:0] next_hsum;
 reg [8:0] next_col;reg [7:0] next_groups;
 // Parallel horizontal block construction; no four-lane phase dependency.
 wire [7:0] g0=gray4[31:24],g1=gray4[23:16],g2=gray4[15:8],g3=gray4[7:0];
 wire [8:0] g01={1'b0,g0}+{1'b0,g1},g23={1'b0,g2}+{1'b0,g3};
 wire [8:0] g12={1'b0,g1}+{1'b0,g2};
 wire [9:0] g012={1'b0,g01}+{2'b0,g2};
 wire [9:0] g123={1'b0,g12}+{2'b0,g3};
 wire [9:0] g0123={1'b0,g01}+{1'b0,g23};
 reg [9:0] block_a,block_b,block_c,block_d;
 reg [3:0] block_mask;
 wire [4:0] column_word=roi_col[6:2],column_next=roi_col[6:2]+1'b1;
 always @*begin
  complete_en=0;sum0=0;sum1=0;sum2=0;sum3=0;col0=0;col1=0;col2=0;col3=0;
  next_hphase=horizontal_phase;next_hsum=horizontal_sum;next_col={1'b0,roi_col};next_groups=roi_groups;
  block_a=0;block_b=0;block_c=0;block_d=0;block_mask=0;
  if(start_capture)begin next_hphase=0;next_hsum=0;next_col=0;next_groups=0;end
  // x0/span are4aligned, so every admitted group contributes all four pixels.
  if(take&&selected_row&&write_allowed&&px>=x0&&{1'b0,px}<{1'b0,x0}+span)begin
   next_groups=roi_groups+8'd1;
   case(stride)
    1:begin
     block_a={2'd0,g0};block_b={2'd0,g1};block_c={2'd0,g2};block_d={2'd0,g3};block_mask=4'b1111;
     next_hphase=0;next_hsum=0;next_col={1'b0,roi_col}+9'd4;
    end
    2:begin
     block_a={1'b0,g01};block_b={1'b0,g23};block_mask=4'b0011;
     next_hphase=0;next_hsum=0;next_col={1'b0,roi_col}+9'd2;
    end
    3:begin
     case(horizontal_phase)
      0:begin block_a=g012;block_mask=4'b0001;next_hsum={2'd0,g3};next_hphase=1;next_col={1'b0,roi_col}+9'd1;end
      1:begin block_a=horizontal_sum+g01;block_mask=4'b0001;next_hsum={1'b0,g23};next_hphase=2;next_col={1'b0,roi_col}+9'd1;end
      2:begin block_a=horizontal_sum+g0;block_b=g123;block_mask=4'b0011;next_hsum=0;next_hphase=0;next_col={1'b0,roi_col}+9'd2;end
      default:begin end
     endcase
    end
    4:begin block_a=g0123;block_mask=4'b0001;next_hphase=0;next_hsum=0;next_col={1'b0,roi_col}+9'd1;end
    default:begin end
   endcase
   // Generic column/bank rotation: this does not assume the column modulo4
   // from stride phase, and handles a completed block crossing a word boundary.
   case(roi_col[1:0])
    0:begin complete_en=block_mask;sum0=block_a;sum1=block_b;sum2=block_c;sum3=block_d;col0=column_word;col1=column_word;col2=column_word;col3=column_word;end
    1:begin complete_en={block_mask[2:0],block_mask[3]};sum1=block_a;sum2=block_b;sum3=block_c;sum0=block_d;col0=column_next;col1=column_word;col2=column_word;col3=column_word;end
    2:begin complete_en={block_mask[1:0],block_mask[3:2]};sum2=block_a;sum3=block_b;sum0=block_c;sum1=block_d;col0=column_next;col1=column_next;col2=column_word;col3=column_word;end
    3:begin complete_en={block_mask[0],block_mask[3:1]};sum3=block_a;sum0=block_b;sum1=block_c;sum2=block_d;col0=column_next;col1=column_next;col2=column_next;col3=column_word;end
   endcase
  end
 end
 reg [3:0] pending;
 reg [9:0] ps0,ps1,ps2,ps3;
 reg [4:0] pc0,pc1,pc2,pc3;reg [6:0] prow;
 reg pfirst,plast;reg [2:0] pstride;
 wire [11:0] add0=(pfirst?12'd0:vq0)+ps0;
 wire [11:0] add1=(pfirst?12'd0:vq1)+ps1;
 wire [11:0] add2=(pfirst?12'd0:vq2)+ps2;
 wire [11:0] add3=(pfirst?12'd0:vq3)+ps3;
 reg [3:0] output_pending;reg [11:0] output_sum0,output_sum1,output_sum2,output_sum3;
 reg [4:0] output_col0,output_col1,output_col2,output_col3;
 reg [6:0] output_row;reg [2:0] output_stride;
 // Diagnostic-only first-event evidence. All causes on the FIRST faulty CSI
 // cycle are retained together; no priority silently discards simultaneous
 // events. Later faults, including faults of the next frame in CLOSE, cannot
 // replace the first event or its closing-boundary snapshot.
 reg [11:0] diag_first_causes,diag_causes_now;
 reg [5:0] diag_close_flags;
 always @*begin
  diag_causes_now=0;
  if(owner==WAIT_SOF&&!config_checked_good)diag_causes_now[0]=1;
  if(start_capture)begin
   if(source_id==hint)diag_causes_now[1]=1;
   if(frame_error)diag_causes_now[2]=1;
   if(!source_id_valid)diag_causes_now[3]=1;
   if(gray_eol!=(GROUPS==1))diag_causes_now[4]=1;
  end
  if(owner==CAPTURE)begin
   if(frame_error)diag_causes_now[2]=1;
   if(!source_id_valid)diag_causes_now[3]=1;
   if(sof)begin
    if(!full_seen)diag_causes_now[8]=1;
    if(groups_seen!=GROUPS*HEIGHT)diag_causes_now[9]=1;
    if(bad)diag_causes_now[11]=1;
   end else if(gray_valid)begin
    if(full_seen)diag_causes_now[6]=1;
    else begin
     if(gray_eol!=(gx==GROUPS-1))diag_causes_now[4]=1;
     if(source_id!=id)diag_causes_now[5]=1;
     if(gx==GROUPS-1&&selected_row&&(next_col!=9'd128||next_hphase!=3'd0))diag_causes_now[7]=1;
    end
   end
  end
  if(owner==CLOSE&&output_pending==0&&canonical_count!=16384)diag_causes_now[10]=1;
 end
 always @(posedge csi_clk or negedge creset)begin
  if(!creset)begin diag_first_causes<=0;diag_close_flags<=0;end
  else if(release_sync[1]!=release_seen||owner==SETTLE)begin diag_first_causes<=0;diag_close_flags<=0;end
  else begin
   if(diag_first_causes==0&&diag_causes_now!=0)diag_first_causes<=diag_causes_now;
   if(owner==CAPTURE&&sof)diag_close_flags<={sof,gray_valid,frame_error,source_id_valid,full_seen,(pending!=0||output_pending!=0)};
  end
 end

 function [7:0] averaged;
  input [11:0] value;input [2:0] s;reg [25:0] reciprocal_product;
  begin reciprocal_product=value*14'd7282;
   case(s)1:averaged=value[7:0];2:averaged=value>>2;3:averaged=reciprocal_product[23:16];default:averaged=value>>4;endcase end
 endfunction
 always @(posedge csi_clk)begin
  if(creset&&complete_en[0])vq0<=accum0[col0];
  if(creset&&complete_en[1])vq1<=accum1[col1];
  if(creset&&complete_en[2])vq2<=accum2[col2];
  if(creset&&complete_en[3])vq3<=accum3[col3];
  if(creset&&release_sync[1]==release_seen&&owner==CAPTURE&&!bad&&!frame_error)begin
   if(pending[0])accum0[pc0]<=add0;
   if(pending[1])accum1[pc1]<=add1;
   if(pending[2])accum2[pc2]<=add2;
   if(pending[3])accum3[pc3]<=add3;
  end
  if(drain_write_allowed)begin
   if(output_pending[0])bank0[{output_row,output_col0}]<=averaged(output_sum0,output_stride);
   if(output_pending[1])bank1[{output_row,output_col1}]<=averaged(output_sum1,output_stride);
   if(output_pending[2])bank2[{output_row,output_col2}]<=averaged(output_sum2,output_stride);
   if(output_pending[3])bank3[{output_row,output_col3}]<=averaged(output_sum3,output_stride);
  end
 end
 always @(posedge rd_clk)if(rd_rst_n&&rd_authority&&rd_en)begin
  rq0<=bank0[rd_addr[13:2]];rq1<=bank1[rd_addr[13:2]];
  rq2<=bank2[rd_addr[13:2]];rq3<=bank3[rd_addr[13:2]];read_lane<=rd_addr[1:0];
 end
 always @(posedge csi_clk or negedge creset)begin
  if(!creset)begin
   request_sync<=0;release_sync<=0;request_ack<=0;commit_toggle<=0;owner<=IDLE;release_seen<=0;
   x0<=0;y0<=0;stride<=1;radius<=0;hint<=0;config_id<=0;id<=0;target<=0;
   gx<=0;gy<=0;groups_seen<=0;full_seen<=0;bad<=0;roi_groups<=0;roi_row<=0;
   vertical_phase<=0;horizontal_sum<=0;canonical_count<=0;
   pending<=0;ps0<=0;ps1<=0;ps2<=0;ps3<=0;pc0<=0;pc1<=0;pc2<=0;pc3<=0;prow<=0;pfirst<=0;plast<=0;pstride<=1;
   metadata_reason<=0;metadata_good<=0;config_checked_good<=0;published_id<=0;output_pending<=0;output_sum0<=0;output_sum1<=0;output_sum2<=0;output_sum3<=0;output_col0<=0;output_col1<=0;output_col2<=0;output_col3<=0;output_row<=0;output_stride<=1;
  end else begin
   request_sync<={request_sync[0],request_toggle};release_sync<={release_sync[0],release_toggle};
   output_pending<=(owner==CAPTURE&&!bad&&!frame_error&&release_sync[1]==release_seen)?(pending&{4{plast}}):4'd0;
   output_sum0<=add0;output_sum1<=add1;output_sum2<=add2;output_sum3<=add3;
   output_col0<=pc0;output_col1<=pc1;output_col2<=pc2;output_col3<=pc3;output_row<=prow;output_stride<=pstride;
   pending<=complete_en;ps0<=sum0;ps1<=sum1;ps2<=sum2;ps3<=sum3;
   pc0<=col0;pc1<=col1;pc2<=col2;pc3<=col3;prow<=roi_row;
   pfirst<=vertical_phase==0;plast<=vertical_phase==stride-1;pstride<=stride;
   // Count the actual registered output writes, not the combinational lane
   // decision. CLOSE waits for this final count before exposing any good lease.
   if(drain_write_allowed)
    canonical_count<=canonical_count+output_pending[0]+output_pending[1]+output_pending[2]+output_pending[3];
   if(release_sync[1]!=release_seen)begin
    owner<=IDLE;pending<=0;output_pending<=0;release_seen<=release_sync[1];request_ack<=request_sync[1];metadata_good<=0;
   end else case(owner)
    IDLE:if(request_sync[1]!=request_ack)owner<=SETTLE;
    SETTLE:begin
     {x0,y0,stride,radius,hint,target,config_id}<=request_payload[126:16];owner<=CHECKCFG;
     bad<=0;pending<=0;roi_groups<=0;roi_row<=0;vertical_phase<=0;horizontal_sum<=0;canonical_count<=0;
    end
    CHECKCFG:begin config_checked_good<=config_ok;owner<=WAIT_SOF;end
    WAIT_SOF:if(!config_checked_good)begin
     metadata_good<=0;metadata_reason<=1;published_id<=0;commit_toggle<=~commit_toggle;owner<=LEASED;
    end else if(start_capture)begin
     owner<=CAPTURE;id<=source_id;groups_seen<=1;full_seen<=0;
     bad<=frame_error||!source_id_valid||source_id==hint||gray_eol!=(GROUPS==1);
     gx<=1;gy<=0;roi_groups<=next_groups;horizontal_sum<=next_hsum;
     canonical_count<=0;
    end
    CAPTURE:begin
     if(frame_error||!source_id_valid)bad<=1;
     if(sof)begin
      metadata_good<=!bad&&!frame_error&&source_id_valid&&full_seen&&groups_seen==GROUPS*HEIGHT;
      metadata_reason<=(!bad&&!frame_error&&source_id_valid&&full_seen&&groups_seen==GROUPS*HEIGHT)?0:2;
      published_id<=id;owner<=CLOSE;pending<=0;
     end else if(gray_valid&&!full_seen)begin
      if(gray_eol!=(gx==GROUPS-1)||source_id!=id)bad<=1;
      groups_seen<=groups_seen+1'b1;roi_groups<=next_groups;horizontal_sum<=next_hsum;
      if(gx==GROUPS-1)begin
       gx<=0;
       if(selected_row)begin
        if(next_col!=9'd128||next_hphase!=3'd0)bad<=1;
        roi_groups<=0;horizontal_sum<=0;
        if(vertical_phase==stride-1)begin vertical_phase<=0;roi_row<=roi_row+1'b1;end
        else vertical_phase<=vertical_phase+1'b1;
       end
       if(gy==HEIGHT-1)full_seen<=1;else gy<=gy+1'b1;
      end else gx<=gx+1'b1;
     end else if(gray_valid&&full_seen)bad<=1;
    end
    CLOSE:begin
     if(output_pending==0)begin
      metadata_good<=metadata_good&&canonical_count==16384;
      metadata_reason<=(metadata_good&&canonical_count==16384)?0:2;
      commit_toggle<=~commit_toggle;owner<=LEASED;
     end
    end
    default:begin end
   endcase
  end
 end
 reg [1:0] pstate;reg seen_commit;reg [31:0] wait_cycles;
 assign req_ready=preset&&!cancel&&!lease_release&&pstate==0&&ack_sync[1]==request_toggle;
 assign busy=pstate!=0;
 always @(posedge clk or negedge preset)begin
  if(!preset)begin
   ack_sync<=0;commit_sync<=0;request_toggle<=0;release_toggle<=0;request_payload<=0;pstate<=0;seen_commit<=0;wait_cycles<=0;
   commit_pulse<=0;lease_valid<=0;capture_good<=0;capture_reason<=0;
   captured_x0<=0;captured_y0<=0;captured_stride<=0;captured_radius<=0;captured_source<=0;captured_hint_source<=0;captured_config<=0;captured_target<=0;
   captured_diagnostics<=0;
  end else begin
   ack_sync<={ack_sync[0],request_ack};commit_sync<={commit_sync[0],commit_toggle};commit_pulse<=0;
   if(pstate!=0)wait_cycles<=wait_cycles+1'b1;
   if((cancel||lease_release||(pstate==1&&wait_cycles>=MAX_CAPTURE_WAIT))&&pstate!=0&&pstate!=3)begin
    release_toggle<=~release_toggle;pstate<=3;lease_valid<=0;capture_good<=0;capture_reason<=cancel?3:lease_release?0:4;
    captured_diagnostics<=0;
   end else case(pstate)
    0:if(req_valid&&req_ready)begin
     request_payload<={req_x0,req_y0,req_stride,req_radius,req_hint_source,req_target,req_config,16'd0};
     request_toggle<=~request_toggle;pstate<=1;wait_cycles<=0;lease_valid<=0;capture_good<=0;
     captured_diagnostics<=0;
    end
    1:if(commit_sync[1]!=seen_commit)begin seen_commit<=commit_sync[1];pstate<=2;end
    2:if(!lease_valid)begin
     // Held metadata has settled an extra full processing clock after the toggle.
     captured_x0<=x0;captured_y0<=y0;captured_stride<=stride;captured_radius<=radius;
     captured_source<=published_id;captured_hint_source<=hint;captured_config<=config_id;captured_target<=target;
     capture_good<=metadata_good;capture_reason<=metadata_reason;lease_valid<=1;commit_pulse<=1;
     // No CSI data is sampled early: these fields stay immutable in LEASED,
     // after the same synchronized commit and extra settle as captured_*.
     // A rejected configuration never admitted T; old job counters are not
     // valid evidence for that request and are explicitly represented as0.
     captured_diagnostics<=metadata_reason==1?
       {diag_first_causes,1'b0,1'b0,18'd0,15'd0,6'd0}:
       {diag_first_causes,bad,full_seen,groups_seen,canonical_count,diag_close_flags};
    end
    3:if(ack_sync[1]==request_toggle)begin pstate<=0;seen_commit<=commit_sync[1];wait_cycles<=0;end
   endcase
  end
 end
endmodule
