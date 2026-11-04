set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/return_psi_q8[*] u_meter_pair/pipeline/reader/live/return_psi_valid}] -to [get_clocks {HDMI_PIXEL_CLK}] -datapath_only 7.200
