//128rawROI bounded hub-ring kernel; no independent read authority.
// External grayscale RAM: one synchronous read response, no backpressure.
// All addresses belong to an externally frozen128x128 ROI for the whole busy.
module t06_meter_hub128(
    input wire clk,
    input wire rst_n,
    input wire start,
    input wire cancel,
    output reg rd_en,
    output reg [15:0] rd_addr,
    input wire [7:0] rd_data,
    output reg busy,
    output reg done,
    output reg hub_valid,
    output reg [7:0] hub_x,
    output reg [7:0] hub_y,
    output reg [4:0] hub_radius,
    output reg signed [15:0] hub_score,
    output reg [4:0] hub_support
);
    // Separate ROM decode, multiplication, coordinate rounding and RAM address
    // construction. No stage combines trig decode and DSP/adder address logic.
    localparam IDLE=0,TRIG_REG=1,MULT_REG=2,COORD_REG=3,
               ISSUE=4,WAIT_RD=5,GET=6,EVAL=7,FINISH=8;
    reg [3:0] state;
    reg [7:0] cx,cy;
    reg [4:0] radius;
    reg [3:0] direction;
    reg [1:0] sample_sel;
    reg [7:0] inner_gray,ring_gray;
    reg signed [15:0] total;
    reg [4:0] support;
    reg signed [15:0] best_total;

    function [31:0] trig;
      input [3:0] k;
      begin
        case(k)
          0:trig=32'h04000000;1:trig=32'h03b50180;
          2:trig=32'h02d402d4;3:trig=32'h019003af;
          4:trig=32'h00000400;5:trig=32'hfe8003b5;
          6:trig=32'hfd2c02d4;7:trig=32'hfc510190;
          8:trig=32'hfc000000;9:trig=32'hfc4bfe80;
          10:trig=32'hfd2cfd2c;11:trig=32'hfe70fc51;
          12:trig=32'h0000fc00;13:trig=32'h0180fc4b;
          14:trig=32'h02d4fd2c;default:trig=32'h03affe70;
        endcase
      end
    endfunction
    wire [31:0] trig_value=trig(direction);
    reg signed [15:0] cosq,sinq;
    wire [5:0] sample_radius=(sample_sel==0)?({1'b0,radius}-6'd2):
                                  (sample_sel==1)?{1'b0,radius}:({1'b0,radius}+6'd2);
    reg [5:0] sample_radius_q;
    reg signed [23:0] xprod,yprod;
    wire signed [23:0] xoff=(xprod+24'sd512)>>>10;
    wire signed [23:0] yoff=(yprod+24'sd512)>>>10;
    reg signed [24:0] sx,sy;
    // Coordinates are provably0..191 in this fixed hub envelope. Explicit16bit
    // shift/add prevents a general25x25multiply in the rd_addr timing cone.
    wire [15:0] sx16=sx[15:0],sy16=sy[15:0];
    wire [15:0] address_shiftadd=(sy16<<7)+sx16;
    wire signed [10:0] contrast=$signed({3'b0,inner_gray})+$signed({3'b0,rd_data})-
                               ($signed({3'b0,ring_gray})<<<1);
    wire [7:0] adx=(cx>=64)?cx-64:64-cx;
    wire [7:0] ady=(cy>=64)?cy-64:64-cy;
    wire [4:0] adr=(radius>=7)?radius-7:7-radius;
    wire signed [15:0] penalty=$signed({1'b0,adx}+{1'b0,ady})*16'sd4+
                                  $signed({1'b0,adr})*16'sd8;
    wire signed [15:0] current_score=total-penalty;
    always @(posedge clk or negedge rst_n) begin
      if(!rst_n) begin
        state<=IDLE;busy<=0;done<=0;rd_en<=0;rd_addr<=0;
        hub_valid<=0;hub_x<=0;hub_y<=0;hub_radius<=0;
        hub_score<=-16'sd32767;hub_support<=0;
        cx<=58;cy<=58;radius<=5;direction<=0;sample_sel<=0;
        inner_gray<=0;ring_gray<=0;total<=0;support<=0;best_total<=0;
        cosq<=0;sinq<=0;sample_radius_q<=0;xprod<=0;yprod<=0;sx<=0;sy<=0;
      end else begin
        done<=0;rd_en<=0;
        if(cancel) begin
          state<=IDLE;busy<=0;hub_valid<=0;
          hub_x<=0;hub_y<=0;hub_radius<=0;
          hub_score<=-16'sd32767;hub_support<=0;
        end else case(state)
          IDLE:if(start) begin
            busy<=1;hub_valid<=0;hub_x<=0;hub_y<=0;hub_radius<=0;
            hub_score<=-16'sd32767;hub_support<=0;best_total<=0;
            cx<=58;cy<=58;radius<=5;direction<=0;sample_sel<=0;
            total<=0;support<=0;state<=TRIG_REG;
          end
          TRIG_REG:begin
            cosq<=trig_value[31:16];sinq<=trig_value[15:0];
            sample_radius_q<=sample_radius;state<=MULT_REG;
          end
          MULT_REG:begin
            xprod<=cosq*$signed({1'b0,sample_radius_q});
            yprod<=sinq*$signed({1'b0,sample_radius_q});state<=COORD_REG;
          end
          COORD_REG:begin
            sx<=$signed({1'b0,cx})+xoff;
            sy<=$signed({1'b0,cy})+yoff;state<=ISSUE;
          end
          ISSUE:begin
            // Bound by cx58..70,cy58..70,radius<=12; physical128ROI bound safe.
            rd_en<=1;rd_addr<=address_shiftadd;state<=WAIT_RD;
          end
          WAIT_RD:state<=GET;
          GET:begin
            if(sample_sel==0) begin inner_gray<=rd_data;sample_sel<=1;state<=TRIG_REG;end
            else if(sample_sel==1) begin ring_gray<=rd_data;sample_sel<=2;state<=TRIG_REG;end
            else begin
              total<=total+contrast;
              if(contrast>11'sd6)support<=support+1'b1;
              sample_sel<=0;
              if(direction==15)state<=EVAL;
              else begin direction<=direction+1'b1;state<=TRIG_REG;end
            end
          end
          EVAL:begin
            if((current_score>hub_score)&&(total>=16'sd160)&&(support>=9)) begin
              hub_score<=current_score;hub_x<=cx;hub_y<=cy;
              hub_radius<=radius;hub_support<=support;best_total<=total;
            end
            direction<=0;sample_sel<=0;total<=0;support<=0;
            if(radius<10)begin radius<=radius+1'b1;state<=TRIG_REG;end
            else if(cx<70)begin radius<=5;cx<=cx+1'b1;state<=TRIG_REG;end
            else if(cy<70)begin radius<=5;cx<=58;cy<=cy+1'b1;state<=TRIG_REG;end
            else state<=FINISH;
          end
          FINISH:begin
            hub_valid<=(best_total>=16'sd160)&&(hub_support>=9);
            busy<=0;done<=1;state<=IDLE;
          end
          default:begin state<=IDLE;busy<=0;hub_valid<=0;end
        endcase
      end
    end
endmodule
