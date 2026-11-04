// Optional exact arithmetic mapping: trade twelve otherwise idle DSP multipliers
// for grayconstantmultiply logic. Combinational; the existing gray0 register
// remains the only sample stage. Do not add this module unless fullproject
// actual mapping proves the trade and final STA passes.
module t06_gray4_exact_dsp(input [95:0] rgb4,output [31:0] gray4);
 genvar lane;
 generate for(lane=0;lane<4;lane=lane+1)begin:g_lane
  wire [23:0] p=rgb4[95-24*lane -:24];
  (* dsp_style="yes" *) wire [15:0] pr=p[23:16]*8'd77;
  (* dsp_style="yes" *) wire [15:0] pg=p[15:8]*8'd150;
  (* dsp_style="yes" *) wire [15:0] pb=p[7:0]*8'd29;
  wire [15:0] weighted=pr+pg+pb+16'd128;
  assign gray4[31-8*lane -:8]=weighted[15:8];
 end endgenerate
endmodule
