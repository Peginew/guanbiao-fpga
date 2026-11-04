// Native, non-stalling RGB byte stream packer. High byte is earliest.
// Four 96-bit beats -> three 128-bit words. Bubbles NEVER reset phase.
// WIDTH must be divisible by 16. Frame pulse is separate from word SOF.
module t06_pack96_128(
 input clk, rst_n, input [95:0] s_data,
 input s_valid, s_sof, s_eol,
 output reg [127:0] m_data, output reg m_valid, m_sof, m_eol,
 output reg format_error
);
 reg [95:0] previous;
 reg [1:0] phase;
 reg first_word;
 wire [1:0] current_phase = s_sof ? 2'd0 : phase;
 always @(posedge clk or negedge rst_n) begin
  if(!rst_n) begin
   previous<=0;phase<=0;first_word<=0;
   m_data<=0;m_valid<=0;m_sof<=0;m_eol<=0;format_error<=0;
  end else begin
   m_valid<=0;m_sof<=0;m_eol<=0;
   if(s_valid) begin
    if(s_sof) begin
     first_word<=1;
     if(phase!=0) format_error<=1;
    end
    previous<=s_data;
    phase<=current_phase+1'b1;
    if(s_eol && current_phase!=3) format_error<=1;
    case(current_phase)
     0: begin end
     1: begin m_data<={previous,s_data[95:64]};m_valid<=1;m_sof<=first_word;first_word<=0;end
     2: begin m_data<={previous[63:0],s_data[95:32]};m_valid<=1;end
     3: begin m_data<={previous[31:0],s_data};m_valid<=1;m_eol<=s_eol;end
    endcase
   end
  end
 end
endmodule
