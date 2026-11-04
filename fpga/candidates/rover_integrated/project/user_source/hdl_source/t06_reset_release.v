// Asynchronous assertion; three local clock edges before reset release.
module t06_reset_release(input wire clk, input wire arst_n, output wire rst_n);
 (* ASYNC_REG="TRUE" *) reg [2:0] release_ff;
 always @(posedge clk or negedge arst_n)
  if(!arst_n)release_ff<=3'b000;
  else release_ff<={release_ff[1:0],1'b1};
 assign rst_n=release_ff[2];
endmodule
