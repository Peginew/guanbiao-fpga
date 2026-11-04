// Sparse original-RGB statistics. No ready, frame buffer, or video feedback.
// SOF may precede pixels or coincide with pixel group zero. A summary closes
// only at the following SOF; EOL positions and total groups must both agree.
module t06_quality_stats #(
 parameter IMG_WIDTH=1280, IMG_HEIGHT=720, SAMPLE_PIXELS=8, SAMPLE_ROWS=8,
 parameter MIN_NEUTRAL=16
)(
 input I_clk,I_rst_n,I_tuser,I_tlast,I_tvalid,I_abort,
 input [95:0] I_tdata,
 output reg O_valid,O_good,
 output reg [31:0] O_frame,
 output reg [23:0] O_y_sum,
 output reg [15:0] O_count,O_dark,O_bright,O_global_count,O_global_bright,
 output reg [23:0] O_r_sum,O_g_sum,O_b_sum,
 output reg [15:0] O_neutral_count
);
 localparam GROUPS=IMG_WIDTH/4, TOTAL=GROUPS*IMG_HEIGHT;
 localparam SX=(SAMPLE_PIXELS<4)?1:SAMPLE_PIXELS/4;
 reg active,bad;
 localparam GW=(TOTAL+2<=2)?1:$clog2(TOTAL+2);
 localparam XW=(GROUPS<=2)?1:$clog2(GROUPS);
 localparam YW=(IMG_HEIGHT+2<=2)?1:$clog2(IMG_HEIGHT+2);
 reg [31:0] frame_id;
 reg [GW-1:0] groups_seen;
 reg [XW-1:0] x;
 reg [YW-1:0] y;
 reg [23:0] sy,sr,sg,sb;
 reg [15:0] n,nd,nb,ng,ngb,nn;
 wire [7:0] r=I_tdata[23:16], g=I_tdata[15:8], b=I_tdata[7:0];
 // Integer coefficients sum to 256; addition operands explicitly extended.
 // Exact original unrounded77/150/29 dot product; three spareDSPs.
 (* dsp_style="yes" *) wire [15:0] yr=r*8'd77;
 (* dsp_style="yes" *) wire [15:0] yg=g*8'd150;
 (* dsp_style="yes" *) wire [15:0] yb=b*8'd29;
 wire [15:0] weighted=yr+yg+yb;
 wire [7:0] lum=weighted[15:8];
 wire [7:0] hi=(r>g)?((r>b)?r:b):((g>b)?g:b);
 wire [7:0] lo=(r<g)?((r<b)?r:b):((g<b)?g:b);
 wire neutral=(lo>=24)&&(hi<=235)&&({1'b0,hi}<=({1'b0,lo}<<1));
 wire [15:0] px=I_tuser?16'd0:x, py=I_tuser?16'd0:y;
 wire sparse=((px%SX)==0)&&((py%SAMPLE_ROWS)==0);
 wire center=(px>=GROUPS/4)&&(px<(3*GROUPS)/4)&&
             (py>=IMG_HEIGHT/4)&&(py<(3*IMG_HEIGHT)/4);
 wire accept=I_tvalid&&(I_tuser||active);
 always @(posedge I_clk or negedge I_rst_n) begin
  if(!I_rst_n) begin
   active<=0;bad<=0;frame_id<=0;groups_seen<=0;x<=0;y<=0;
   sy<=0;sr<=0;sg<=0;sb<=0;n<=0;nd<=0;nb<=0;ng<=0;ngb<=0;nn<=0;
   O_valid<=0;O_good<=0;O_frame<=0;O_y_sum<=0;O_count<=0;
   O_dark<=0;O_bright<=0;O_global_count<=0;O_global_bright<=0;
   O_r_sum<=0;O_g_sum<=0;O_b_sum<=0;O_neutral_count<=0;
  end else begin
   O_valid<=0;
   if(I_tuser) begin
    if(active) begin
     O_valid<=1;O_good<=!bad&&!I_abort&&(groups_seen==TOTAL)&&(x==0)&&(y==IMG_HEIGHT);
     O_frame<=frame_id;O_y_sum<=sy;O_count<=n;O_dark<=nd;O_bright<=nb;
     O_global_count<=ng;O_global_bright<=ngb;
     O_r_sum<=sr;O_g_sum<=sg;O_b_sum<=sb;O_neutral_count<=nn;
    end
    active<=1;frame_id<=active?(frame_id+1'b1):32'd0;
    bad<=I_abort;groups_seen<=0;x<=0;y<=0;
    sy<=0;sr<=0;sg<=0;sb<=0;n<=0;nd<=0;nb<=0;ng<=0;ngb<=0;nn<=0;
   end else if(I_abort&&active) bad<=1;
   if(accept) begin
    // Saturation means malformed overlong frames never wrap into validity.
    groups_seen<=I_tuser?32'd1:((groups_seen<TOTAL+1)?groups_seen+1'b1:groups_seen);
    if((!I_tuser&&(groups_seen>=TOTAL))||(I_tlast!=(px==GROUPS-1))) bad<=1;
    if(px==GROUPS-1) begin x<=0;y<=(py<IMG_HEIGHT+1)?py+1'b1:py;end
    else begin x<=px+1'b1;y<=py;end
    if(sparse) begin
     ng<=I_tuser?16'd1:ng+1'b1;
     if(lum>=240) ngb<=I_tuser?16'd1:ngb+1'b1;
     if(center) begin
      sy<=I_tuser?{16'd0,lum}:sy+lum;
      n<=I_tuser?16'd1:n+1'b1;
      if(lum<48) nd<=I_tuser?16'd1:nd+1'b1;
      if(lum>=240) nb<=I_tuser?16'd1:nb+1'b1;
      if(neutral) begin
       sr<=I_tuser?{16'd0,r}:sr+r;sg<=I_tuser?{16'd0,g}:sg+g;
       sb<=I_tuser?{16'd0,b}:sb+b;nn<=I_tuser?16'd1:nn+1'b1;
      end
     end
    end
   end
  end
 end
endmodule
