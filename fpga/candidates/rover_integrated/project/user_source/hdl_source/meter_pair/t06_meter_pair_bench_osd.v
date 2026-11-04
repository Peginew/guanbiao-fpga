// STATIC FRONTAL BENCH: held output labelled LAST, never a current READ permit.
// Source-safe resultauxiliary. HDMI-domainonly; combinationalRGB,noaddedvideodelay.
// AgeA is unsignedsource-frame difference inHEX,notmilliseconds;K israwangleindexHEX.
// Cyan geometry is exact-source; orange geometry is explicitly aged evidence.
// HOLD_RESULTS only retains display evidence; future/replay/revoke/raster checks remain.
// DBG describes the latest completed reader job with its original source.
module t06_meter_pair_bench_osd #(
 parameter PANEL_X=640,PANEL_Y0=592,PANEL_Y1=624,MAX_SOURCE_AGE=12,
 parameter MAX_WALL_CYCLES=15000000,SOURCE_X_OFFSET=2,ENABLE_CAPTURE_DIAGNOSTICS=0,
 parameter HOLD_RESULTS=0,TRIG_FILE="C:/Users/Edward/Desktop/FPGA/Stable3s_Rover_Merged_20261104/fpga/project/user_source/hdl_source/meter_pair/needle_trig128.hex",SEPARATE_GEOMETRY_BOX=0,HELD_ONLY_ENABLE=0,DRAW_TEXT=1
)(
 input clk,rst_n,vs,de,input [23:0] rgb,
 input update,input [251:0] payload,input [71:0] debug_payload,input revoke,
 input [120:0] capture_debug_payload,
 input [43:0] geometry_box_payload,
 input geometry_held_only,
 input display_id_valid,input [31:0] display_source_id,input display_good,display_fault,
 output wire [23:0] out_rgb,
 // Passive same-clock presentation taps; consumers must use qualified_flags.
 output wire [251:0] qualified_payload,
 output wire [71:0] qualified_debug,
 output wire [3:0] qualified_flags,
 output wire qualified_estimated,
 output wire [31:0] age_loc,age_geo,age_read
);
 wire fc,rc,cv;wire [10:0] fx0,fy0,fx1,fy1,fcx,fcy,hx,hy;wire [31:0] fid,rid,csource;
 wire [15:0] ftarget,score,cbcd;wire [8:0] angle;wire [7:0] reason_in;
 assign {fc,fx0,fy0,fx1,fy1,fcx,fcy,fid,ftarget,score,rc,rid,hx,hy,angle,cv,cbcd,csource,reason_in}=payload;
 reg [251:0] pending,shown;reg have_pending,have_shown;
 // Optional sideband is sampled with exactly the same update/VS as payload.
 // Legacy consumers keep their existing shared-box behavior by default.
 reg [43:0] geometry_box_pending,geometry_box_shown;
 reg held_only_pending,held_only_shown;
 wire live_held_only=HELD_ONLY_ENABLE&&geometry_held_only;
 wire next_held_only=update?live_held_only:held_only_pending;
 wire [43:0] next_geometry_box=update?geometry_box_payload:geometry_box_pending;
 wire dv;wire [31:0] ds;wire [4:0] dq,df;
 wire [5:0] dm;wire [9:0] dd;wire signed [4:0] dr;wire [7:0] dc;
 assign {dv,ds,dq,dm,df,dd,dr,dc}=debug_payload;
 reg [71:0] debug_pending,debug_shown;
 reg [120:0] capture_pending,capture_shown;
 wire [4:0] cap_reason;wire [52:0] cap_diag;wire [10:0] cap_x;wire [9:0] cap_y;
 wire [2:0] cap_stride;wire [6:0] cap_radius;wire [31:0] cap_hint;
 assign {cap_reason,cap_diag,cap_x,cap_y,cap_stride,cap_radius,cap_hint}=capture_shown;
 wire [11:0] cap_first=cap_diag[52:41];wire cap_bad=cap_diag[40],cap_full=cap_diag[39];
 wire [17:0] cap_groups=cap_diag[38:21];wire [14:0] cap_writes=cap_diag[20:6];wire [5:0] cap_close=cap_diag[5:0];
 wire adv;wire [31:0] ads;wire [4:0] adq,adf;
 wire [5:0] adm;wire [9:0] add;wire signed [4:0] adr;wire [7:0] adc;
 assign {adv,ads,adq,adm,adf,add,adr,adc}=debug_shown;
 reg debug_allowed,debug_seen,debug_blocked;reg [31:0] debug_floor;
 wire [31:0] debug_delta=ds-debug_floor;
 wire debug_new=!debug_seen||(!debug_delta[31]&&(debug_delta!=0||!debug_blocked));
 wire [71:0] debug_filtered={dv&&debug_new,ds,dq,dm,df,dd,dr,dc};
 wire [71:0] debug_next=update?debug_filtered:debug_pending;
 wire afc,arc,acv;wire [10:0] ax0,ay0,ax1,ay1,acx,acy,ahx,ahy;
 wire [31:0] aid,arid,amsrc;wire [15:0] atarget,ascore,abcd;wire [8:0] aangle;wire [7:0] areason;
 assign {afc,ax0,ay0,ax1,ay1,acx,acy,aid,atarget,ascore,arc,arid,ahx,ahy,aangle,acv,abcd,amsrc,areason}=shown;
 reg candidate_allowed,geometry_allowed,measure_allowed;
 reg [31:0] candidate_floor,geometry_floor,measure_floor;
 reg seen_candidate,seen_geometry,seen_measure,blocked_candidate,blocked_geometry,blocked_measure;
 wire [31:0] cdelta=fid-candidate_floor,gdelta=rid-geometry_floor,mdelta=csource-measure_floor;
 wire cnew=!seen_candidate||(!cdelta[31]&&(cdelta!=0||!blocked_candidate));
 wire gnew=!seen_geometry||(!gdelta[31]&&(gdelta!=0||!blocked_geometry));
 wire mnew=!seen_measure||(!mdelta[31]&&(mdelta!=0||!blocked_measure));
 wire [251:0] filtered={fc&&cnew,fx0,fy0,fx1,fy1,fcx,fcy,fid,ftarget,score,
                     rc&&gnew,rid,hx,hy,angle,cv&&mnew,cbcd,csource,reason_in};
 wire [251:0] next_shown=update?filtered:pending;
 wire nfc,nrc,ncv;wire [10:0] nx0,ny0,nx1,ny1,ncx,ncy,nhx,nhy;
 wire [31:0] nid,nrid,nmsrc;wire [15:0] ntarget,nscore,nbcd;wire [8:0] nangle;wire [7:0] nreason;
 assign {nfc,nx0,ny0,nx1,ny1,ncx,ncy,nid,ntarget,nscore,nrc,nrid,nhx,nhy,nangle,ncv,nbcd,nmsrc,nreason}=next_shown;
 reg vs_prev,de_prev;reg [10:0] x,y;
 wire boundary=vs&&!vs_prev;
 reg raster_known,raster_good,raster_conflict;reg [31:0] raster_id;
 reg [23:0] candidate_wall,measure_wall,geometry_wall,debug_wall;
 reg [15:0] cx_bcd,cy_bcd;
 function [15:0] binary_bcd;
  input [10:0] value;reg [26:0] scratch;integer i,j;
  begin scratch=0;scratch[10:0]=value;
   for(i=0;i<11;i=i+1)begin
    for(j=0;j<4;j=j+1)if(scratch[11+j*4 +:4]>=5)scratch[11+j*4 +:4]=scratch[11+j*4 +:4]+3;
    scratch=scratch<<1;
   end
   binary_bcd=scratch[26:11];
  end
 endfunction
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   pending<=0;shown<=0;debug_pending<=0;debug_shown<=0;debug_allowed<=0;
   geometry_box_pending<=0;geometry_box_shown<=0;
   held_only_pending<=0;held_only_shown<=0;
   debug_seen<=0;debug_blocked<=0;debug_floor<=0;capture_pending<=0;capture_shown<=0;
   have_pending<=0;have_shown<=0;candidate_allowed<=0;geometry_allowed<=0;measure_allowed<=0;
   candidate_floor<=0;geometry_floor<=0;measure_floor<=0;seen_candidate<=0;seen_geometry<=0;seen_measure<=0;
   blocked_candidate<=0;blocked_geometry<=0;blocked_measure<=0;
   vs_prev<=0;de_prev<=0;x<=0;y<=0;raster_known<=0;raster_good<=0;raster_conflict<=0;raster_id<=0;
   candidate_wall<=0;measure_wall<=0;geometry_wall<=0;debug_wall<=0;cx_bcd<=0;cy_bcd<=0;
  end else begin
   vs_prev<=vs;de_prev<=de;
   if(boundary)begin x<=0;y<=0;raster_known<=0;raster_good<=0;raster_conflict<=0;end
   else begin
    if(!de)x<=0;else if(x!=2047)x<=x+1'b1;
    if(de_prev&&!de&&y!=2047)y<=y+1'b1;
   end
   if(display_id_valid&&!boundary&&!raster_known)begin raster_known<=1;raster_id<=display_source_id;raster_good<=display_good&&!display_fault;end
   if(display_id_valid&&!boundary&&raster_known&&(display_source_id!=raster_id||!display_good||display_fault))raster_conflict<=1;
   if(display_fault||(raster_known&&!display_good))raster_good<=0;
   if(candidate_wall<MAX_WALL_CYCLES)candidate_wall<=candidate_wall+1'b1;
   if(!HOLD_RESULTS&&measure_wall<MAX_WALL_CYCLES)measure_wall<=measure_wall+1'b1;
   if(!HOLD_RESULTS&&geometry_wall<MAX_WALL_CYCLES)geometry_wall<=geometry_wall+1'b1;
   if(!HOLD_RESULTS&&debug_wall<MAX_WALL_CYCLES)debug_wall<=debug_wall+1'b1;
   if(revoke||display_fault)begin
    have_pending<=0;have_shown<=0;candidate_allowed<=0;geometry_allowed<=0;measure_allowed<=0;debug_allowed<=0;raster_good<=0;
    debug_blocked<=debug_seen;
    blocked_candidate<=seen_candidate;blocked_geometry<=seen_geometry;blocked_measure<=seen_measure;
    // Same-cyclearrivalisrevokedtoo;laterretransmitofthesamesourcecannotreviveit.
    if(update&&fc&&cnew)begin candidate_floor<=fid;seen_candidate<=1;blocked_candidate<=1;end
    if(update&&rc&&gnew)begin geometry_floor<=rid;seen_geometry<=1;blocked_geometry<=1;end
    if(update&&cv&&mnew)begin measure_floor<=csource;seen_measure<=1;blocked_measure<=1;end
    if(update&&dv&&debug_new)begin debug_floor<=ds;debug_seen<=1;debug_blocked<=1;end
   end else begin
    if(update)begin
     pending<=filtered;debug_pending<=debug_filtered;capture_pending<=capture_debug_payload;have_pending<=1;
     geometry_box_pending<=geometry_box_payload;
     held_only_pending<=live_held_only;
     if(dv&&debug_new)begin debug_floor<=ds;debug_seen<=1;debug_blocked<=0;end
     else begin debug_allowed<=0;debug_blocked<=debug_seen;end
     if(fc&&cnew)begin candidate_floor<=fid;seen_candidate<=1;blocked_candidate<=0;end
     else begin candidate_allowed<=0;blocked_candidate<=seen_candidate;end
     if(rc&&gnew)begin geometry_floor<=rid;seen_geometry<=1;blocked_geometry<=0;end
     // In HOLD mode rc is the parent's current, trusted position association.
     // Losing that association hides the old overlay, but is not a hard revoke
     // of its source. The same held source may reappear only after rc returns
     // and the next VS atomically accepts it. Hard revoke still blocks replay.
     else begin geometry_allowed<=0;if(!HOLD_RESULTS)blocked_geometry<=seen_geometry;end
     if(cv&&mnew)begin measure_floor<=csource;seen_measure<=1;blocked_measure<=0;end
     else begin measure_allowed<=0;blocked_measure<=seen_measure;end
     if(have_shown&&ftarget!=atarget)begin candidate_allowed<=0;geometry_allowed<=0;measure_allowed<=0;debug_allowed<=0;end
    end
    if(boundary&&(have_pending||update))begin
     shown<=next_shown;debug_shown<=debug_next;capture_shown<=update?capture_debug_payload:capture_pending;have_shown<=1;have_pending<=0;
     geometry_box_shown<=next_geometry_box;
     held_only_shown<=next_held_only;
     debug_allowed<=debug_next[71];
     candidate_allowed<=nfc;geometry_allowed<=nrc;measure_allowed<=ncv;
     cx_bcd<=binary_bcd(ncx);cy_bcd<=binary_bcd(ncy);
     if(!have_shown||nid!=aid||ntarget!=atarget)candidate_wall<=0;
     if(!have_shown||nmsrc!=amsrc||ntarget!=atarget)measure_wall<=0;
     if(!have_shown||nrid!=arid||ntarget!=atarget)geometry_wall<=0;
     if(!have_shown||debug_next[70:39]!=ads||ntarget!=atarget)debug_wall<=0;
    end
   end
  end
 end
 wire healthy=have_shown&&raster_known&&raster_good&&!raster_conflict&&display_good&&!display_fault&&!revoke&&ftarget==atarget;
 // Registered metadata qualification, not a video pipeline. A newly published
 // raster descriptor is eligible one clock later. Clear on every VS so cached
 // age/source fields can never be applied to a newly activated shown bundle.
 wire [31:0] cage_next=raster_id-aid,mage_next=raster_id-amsrc;
 wire [31:0] gage_next=raster_id-arid,dage_next=raster_id-ads;
 reg [31:0] cage,mage,gage;
 reg c_source_age_ok,m_source_age_ok,g_source_age_ok,d_source_age_ok,c_exact,m_exact,geometry_exact_q;
 reg box_ok,bcd_good;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   cage<=0;mage<=0;gage<=0;c_source_age_ok<=0;m_source_age_ok<=0;g_source_age_ok<=0;d_source_age_ok<=0;
   c_exact<=0;m_exact<=0;geometry_exact_q<=0;box_ok<=0;bcd_good<=0;
  end else begin
   cage<=cage_next;mage<=mage_next;gage<=gage_next;
   if(boundary||!healthy)begin
    c_source_age_ok<=0;m_source_age_ok<=0;g_source_age_ok<=0;d_source_age_ok<=0;c_exact<=0;m_exact<=0;
    geometry_exact_q<=0;box_ok<=0;bcd_good<=0;
   end else begin
    c_source_age_ok<=!cage_next[31]&&cage_next<=MAX_SOURCE_AGE;
    m_source_age_ok<=!mage_next[31]&&(HOLD_RESULTS||mage_next<=MAX_SOURCE_AGE);
    g_source_age_ok<=!gage_next[31]&&(HOLD_RESULTS||gage_next<=MAX_SOURCE_AGE)&&ahx<1280&&ahy<720;
    d_source_age_ok<=!dage_next[31]&&(HOLD_RESULTS||dage_next<=MAX_SOURCE_AGE);
    c_exact<=cage_next==0;m_exact<=mage_next==0;
    geometry_exact_q<=!held_only_shown&&arid==raster_id&&ahx<1280&&ahy<720;
    box_ok<=ax0<ax1&&ay0<ay1&&ax1<=1280&&ay1<=720;
    bcd_good<=abcd[15:12]<=9&&abcd[11:8]<=9&&abcd[7:4]<=9&&abcd[3:0]<=9;
   end
  end
 end
 wire c_age_ok=c_source_age_ok&&candidate_wall<MAX_WALL_CYCLES;
 wire m_age_ok=m_source_age_ok&&(HOLD_RESULTS||measure_wall<MAX_WALL_CYCLES);
 // Held age stays32bit internally; two-hex display saturatesFF (>=255frames), never wraps00.
 wire [7:0] mage_display=|mage[31:8]?8'hff:mage[7:0],gage_display=|gage[31:8]?8'hff:gage[7:0];
 wire show_candidate=healthy&&candidate_allowed&&afc&&c_age_ok&&box_ok&&!(update&&!fc);
 wire estimated=show_candidate&&!c_exact;
 wire object_present=candidate_allowed&&afc&&box_ok&&!(update&&!fc);
 // LAST text is independent of the transient locator. In HOLD mode the
 // parent alone qualifies rc for a trustworthy current-position overlay;
 // cv remains the last successful number, never a current READ permission.
 wire show_geometry=healthy&&(HOLD_RESULTS||object_present)&&(HOLD_RESULTS||c_age_ok)&&geometry_allowed&&arc&&g_source_age_ok&&(HOLD_RESULTS||geometry_wall<MAX_WALL_CYCLES)&&!(update&&!rc);
 wire show_debug=healthy&&(HOLD_RESULTS||object_present)&&(HOLD_RESULTS||c_age_ok)&&debug_allowed&&adv&&d_source_age_ok&&(HOLD_RESULTS||debug_wall<MAX_WALL_CYCLES)&&!(update&&!dv);
 wire show_measure=healthy&&(HOLD_RESULTS||object_present)&&measure_allowed&&acv&&m_age_ok&&bcd_good&&!(update&&!cv);
 // Source pixel zero is observed at final raster X=2 in the retained video tail.
 // Reverse the fixed delay ONLY for drawing. Metadata and decimal text stay native.
 wire source_pixel=x>=SOURCE_X_OFFSET&&x<1280&&y<720;
 wire [10:0] source_x=x-SOURCE_X_OFFSET;
 wire box_edge=show_candidate&&source_pixel&&source_x>=ax0&&source_x<ax1&&y>=ay0&&y<ay1&&
               ((source_x==ax0||source_x==ax1-1)||(y==ay0||y==ay1-1));
 wire dash_on=(source_x==ax0||source_x==ax1-1)?y[3:0]<8:source_x[3:0]<8;
 wire box_ink=box_edge&&(!estimated||dash_on);
 wire [10:0] hub_dx=source_x>ahx?source_x-ahx:ahx-source_x,hub_dy=y>ahy?y-ahy:ahy-y;
 wire cross_ink=show_geometry&&source_pixel&&((source_x==ahx&&hub_dy<=5)||(y==ahy&&hub_dx<=5));
 // R=floor(7*min(saved T box W,H)/16). Its translated bounds are sampled
 // with the same T hub/angle/source; current locator U cannot resize LAST.
 wire [10:0] gx0,gy0,gx1,gy1,ngx0,ngy0,ngx1,ngy1;
 assign {gx0,gy0,gx1,gy1}=SEPARATE_GEOMETRY_BOX?geometry_box_shown:{ax0,ay0,ax1,ay1};
 assign {ngx0,ngy0,ngx1,ngy1}=SEPARATE_GEOMETRY_BOX?next_geometry_box:{nx0,ny0,nx1,ny1};
 wire geometry_box_ok=gx0<gx1&&gy0<gy1&&gx1<=1280&&gy1<=720;
 wire [10:0] next_box_w=ngx1-ngx0,next_box_h=ngy1-ngy0;
 wire [10:0] next_min_side=next_box_w<next_box_h?next_box_w:next_box_h;
 wire [12:0] next_radius7=({2'b0,next_min_side}<<2)+({2'b0,next_min_side}<<1)+{2'b0,next_min_side};
 wire next_line_box_ok=ngx0<ngx1&&ngy0<ngy1&&ngx1<=1280&&ngy1<=720;
 wire needle_ink;
 t06_meter_direction_line #(.TRIG_FILE(TRIG_FILE)) direction_line(
  .clk(clk),.rst_n(rst_n),.load(boundary&&(have_pending||update)),.invalidate(revoke||display_fault),
  .load_valid(nrc&&nangle<360&&next_line_box_ok),.load_angle(nangle),.load_radius(next_radius7[12:4]),.angle(aangle),
  .enable(show_geometry&&source_pixel&&geometry_box_ok),.pixel_x(source_x),.pixel_y(y),.hub_x(ahx),.hub_y(ahy),
  .box_x0(gx0),.box_y0(gy0),.box_x1(gx1),.box_y1(gy1),.needle_ink(needle_ink));
 function [7:0] hex_char;
  input [3:0] n;begin hex_char=n<10?48+n:55+n;end
 endfunction
 // FONT_INSERT: copiedunchangedfunctionfromtheexistingapprovedOSDexceptaddedX/Y/H.
    function [34:0] font;
        input [7:0] c;
        begin case(c)
            "0":font=35'b01110100011001110101110011000101110;
            "1":font=35'b00100011000010000100001000010001110;
            "2":font=35'b01110100010000100010001000100011111;
            "3":font=35'b11110000010000101110000010000111110;
            "4":font=35'b00010001100101010010111110001000010;
            "5":font=35'b11111100001000011110000010000111110;
            "6":font=35'b01110100001000011110100011000101110;
            "7":font=35'b11111000010001000100010000100001000;
            "8":font=35'b01110100011000101110100011000101110;
            "9":font=35'b01110100011000101111000010000101110;
            "A":font=35'b01110100011000111111100011000110001;
            "B":font=35'b11110100011000111110100011000111110;
            "C":font=35'b01111100001000010000100001000001111;
            "D":font=35'b11110100011000110001100011000111110;
            "E":font=35'b11111100001000011110100001000011111;
            "F":font=35'b11111100001000011110100001000010000;
            "G":font=35'b01111100001000010111100011000101111;
            "I":font=35'b01110001000010000100001000010001110;
            "J":font=35'b00111000100001000010000101001001100;
            "K":font=35'b10001100101010011000101001001010001;
            "L":font=35'b10000100001000010000100001000011111;
            "M":font=35'b10001110111010110101100011000110001;
            "N":font=35'b10001110011010110011100011000110001;
            "O":font=35'b01110100011000110001100011000101110;
            "P":font=35'b11110100011000111110100001000010000;
            "Q":font=35'b01110100011000110001101011001001101;
            "R":font=35'b11110100011000111110101001001010001;
            "S":font=35'b01111100001000001110000010000111110;
            "T":font=35'b11111001000010000100001000010000100;
            "V":font=35'b10001100011000110001100010101000100;
            "W":font=35'b10001100011000110101101011101110001;
            "=":font=35'b00000000001111100000111110000000000;
            "-":font=35'b00000000000000011111000000000000000;
            ".":font=35'b00000000000000000000000000011000110;
            "/":font=35'b00001000100001000100010000100010000;
            "X":font=35'b10001100010101000100010101000110001;
            "Y":font=35'b10001100010101000100001000010000100;
            "Z":font=35'b11111000010001000100010001000011111;
            "H":font=35'b10001100011000111111100011000110001;
            default:font=0;
        endcase end
    endfunction
 wire panel0=y>=PANEL_Y0&&y<PANEL_Y0+14,panel1=y>=PANEL_Y1&&y<PANEL_Y1+14;
 wire panel2=y>=PANEL_Y1+32&&y<PANEL_Y1+46,panel3=y>=PANEL_Y1+64&&y<PANEL_Y1+78;
 wire cap_panel0=ENABLE_CAPTURE_DIAGNOSTICS&&panel2&&x<640;
 wire cap_panel1=ENABLE_CAPTURE_DIAGNOSTICS&&panel3&&x<640;
 wire cap_panel=cap_panel0||cap_panel1;
 wire panel=((panel0||panel1||panel2||panel3)&&x>=PANEL_X&&x<PANEL_X+640)||cap_panel;
 wire [10:0] panel_dx=cap_panel?x:x-PANEL_X,panel_dy=panel0?y-PANEL_Y0:panel1?y-PANEL_Y1:panel2?y-(PANEL_Y1+32):y-(PANEL_Y1+64);
 wire [4:0] abs_roll=adr[4]?-adr:adr;
 wire [5:0] column=panel_dx[9:4];wire [3:0] pixel_column=panel_dx[3:0];wire [2:0] pixel_row=panel_dy[3:1];
 reg [7:0] ch;reg [3:0] nibble;integer k;
 always @*begin
  ch=" ";nibble=0;
  if(cap_panel0)begin
   case(column)
    0:ch="C";1:ch="A";2:ch="P";3:ch="3";
    5:ch="E";6:ch="=";
    7:ch=show_debug?hex_char(cap_first[11:8]):"-";8:ch=show_debug?hex_char(cap_first[7:4]):"-";9:ch=show_debug?hex_char(cap_first[3:0]):"-";
    11:ch="G";12:ch="=";
    13:ch=show_debug?hex_char({2'b0,cap_groups[17:16]}):"-";14:ch=show_debug?hex_char(cap_groups[15:12]):"-";15:ch=show_debug?hex_char(cap_groups[11:8]):"-";16:ch=show_debug?hex_char(cap_groups[7:4]):"-";17:ch=show_debug?hex_char(cap_groups[3:0]):"-";
    19:ch="W";20:ch="=";
    21:ch=show_debug?hex_char({1'b0,cap_writes[14:12]}):"-";22:ch=show_debug?hex_char(cap_writes[11:8]):"-";23:ch=show_debug?hex_char(cap_writes[7:4]):"-";24:ch=show_debug?hex_char(cap_writes[3:0]):"-";
    26:ch="B";27:ch="=";28:ch=show_debug?(cap_bad?"1":"0"):"-";
    30:ch="F";31:ch="=";32:ch=show_debug?(cap_full?"1":"0"):"-";
    34:ch="Z";35:ch="=";36:ch=show_debug?hex_char({2'b0,cap_close[5:4]}):"-";37:ch=show_debug?hex_char(cap_close[3:0]):"-";
   endcase
  end else if(cap_panel1)begin
   case(column)
    0:ch="R";1:ch="O";2:ch="I";
    4:ch="X";5:ch="=";6:ch=show_debug?hex_char({1'b0,cap_x[10:8]}):"-";7:ch=show_debug?hex_char(cap_x[7:4]):"-";8:ch=show_debug?hex_char(cap_x[3:0]):"-";
    10:ch="Y";11:ch="=";12:ch=show_debug?hex_char({2'b0,cap_y[9:8]}):"-";13:ch=show_debug?hex_char(cap_y[7:4]):"-";14:ch=show_debug?hex_char(cap_y[3:0]):"-";
    16:ch="S";17:ch="=";18:ch=show_debug?hex_char({1'b0,cap_stride}):"-";
    20:ch="R";21:ch="=";22:ch=show_debug?hex_char({1'b0,cap_radius[6:4]}):"-";23:ch=show_debug?hex_char(cap_radius[3:0]):"-";
    25:ch="C";26:ch="=";
    27:ch=show_debug?hex_char(cap_hint[31:28]):"-";28:ch=show_debug?hex_char(cap_hint[27:24]):"-";
    29:ch=show_debug?hex_char(cap_hint[23:20]):"-";30:ch=show_debug?hex_char(cap_hint[19:16]):"-";
    31:ch=show_debug?hex_char(cap_hint[15:12]):"-";32:ch=show_debug?hex_char(cap_hint[11:8]):"-";
    33:ch=show_debug?hex_char(cap_hint[7:4]):"-";34:ch=show_debug?hex_char(cap_hint[3:0]):"-";
    36:ch="Q";37:ch="=";38:ch=show_debug?hex_char({3'b0,cap_reason[4]}):"-";39:ch=show_debug?hex_char(cap_reason[3:0]):"-";
   endcase
  end else if(panel0)begin
   case(column)
    0:ch=show_candidate?(estimated?"E":"C"):"W";
    1:ch=show_candidate?(estimated?"S":"A"):"A";
    2:ch=show_candidate?(estimated?"T":"N"):"I";
    3:ch=show_candidate?(estimated?" ":"D"):"T";
    5:ch="X";6:ch="=";
    7:ch=show_candidate?hex_char(cx_bcd[15:12]):"-";8:ch=show_candidate?hex_char(cx_bcd[11:8]):"-";
    9:ch=show_candidate?hex_char(cx_bcd[7:4]):"-";10:ch=show_candidate?hex_char(cx_bcd[3:0]):"-";
    12:ch="Y";13:ch="=";
    14:ch=show_candidate?hex_char(cy_bcd[15:12]):"-";15:ch=show_candidate?hex_char(cy_bcd[11:8]):"-";
    16:ch=show_candidate?hex_char(cy_bcd[7:4]):"-";17:ch=show_candidate?hex_char(cy_bcd[3:0]):"-";
    19:ch="S";20:ch="=";30:ch="A";31:ch="=";
    32:ch=show_candidate?hex_char(cage[7:4]):"-";33:ch=show_candidate?hex_char(cage[3:0]):"-";
    35:ch="R";36:ch="=";37:ch=show_candidate?hex_char(areason[7:4]):"-";38:ch=show_candidate?hex_char(areason[3:0]):"-";
    default:begin
     for(k=0;k<8;k=k+1)if(column==21+k)ch=show_candidate?hex_char(aid[31-k*4 -:4]):"-";
    end
   endcase
  end else if(panel1)begin
   case(column)
    0:ch=show_measure?(HOLD_RESULTS?"L":"T"):"W";
    1:ch=show_measure?(HOLD_RESULTS?"A":"E"):"A";
    2:ch=show_measure?"S":"I";
    3:ch="T";
    5:ch="V";6:ch="=";
    7:ch=show_measure?hex_char(abcd[15:12]):"-";8:ch=show_measure?hex_char(abcd[11:8]):"-";9:ch=".";
    10:ch=show_measure?hex_char(abcd[7:4]):"-";11:ch=show_measure?hex_char(abcd[3:0]):"-";
    13:ch="S";14:ch="=";24:ch="A";25:ch="=";
    26:ch=show_measure?hex_char(mage_display[7:4]):"-";27:ch=show_measure?hex_char(mage_display[3:0]):"-";
    29:ch="K";30:ch="=";
    31:ch=show_geometry&&aangle<360?hex_char({3'b0,aangle[8]}):"-";32:ch=show_geometry&&aangle<360?hex_char(aangle[7:4]):"-";33:ch=show_geometry&&aangle<360?hex_char(aangle[3:0]):"-";
    default:begin
     for(k=0;k<8;k=k+1)if(column==15+k)ch=show_measure?hex_char(amsrc[31-k*4 -:4]):"-";
    end
   endcase
  end else if(panel2)begin
   case(column)
    0:ch="D";1:ch="B";2:ch="G";4:ch="S";5:ch="=";
    15:ch="Q";16:ch="=";17:ch=show_debug?hex_char({3'b0,adq[4]}):"-";18:ch=show_debug?hex_char(adq[3:0]):"-";
    20:ch="H";21:ch="=";22:ch=show_debug?(adf[2]?"1":"0"):"-";
    24:ch="N";25:ch="=";26:ch=show_debug?(adf[3]?"1":"0"):"-";
    28:ch="F";29:ch="=";30:ch=show_debug?hex_char({2'b0,adm[5:4]}):"-";31:ch=show_debug?hex_char(adm[3:0]):"-";
    33:ch="D";34:ch="=";35:ch=show_debug?hex_char({2'b0,add[9:8]}):"-";36:ch=show_debug?hex_char(add[7:4]):"-";37:ch=show_debug?hex_char(add[3:0]):"-";
    default:for(k=0;k<8;k=k+1)if(column==6+k)ch=show_debug?hex_char(ads[31-k*4 -:4]):"-";
   endcase
  end else if(panel3)begin
   case(column)
    0:ch="C";1:ch="=";2:ch=show_debug?hex_char(adc[7:4]):"-";3:ch=show_debug?hex_char(adc[3:0]):"-";
    5:ch="R";6:ch="=";7:ch=show_debug?(adr[4]?"-":" "):"-";8:ch=show_debug?hex_char({3'b0,abs_roll[4]}):"-";9:ch=show_debug?hex_char(abs_roll[3:0]):"-";
    11:ch="T";12:ch="=";13:ch=show_debug?hex_char({3'b0,adf[4]}):"-";14:ch=show_debug?hex_char(adf[3:0]):"-";
    16:ch="G";17:ch="=";27:ch="A";28:ch="=";29:ch=show_geometry?hex_char(gage_display[7:4]):"-";30:ch=show_geometry?hex_char(gage_display[3:0]):"-";
    32:ch="P";33:ch="=";34:ch=show_candidate?hex_char(ascore[15:12]):"-";35:ch=show_candidate?hex_char(ascore[11:8]):"-";
    default:for(k=0;k<8;k=k+1)if(column==18+k)ch=show_geometry?hex_char(arid[31-k*4 -:4]):"-";
   endcase
  end
 end
 wire [34:0] bits=font(ch);
 wire glyph_ink=panel&&pixel_column<10&&bits[34-pixel_row*5-pixel_column[3:1]];
 wire [23:0] box_color=estimated?24'hff8000:24'hffff00;
 // A held-only T is always orange, including when display_source stopped at
 // that same T. Live mode may conservatively tint the previous VS bundle
 // orange early; it never authorizes geometry or changes its coordinates.
 wire [23:0] geometry_color=geometry_exact_q&&!held_only_shown&&!(update&&live_held_only)?24'h00ffff:24'hff8000;
 wire [23:0] text_color=panel0?(show_candidate?box_color:24'hb0b0b0):panel1?(show_measure?(m_exact?24'h00ff00:24'hff8000):24'hb0b0b0):(show_debug?24'hffffff:24'hb0b0b0);
 // Expose the existing accepted VS snapshot; no new qualification or state.
 assign qualified_payload=shown;
 assign qualified_debug=debug_shown;
 assign qualified_flags={show_debug,show_measure,show_geometry,show_candidate};
 assign qualified_estimated=estimated;
 assign age_loc=cage;
 assign age_geo=gage;
 assign age_read=mage;
 assign out_rgb=!de?rgb:cross_ink?geometry_color:box_ink?box_color:(DRAW_TEXT&&panel)?(glyph_ink?text_color:24'h000000):needle_ink?geometry_color:rgb;
endmodule
