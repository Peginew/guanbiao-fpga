// Display-only psi formatter. Inputs MUST be the same-observation LAST package,
// not live/working q16. Does not change calibration, inference, or READ permits.
//
// One job owns the two serial engines until it drains. A sticky current flag
// can be cleared by withdrawal or any owner/value change, but is never restored
// while that job is running. Thus same-source/same-value reentry cannot revive
// a completion from before cancellation. Busy updates retain only the latest
// request; no queue, timeout, bus, new clock or asynchronous reset is introduced.
module t06_ui_pressure_display (
 input wire clk,rst_n,value_update,value_valid,revoke,
 input wire [15:0] bar_q16,
 input wire [31:0] source_id,
 output reg psi_update,
 output wire psi_valid,
 output reg [15:0] psi_hundredths,psi_bcd,
 output reg [31:0] psi_source
);
 reg [1:0] state;
 reg have_request;
 reg [15:0] latest_q16,job_q16,held_q16,job_psi;
 reg [31:0] latest_source,job_source;
 reg job_current,held_valid;
 reg p_start,b_start;
 reg [31:0] b_value;
 wire p_busy,p_done,b_busy,b_done;
 wire [15:0] p_value;
 wire [39:0] b_value_bcd;
 wire request_available=value_valid&&!revoke&&(value_update||have_request);
 wire [15:0] request_q16=value_update?bar_q16:latest_q16;
 wire [31:0] request_source=value_update?source_id:latest_source;
 wire request_is_current=request_available&&request_q16==bar_q16&&request_source==source_id;
 wire job_is_current=value_valid&&!revoke&&job_q16==bar_q16&&job_source==source_id;
 wire latest_is_job=request_is_current&&request_q16==job_q16&&request_source==job_source;
 assign psi_valid=held_valid&&value_valid&&!revoke&&held_q16==bar_q16&&psi_source==source_id;

 t06_ui_barq16_psi100 convert_psi(
  .clk(clk),.rst_n(rst_n),.start(p_start),.bar_q16(job_q16),
  .busy(p_busy),.done(p_done),.psi_hundredths(p_value));
 t06_ui_bin32_bcd convert_bcd(
  .clk(clk),.rst_n(rst_n),.start(b_start),.value(b_value),
  .busy(b_busy),.done(b_done),.bcd(b_value_bcd));

 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=0;have_request<=0;latest_q16<=0;latest_source<=0;
   job_q16<=0;job_source<=0;job_current<=0;job_psi<=0;
   held_valid<=0;held_q16<=0;psi_update<=0;psi_hundredths<=0;psi_bcd<=0;psi_source<=0;
   p_start<=0;b_start<=0;b_value<=0;
  end else begin
   psi_update<=0;p_start<=0;b_start<=0;
   if(revoke||!value_valid)begin
    have_request<=0;held_valid<=0;job_current<=0;
   end else begin
    if(value_update)begin
     have_request<=1;latest_q16<=bar_q16;latest_source<=source_id;
    end
    if(held_valid&&(held_q16!=bar_q16||psi_source!=source_id))held_valid<=0;
   end
   if(state!=0&&!job_is_current)job_current<=0;
   case(state)
    0:if(request_is_current&&!p_busy&&!b_busy&&
         (!held_valid||held_q16!=request_q16||psi_source!=request_source))begin
      job_q16<=request_q16;job_source<=request_source;job_current<=1;
      p_start<=1;state<=1;
     end
    1:if(p_done)begin
      if(job_current&&job_is_current&&latest_is_job)begin
       job_psi<=p_value;b_value<={16'd0,p_value};b_start<=1;state<=2;
      end else state<=0;
     end
    2:if(b_done)begin
      if(job_current&&job_is_current&&latest_is_job)begin
       psi_hundredths<=job_psi;psi_bcd<=b_value_bcd[15:0];psi_source<=job_source;
       held_q16<=job_q16;held_valid<=1;psi_update<=1;
      end
      state<=0;
     end
    default:begin state<=0;job_current<=0;end
   endcase
  end
 end
endmodule
