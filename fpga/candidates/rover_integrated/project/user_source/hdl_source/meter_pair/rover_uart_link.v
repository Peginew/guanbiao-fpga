`timescale 1ns/1ps
`include "C:/Users/Edward/Desktop/FPGA/Stable3s_Rover_Merged_20261104/fpga/project/user_source/hdl_source/meter_pair/guanbiao_uart_v4_defs.vh"
// V4 lite vision endpoint. The ESP owns navigation, finite action/point/task
// deadlines, real terminal progression and the continuous six-second clock.
// This endpoint independently checks parked STATE, fresh local evidence and
// actual CSI fences. REF/LAST and geometry never enter the result path.
module rover_uart_link #(parameter integer CLK_HZ=75000000,BAUD=115200)(
 input wire clk,rst_n,input wire[31:0]now_ms,input wire uart_rx,output wire uart_tx,
 input wire healthy,location_valid,location_lock,readable,input wire[3:0]pipeline_state,input wire[4:0]read_reason,
 input wire camera_update,input wire[31:0]camera_source,input wire camera_good,
 input wire observation_update,input wire[1:0]observation_kind,
 input wire[31:0]observation_source,observation_age_cycles,
 input wire[10:0]box_left,box_right,input wire[9:0]box_top,box_bottom,input wire box_partial,box_credible,
 input wire current_read_update,current_read_valid,input wire[15:0]raw_bar_q16,
 input wire[31:0]current_read_source,input wire[1:0]ref_mode,input wire ref_valid,input wire[15:0]ref_psi100,
 input wire fence_idle,fence_ready,input wire[31:0]fence_source,output reg fence_request,
 output wire link_up,output reg task_active,output wire stationary_permit,output wire[31:0]motion_epoch,
 output reg analysis_cancel,reader_revoke
);
 localparam integer SERIAL_MS=(320000+BAUD-1)/BAUD;
 localparam [31:0] POS_CYCLES=CLK_HZ/1000*150,NEG_CYCLES=CLK_HZ;
 function forward16; input[15:0]a,b;reg[15:0]d;begin d=a-b;forward16=d!=0&&!d[15];end endfunction
 function forward32; input[31:0]a,b;reg[31:0]d;begin d=a-b;forward32=d!=0&&!d[31];end endfunction
 wire[7:0] rb,tb;wire rb_valid,rb_error,tb_valid,tb_ready;
 rover_uart_phy #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) u_phy(.clk(clk),.rst_n(rst_n),.rx(uart_rx),.tx(uart_tx),
  .tx_data(tb),.tx_valid(tb_valid),.tx_ready(tb_ready),.rx_data(rb),.rx_valid(rb_valid),.rx_error(rb_error));
 wire[223:0]rx_body;wire received_valid,received_error,frame_ready,capture_busy,capture_done;wire[2:0]capture_index;
 reg frame_send;reg[31:0]tx_word;
 rover_uart_codec_v4 u_codec(.clk(clk),.rst_n(rst_n),.now_ms(now_ms),.rx_byte(rb),.rx_valid(rb_valid),.rx_error(rb_error),
  .rx_body(rx_body),.frame_valid(received_valid),.frame_error(received_error),.tx_word(tx_word),.capture_index(capture_index),
  .frame_send(frame_send),.frame_ready(frame_ready),.capture_busy(capture_busy),.capture_done(capture_done),
  .tx_byte(tb),.tx_valid(tb_valid),.tx_ready(tb_ready));
 wire[7:0]rtype=rx_body[15:8],raction=rx_body[39:32],rflags=rx_body[47:40];
 wire[15:0]rseq=rx_body[31:16];
 wire[31:0]rtoken=rx_body[79:48],rkey=rx_body[111:80],repoch=rx_body[143:112];
 wire[79:0]p=rx_body[223:144];
 reg[31:0]token,peer_session,task_key,vehicle_epoch;
 reg expiry_pending;reg bound,hello_zero_sent,zero_inflight,hello_pending,token_exhausted,rx_deferred,seq_have;
 reg[15:0]rx_seq,tx_seq;reg[9:0]peer_ms;reg[7:0]state_ms,tx_ms;
 reg state_have,state_owner,tx_due,task_have,direction,task_mode;
 reg[7:0]vehicle_flags,imu_age;reg park_six;reg[5:0]vehicle_action,action_id;
 reg[3:0]stage;reg[4:0]failure_reason;
 wire[9:0]peer_age=now_ms[9:0]-peer_ms;
 wire[7:0]state_age=now_ms[7:0]-state_ms,tx_age=now_ms[7:0]-tx_ms;
 wire[9:0]imu_total={2'd0,imu_age}+{2'd0,state_age}+SERIAL_MS+10'd1;
 wire state_fresh=state_have&&state_age<=250&&imu_total<=180;
 wire state_parked=(vehicle_flags&8'h27)==8'h07;
 wire local_permission=(vehicle_flags&8'h1b)==8'h1b;
 assign link_up=bound;assign motion_epoch=vehicle_epoch;
 assign stationary_permit=bound&&state_fresh&&state_parked;
 wire owner_ready=stationary_permit&&park_six&&state_owner&&vehicle_action==action_id;
 wire ready_step=owner_ready&&local_permission&&vehicle_flags[6]&&vehicle_action==action_id;
 wire ready_read=owner_ready&&local_permission&&vehicle_flags[7]&&stage!=`GB4_STAGE_WAIT_ACTION;
 wire new_seq=!seq_have||forward16(rseq,rx_seq);
 wire hold_context=capture_busy||frame_send;
 wire consume_rx=received_valid||rx_deferred;
 wire rx_commit=consume_rx&&!hold_context;
 wire normal_header=bound&&rtoken==token&&rflags==0&&raction<=36;
 wire active_context=normal_header&&task_active&&rkey==task_key&&repoch==vehicle_epoch;
 wire cancel_shape=p[79:8]==0&&p[7:0]<=31;
 // Cancellation is a safety operation even while one queued ACK is blocked.
 wire immediate_cancel=received_valid&&active_context&&rtype==4&&cancel_shape&&new_seq;
 wire hello_shape=raction==0&&rflags==0&&rkey!=0&&repoch==`GB4_CONFIG_SIGNATURE&&
  p[31:0]==`GB4_ESP_BUILD&&p[47:32]==127&&p[55:48]==32&&p[63:56]==4&&p[79:64]==0;
 wire state_shape=p[79:48]==0;
 wire start_shape=raction==0&&rkey!=0&&p[79:24]==0&&p[23:16]<=1&&
  (p[15:0]==16'd10000||p[15:0]==-16'sd10000);
 reg camera_have;reg[8:0]camera_ms;
 wire[8:0]camera_age=now_ms[8:0]-camera_ms;
 wire camera_alive=camera_have&&camera_age<=500;
 reg obs_seen,obs_have,obs_partial,obs_positive;reg[31:0]obs_source;reg[4:0]obs_ms;
 wire[4:0]obs_age=now_ms[4:0]-obs_ms;
 wire raw_positive=observation_kind==2&&box_credible&&observation_age_cycles<=POS_CYCLES;
 wire raw_negative=observation_kind==1&&observation_age_cycles<=NEG_CYCLES;
 reg ready_before;reg floor_valid,fence_wait,fence_discard,fence_read;reg[31:0]source_floor;
 wire obs_post_floor=floor_valid&&forward32(observation_source,source_floor);
 reg found,stop_pending,failure_pending,control_pending;
 reg read_have,read_seen,result_pending;reg[31:0]read_source;reg[15:0]read_q;reg[7:0]read_ms;
 wire[7:0]read_age=now_ms[7:0]-read_ms;
 wire[9:0]read_wire_age={2'd0,read_age}+SERIAL_MS+10'd1;
 wire read_current=read_have&&current_read_valid&&current_read_source==read_source&&raw_bar_q16==read_q&&
  healthy&&camera_alive&&ready_read&&read_age<=200&&read_wire_age<=200;
 reg floor_pending,floor_inflight,floor_published;
 reg ack_pending;reg[15:0]ack_seq;reg[3:0]ack_type;reg[2:0]ack_status;
 reg send_selected;reg[3:0]tx_kind;reg tx_owned;reg[5:0]tx_action;reg[79:0]tx_payload;
 wire[31:0]packet_token=peer_session==0?32'd0:token;
 wire[31:0]packet_key=tx_kind==1?peer_session:tx_owned?task_key:32'd0;
 wire[31:0]packet_epoch=tx_kind==1?`GB4_CONFIG_SIGNATURE:vehicle_epoch;
 wire[15:0]obs_flags=16'd3|(obs_positive?16'd20:16'd32)|(obs_partial?16'd8:16'd0);
 wire[15:0]obs_wire_age=(obs_positive?16'd151:16'd1001)+{11'd0,obs_age}+SERIAL_MS+16'd1;
 wire slot=frame_ready&&!frame_send&&!consume_rx&&!observation_update&&!current_read_update&&!fence_ready;
 wire fatal_local=task_active&&(!bound||!state_fresh||vehicle_flags[5]||!healthy||!camera_alive);
 wire decision_safe=!fatal_local&&!immediate_cancel;
 // Architectural context is held for the seven RAM writes; image/payload is
 // captured once. RX body is consumed only at valid (or a one-frame defer).
 always @* begin
  case(capture_index)
   0:tx_word={tx_seq,4'd0,tx_kind,8'd4};
   1:tx_word={packet_token[15:0],8'd0,2'd0,tx_action};
   2:tx_word={packet_key[15:0],packet_token[31:16]};
   3:tx_word={packet_epoch[15:0],packet_key[31:16]};
   4:tx_word={tx_payload[15:0],packet_epoch[31:16]};
   5:tx_word=tx_payload[47:16];
   default:tx_word=tx_payload[79:48];
  endcase
 end
 task revoke_visual;begin
  floor_valid<=0;obs_have<=0;obs_seen<=0;read_have<=0;read_seen<=0;result_pending<=0;
  floor_pending<=0;floor_inflight<=0;floor_published<=0;reader_revoke<=1;
  if(fence_wait)fence_discard<=1;
 end endtask
 task fail_task;input[4:0]reason;begin
  task_active<=0;stage<=`GB4_STAGE_FAILED;failure_reason<=reason;failure_pending<=1;
  stop_pending<=1;analysis_cancel<=1;revoke_visual;
 end endtask
 task acknowledge;input[2:0]status;begin
  if(!ack_pending)begin ack_pending<=1;ack_seq<=rseq;ack_type<=rtype[3:0];ack_status<=status;end
 end endtask
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   expiry_pending<=0;token<=0;peer_session<=0;task_key<=0;vehicle_epoch<=0;bound<=0;hello_zero_sent<=0;zero_inflight<=0;
   hello_pending<=1;token_exhausted<=0;rx_deferred<=0;seq_have<=0;rx_seq<=0;tx_seq<=0;peer_ms<=0;
   state_ms<=0;tx_ms<=0;state_have<=0;state_owner<=0;tx_due<=0;task_have<=0;direction<=0;task_mode<=0;
   vehicle_flags<=0;imu_age<=255;park_six<=0;vehicle_action<=0;action_id<=0;task_active<=0;
   stage<=0;failure_reason<=0;camera_have<=0;camera_ms<=0;obs_seen<=0;obs_have<=0;obs_partial<=0;
   obs_positive<=0;obs_source<=0;obs_ms<=0;floor_valid<=0;fence_wait<=0;fence_discard<=0;fence_read<=0;
   ready_before<=0;source_floor<=0;found<=0;stop_pending<=0;failure_pending<=0;control_pending<=0;
   read_have<=0;read_seen<=0;result_pending<=0;read_source<=0;read_q<=0;read_ms<=0;
   floor_pending<=0;floor_inflight<=0;floor_published<=0;ack_pending<=0;ack_seq<=0;ack_type<=0;ack_status<=0;
   tx_kind<=1;tx_owned<=0;tx_action<=0;tx_payload<=0;frame_send<=0;fence_request<=0;analysis_cancel<=0;reader_revoke<=0;
  end else begin
   frame_send<=0;fence_request<=0;analysis_cancel<=0;reader_revoke<=0;send_selected=0;
   ready_before<=owner_ready;
   if(task_active&&owner_ready&&!ready_before)begin revoke_visual;fence_read<=0;stage<=`GB4_STAGE_WAIT_READY;end
   if(received_valid&&hold_context)rx_deferred<=1;
   if(rx_commit)rx_deferred<=0;
   if(tx_age>=100)tx_due<=1;
   if(camera_have&&camera_age>=501)camera_have<=0;
   if(camera_update&&camera_good)begin camera_have<=1;camera_ms<=now_ms[8:0];end
   if(state_have&&state_age>=251)state_have<=0;
   if(obs_have&&obs_age>=31)obs_have<=0;
   if(read_have&&read_age>=201)begin read_have<=0;result_pending<=0;end
   if(!current_read_valid)begin read_have<=0;if(result_pending)fail_task(`GB4_REASON_FRAME_STALE);end
   if(zero_inflight&&frame_ready&&!frame_send&&!tb_valid&&tb_ready)begin hello_zero_sent<=1;zero_inflight<=0;end
   if(floor_inflight&&frame_ready&&!frame_send&&!tb_valid&&tb_ready)begin
    floor_inflight<=0;if(task_active&&stage==`GB4_STAGE_WAIT_READ)floor_published<=1;
   end
   // One outstanding CSI transaction drains independently of task lifetime.
   if(fence_ready&&fence_wait)begin
    fence_wait<=0;
    if(task_active&&!fence_discard)begin
     source_floor<=fence_source;floor_valid<=1;obs_have<=0;read_have<=0;
     if(fence_read)begin stage<=`GB4_STAGE_WAIT_READ;floor_pending<=1;floor_published<=0;end
     else stage<=`GB4_STAGE_OBSERVE;
    end
   end
   // Observe motion as well as park: a post-epoch floor is needed to STOP on
   // genuinely new moving imagery. NEGATIVE only passes the parked READY gate.
   if(task_active&&state_owner&&vehicle_action==action_id&&!floor_valid&&!fence_wait&&fence_idle&&!hold_context&&!consume_rx)begin
    fence_request<=1;fence_wait<=1;fence_discard<=0;
   end
   if(observation_update&&task_active&&obs_post_floor)begin
    if(observation_kind==3)begin fail_task(`GB4_REASON_OBSERVATION_ERROR);end
    else if((raw_positive||(raw_negative&&ready_step&&stage==`GB4_STAGE_OBSERVE))&&(!obs_seen||observation_source!=obs_source))begin
     obs_seen<=1;obs_source<=observation_source;obs_ms<=now_ms[4:0];obs_have<=1;
     obs_positive<=raw_positive;obs_partial<=box_partial;
     if(raw_positive)begin
      found<=1;
      if(action_id!=0&&(stage==`GB4_STAGE_WAIT_ACTION||!owner_ready))stop_pending<=1;
     end else begin
      read_have<=0;result_pending<=0;reader_revoke<=1;
      if(stage==`GB4_STAGE_WAIT_READ)fail_task(`GB4_REASON_FRAME_STALE);
     end
    end
   end
   if(task_active&&found&&ready_read&&floor_valid&&!fence_read&&!fence_wait&&!hold_context&&!consume_rx)begin
    // A full credible box is required. A partial may stop, but never READ.
    if(obs_have&&obs_positive&&!obs_partial)begin
     fence_read<=1;floor_valid<=0;floor_published<=0;stage<=`GB4_STAGE_READ_FENCE;reader_revoke<=1;
    end
   end
   if(current_read_update&&task_active&&stage==`GB4_STAGE_WAIT_READ&&floor_valid&&ready_read&&healthy&&
      current_read_valid&&forward32(current_read_source,source_floor)&&(!read_seen||current_read_source!=read_source))begin
    read_seen<=1;read_source<=current_read_source;read_q<=raw_bar_q16;read_ms<=now_ms[7:0];read_have<=1;
   end
   if(task_active&&stage==`GB4_STAGE_WAIT_READ&&floor_published&&read_current&&!observation_update&&!consume_rx)
    result_pending<=1;
   if(rx_commit)begin
    if(rtype==1&&hello_shape&&hello_zero_sent&&!token_exhausted&&!expiry_pending)begin
     if(rkey==peer_session&&rtoken==token&&token!=0)begin
      if(!bound)begin bound<=1;seq_have<=1;rx_seq<=rseq;peer_ms<=now_ms[9:0];hello_pending<=1;end
      else if(new_seq)begin seq_have<=1;rx_seq<=rseq;end
     end else if(rtoken==0)begin
      if(rkey!=peer_session)begin
       if(task_active)begin analysis_cancel<=1;reader_revoke<=1;end
       task_active<=0;state_have<=0;state_owner<=0;task_have<=0;task_key<=0;action_id<=0;stage<=0;
       bound<=0;seq_have<=0;ack_pending<=0;stop_pending<=0;failure_pending<=0;revoke_visual;
       if(peer_session==0&&token==0)begin token<=rkey;peer_session<=rkey;end
       else if(token!=32'hffffffff)begin token<=token+1'b1;peer_session<=rkey;end
       else begin token_exhausted<=1;peer_session<=0;end
      end
      hello_pending<=1;
     end
    end else if(normal_header&&new_seq)begin
     if(rtype==2&&state_shape&&((task_active&&rkey==task_key)||(rkey==0&&raction==0)))begin
      rx_seq<=rseq;seq_have<=1;if(!task_active||rkey==task_key)peer_ms<=now_ms[9:0];state_ms<=now_ms[7:0];state_have<=1;
      vehicle_flags<=p[47:40];imu_age<=p[15:8]!=0?8'hff:p[7:0];park_six<=p[31:16]>=6000;
      vehicle_action<=raction[5:0];
      if(repoch!=vehicle_epoch||(rkey==0&&state_owner))begin
       revoke_visual;control_pending<=1;fence_read<=0;
       if(task_active)stage<=`GB4_STAGE_WAIT_READY;
      end
      vehicle_epoch<=repoch;state_owner<=task_active&&rkey==task_key;
      if(task_active&&rkey==task_key&&p[34:32]>=5)fail_task(p[39:35]==0?`GB4_REASON_OUTPUT_FAULT:p[39:35]);
     end else if(rtype==3&&start_shape&&repoch==vehicle_epoch)begin
      rx_seq<=rseq;seq_have<=1;
      if(task_have&&rkey==task_key)begin
       if(task_active&&direction==p[15]&&task_mode==p[16])acknowledge(`GB4_ACK_DUPLICATE);
       else acknowledge(`GB4_ACK_REJECTED);
      end else if(!task_active&&(!task_have||rkey>task_key)&&stationary_permit&&park_six&&local_permission)begin
       task_have<=1;task_active<=1;task_key<=rkey;direction<=p[15];task_mode<=p[16];action_id<=0;found<=0;
       state_owner<=0;stage<=`GB4_STAGE_WAIT_READY;failure_reason<=0;fence_read<=0;read_seen<=0;obs_seen<=0;
       stop_pending<=0;result_pending<=0;failure_pending<=0;revoke_visual;acknowledge(`GB4_ACK_ACCEPTED);
      end else acknowledge(`GB4_ACK_REJECTED);
     end else if(rtype==4&&active_context&&cancel_shape)begin
      rx_seq<=rseq;seq_have<=1;task_active<=0;stage<=`GB4_STAGE_CANCELLED;
      stop_pending<=1;analysis_cancel<=1;revoke_visual;acknowledge(`GB4_ACK_CANCELLED);
     end
    end
   end
   if(bound&&peer_age>=1000)begin
    bound<=0;expiry_pending<=1;state_have<=0;state_owner<=0;hello_pending<=1;
    if(task_active)fail_task(`GB4_REASON_LINK_STALE);
   end
   // Revoke permits on the deadline itself, but retain the old token/key
   // selection until all seven committed RAM writes finish. No HELLO may
   // bind while this expiry drains; the next explicit request gets a new token.
   if(expiry_pending&&!hold_context)begin peer_session<=0;expiry_pending<=0;end
   // The payload is frozen once; physical serialization uses the committed RAM.
   if(slot)begin
    tx_owned<=task_active;tx_action<=action_id;tx_payload<=0;
    if(hello_pending||!bound&&tx_due)begin
     tx_kind<=1;tx_action<=0;tx_owned<=0;
     tx_payload<={16'd0,8'd4,8'd32,16'd127,32'd`GB4_FPGA_BUILD};hello_pending<=0;
     if(token==0)zero_inflight<=1;
     frame_send<=1;send_selected=1;
    end else if(stop_pending)begin
     tx_kind<=10;tx_owned<=1;tx_payload<={8'd0,3'd0,(task_active?5'd24:failure_reason),((task_active&&obs_have&&obs_positive)?obs_flags:16'd0),((task_active&&obs_have&&obs_positive)?obs_wire_age:16'hffff),obs_source};stop_pending<=0;frame_send<=1;send_selected=1;
    end else if(failure_pending)begin
     tx_kind<=8;tx_owned<=1;tx_payload<={32'd0,8'd0,3'd0,failure_reason,source_floor};failure_pending<=0;frame_send<=1;send_selected=1;
    end else if(ack_pending)begin
     tx_kind<=5;tx_owned<=1;tx_payload<={40'd0,8'd0,5'd0,ack_status,4'd0,ack_type,ack_seq};ack_pending<=0;frame_send<=1;send_selected=1;
    end else if(floor_pending&&task_active)begin
     tx_kind<=6;tx_payload<={8'd0,8'd6,16'd131,16'hffff,source_floor};floor_pending<=0;floor_inflight<=1;frame_send<=1;send_selected=1;
    end else if(result_pending&&read_current&&decision_safe)begin
     tx_kind<=7;tx_owned<=1;tx_payload<={8'd0,8'd3,6'd0,read_wire_age,read_q,read_source};
     result_pending<=0;task_active<=0;stage<=`GB4_STAGE_COMPLETE;frame_send<=1;send_selected=1;
    end else if(task_active&&stage==`GB4_STAGE_OBSERVE&&ready_step&&floor_valid&&obs_have&&!obs_positive&&!found&&decision_safe)begin
     if(action_id<36)begin
      tx_kind<=9;tx_owned<=1;tx_action<=action_id+1'b1;
      tx_payload<={16'd35,direction?-16'sd10000:16'sd10000,obs_wire_age,obs_source};
      action_id<=action_id+1'b1;stage<=`GB4_STAGE_WAIT_ACTION;obs_have<=0;fence_read<=0;
      reader_revoke<=1;frame_send<=1;send_selected=1;
     end else fail_task(`GB4_REASON_ACTION_LIMIT);
    end else if(bound&&(tx_due||control_pending))begin
     tx_kind<=6;tx_owned<=task_active;frame_send<=1;send_selected=1;control_pending<=0;
     if(control_pending)tx_payload<={3'd0,failure_reason,4'd0,stage,16'd3,16'hffff,32'd0};
     else if(obs_have&&floor_valid)tx_payload<={3'd0,failure_reason,4'd0,stage,obs_flags,obs_wire_age,obs_source};
     else tx_payload<={3'd0,failure_reason,4'd0,stage,5'd0,1'b1,8'd0,healthy,camera_alive,16'd0,camera_source};
    end
    if(send_selected)begin
     tx_seq<=tx_seq+1'b1;tx_ms<=now_ms[7:0];tx_due<=0;
    end
   end
   // Global safety has final priority over all newly selected motion/reading.
   // A previously committed atomic frame is allowed to finish; receivers still
   // reject its revoked context/age. STOP/FAIL retain priority in the next slot.
   if(immediate_cancel)begin
    task_active<=0;stage<=`GB4_STAGE_CANCELLED;stop_pending<=1;analysis_cancel<=1;revoke_visual;
   end
   if(fatal_local)begin
    if(!bound)fail_task(`GB4_REASON_LINK_STALE);
    else if(!state_fresh)fail_task(`GB4_REASON_STATE_STALE);
    else if(vehicle_flags[5])fail_task(`GB4_REASON_IMU_FAULT);
    else if(!healthy)fail_task(`GB4_REASON_ANALYSIS_FAULT);
    else fail_task(`GB4_REASON_CAMERA_STALE);
   end
  end
 end
endmodule
