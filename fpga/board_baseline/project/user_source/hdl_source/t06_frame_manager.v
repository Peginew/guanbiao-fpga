// Four DDR frame slots. All ownership state is in the DDR clock domain.
// Publish only the preceding, fully validated input frame. Latest/read/write
// slots stay distinct; display may repeat latest or skip older complete frames.
module t06_frame_manager(
 input wire clk, input wire rst_n,
 input wire camera_boundary, input wire camera_good,
 input wire display_acquire,
 output reg [1:0] write_bank,
 output reg [1:0] latest_bank, output reg latest_valid,
 output reg [1:0] read_bank, output reg read_valid,
 output reg [15:0] committed_frames, output reg [15:0] dropped_frames
);
 reg seen_camera;
 reg [1:0] reset_sync;
 always @(posedge clk or negedge rst_n)
  if(!rst_n)reset_sync<=0;else reset_sync<={reset_sync[0],1'b1};
 reg [1:0] free_bank;
 reg found;
 integer k;
 always @* begin
  free_bank=write_bank;found=0;
  for(k=0;k<4;k=k+1)
   if(!found && k!=write_bank && (!read_valid || k!=read_bank) &&
      (!latest_valid || k!=latest_bank))begin free_bank=k[1:0];found=1;end
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n || !reset_sync[1])begin
   write_bank<=0;latest_bank<=0;latest_valid<=0;read_bank<=0;read_valid<=0;
   seen_camera<=0;committed_frames<=0;dropped_frames<=0;
  end else begin
   if(display_acquire)begin read_bank<=latest_bank;read_valid<=latest_valid;end
   if(camera_boundary)begin
    seen_camera<=1;write_bank<=free_bank;
    if(seen_camera && camera_good)begin
     latest_bank<=write_bank;latest_valid<=1;committed_frames<=committed_frames+1'b1;
    end else if(seen_camera)dropped_frames<=dropped_frames+1'b1;
   end
  end
 end
endmodule
